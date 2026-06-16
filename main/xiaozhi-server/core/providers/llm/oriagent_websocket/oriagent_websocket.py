"""
Oriagent LLM Provider — WebSocket variant (oriagent_websocket)

Replaces HTTP SSE with a persistent WebSocket connection to the oriagent
ws_gateway (/ws/chat).  One WS connection is maintained per device (user_id).
Subsequent turns from the same device reuse the existing connection — zero
TCP+TLS+WS handshake overhead after the first call.

Activity-window design (reduces server load):
  - WS is created on first use (lazy), NOT on boot.
  - After activity_window_seconds of inactivity, the connection is closed
    automatically by the background keepalive thread.
  - While active, a ping is sent every keepalive_interval_seconds to prevent
    nginx from killing the idle-but-still-active connection.
  - Reconnect on next use is transparent (~150ms handshake, paid once per session).

Config fields (same keys as oriagent_http for easy A/B swap):
  api_key:                   app-xxxxxxxx   (Oriagent App API token)
  ws_url:                    ws://host:5001/ws/chat  (required, or auto-converted)
  activity_window_seconds:   300   (close WS after N seconds idle, default 5 min)
  keepalive_interval_seconds: 120  (ping interval while active, default 2 min)

Perf metrics emitted:
  oriagent_websocket_connect_ms  — new-connection cost (WS handshake + auth)
  oriagent_websocket_ttft_ms     — time to first text chunk
  oriagent_websocket_total_ms    — total time to done frame
  oriagent_websocket_error_ms    — time when an error frame arrives
"""

import json
import threading
import time
from typing import Dict, Optional, Tuple

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect as ws_connect

from config.logger import setup_logging
from core.providers.llm.base import LLMProviderBase
from core.utils import perf_metrics

TAG = __name__
logger = setup_logging()

_CONNECT_TIMEOUT = 10   # seconds — WS handshake + connected frame
_RECV_TIMEOUT    = 60   # seconds — max wait between frames during stream
_LOCK_TIMEOUT    = 30   # seconds — per-device lock acquire timeout


class LLMProvider(LLMProviderBase):
    is_dify_provider = True

    def __init__(self, config):
        self.api_key    = config.get("api_key", "")
        self.ws_url     = (
            config.get("ws_url")
            or self._http_to_ws(config.get("api_url") or config.get("url") or "")
        )
        self.model_name = config.get("model_name", "oriagent-ws2")

        # How long to keep a WS connection alive after the last response (seconds).
        # After this window, the background thread closes the connection to free
        # server resources.  Set 0 to disable auto-close (always-on mode).
        self._activity_window    = int(config.get("activity_window_seconds", 300))

        # Interval between keepalive pings while a connection is active (seconds).
        # Must be well under nginx proxy_read_timeout (3600s).
        self._keepalive_interval = int(config.get("keepalive_interval_seconds", 120))

        self.session_conversation_map: Dict[str, str] = {}

        # Connection pool — one live WS per device (user_id).
        self._conns:      Dict[str, object]         = {}  # user_id → ws object
        self._conn_locks: Dict[str, threading.Lock] = {}  # per-device serialize lock
        self._pool_lock   = threading.Lock()               # guards _conns + _conn_locks

        # Keepalive / activity-window management
        self._last_activity: Dict[str, float] = {}   # user_id → epoch of last response
        self._keepalive_running = False
        self._keepalive_thread: Optional[threading.Thread] = None

        logger.bind(tag=TAG).info(
            f"Oriagent WS provider ready — ws_url={self.ws_url} "
            f"activity_window={self._activity_window}s "
            f"keepalive_interval={self._keepalive_interval}s"
        )

    # ------------------------------------------------------------------
    # Public interface (drop-in for LLMProviderBase)
    # ------------------------------------------------------------------

    def response(self, session_id, dialogue, **kwargs):
        """
        Sync generator — yields text tokens via persistent WebSocket.
        Acquires a per-device lock so only one in-flight request per device.
        """
        if not self.ws_url or not self.api_key:
            yield "Error: ws_url and api_key must be configured for oriagent_websocket."
            return

        user_id = kwargs.get("user_id") or session_id
        # Strip user_id from kwargs — _stream receives it as a positional arg,
        # so passing it again via **kwargs causes "multiple values for argument".
        stream_kwargs = {k: v for k, v in kwargs.items() if k != "user_id"}
        lock = self._get_device_lock(user_id)

        if not lock.acquire(timeout=_LOCK_TIMEOUT):
            yield f" [Error: device {user_id[:16]} busy — try again] "
            return

        try:
            yield from self._stream(user_id, session_id, dialogue, **stream_kwargs)
        finally:
            lock.release()

    def response_with_functions(self, session_id, dialogue, functions=None, **kwargs):
        for token in self.response(session_id, dialogue, **kwargs):
            yield token, None

    def close(self) -> None:
        """Close all pooled connections and stop the keepalive thread."""
        self._keepalive_running = False
        with self._pool_lock:
            for ws in self._conns.values():
                try:
                    ws.close()
                except Exception:
                    pass
            self._conns.clear()
            self._conn_locks.clear()
            self._last_activity.clear()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Connection pool
    # ------------------------------------------------------------------

    def _get_device_lock(self, user_id: str) -> threading.Lock:
        with self._pool_lock:
            if user_id not in self._conn_locks:
                self._conn_locks[user_id] = threading.Lock()
            return self._conn_locks[user_id]

    def _get_or_connect(self, user_id: str) -> Tuple[object, Optional[float]]:
        """
        Return (ws, connect_ms_or_None).
        Reuses an existing connection if present in pool (assumes alive;
        ConnectionClosed will be caught on send/recv and triggers reconnect).
        connect_ms is None when reusing, float (ms) when a new connection is made.
        """
        with self._pool_lock:
            ws = self._conns.get(user_id)
        if ws is not None:
            return ws, None

        url = f"{self.ws_url}?token={self.api_key}&device_id={user_id}"
        t0  = time.perf_counter()
        ws  = ws_connect(url, open_timeout=_CONNECT_TIMEOUT)

        # Drain connected handshake frame
        raw   = ws.recv(timeout=_CONNECT_TIMEOUT)
        frame = json.loads(raw)
        if frame.get("t") != "connected":
            ws.close()
            raise ConnectionError(f"Unexpected handshake frame: {frame.get('t')!r}")

        connect_ms = (time.perf_counter() - t0) * 1000
        logger.bind(tag=TAG).info(
            f"[WS] New connection for {user_id[:16]} in {connect_ms:.0f}ms"
        )

        with self._pool_lock:
            self._conns[user_id]         = ws
            self._last_activity[user_id] = time.time()
            self._ensure_keepalive_running()

        return ws, connect_ms

    def _drop_conn(self, user_id: str) -> None:
        """Remove and close a device's pooled connection."""
        with self._pool_lock:
            ws = self._conns.pop(user_id, None)
            self._last_activity.pop(user_id, None)
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Keepalive / activity-window background thread
    # ------------------------------------------------------------------

    def _ensure_keepalive_running(self) -> None:
        """Start the keepalive thread if not already running. Call with _pool_lock held."""
        if self._keepalive_running:
            return
        self._keepalive_running = True
        t = threading.Thread(
            target=self._keepalive_loop,
            daemon=True,
            name="ws-keepalive",
        )
        t.start()
        self._keepalive_thread = t

    def _keepalive_loop(self) -> None:
        """
        Background thread — runs while at least one connection is active.

        Every keepalive_interval seconds it inspects each connection:
          - If idle longer than activity_window: close and evict.
          - Otherwise: send a ping to prevent nginx from closing the connection.

        Pings are send-only (fire-and-forget); the pong frame is silently
        dropped by the _stream() recv loop (unknown frame → ignored).

        Tries a non-blocking lock acquire per device: skips devices that are
        currently in-flight (response() holds the lock) so it never contends.
        """
        logger.bind(tag=TAG).debug("[WS] Keepalive thread started")

        while self._keepalive_running:
            time.sleep(self._keepalive_interval)

            if not self._keepalive_running:
                break

            now = time.time()

            with self._pool_lock:
                user_ids = list(self._conns.keys())

            for user_id in user_ids:
                lock = self._get_device_lock(user_id)

                # Non-blocking: if the device is in-flight, skip this cycle.
                if not lock.acquire(timeout=0):
                    continue

                try:
                    with self._pool_lock:
                        ws = self._conns.get(user_id)
                    if ws is None:
                        continue  # already dropped by another path

                    last = self._last_activity.get(user_id, 0)
                    idle_s = now - last

                    # Activity window expired → evict
                    if self._activity_window > 0 and idle_s > self._activity_window:
                        logger.bind(tag=TAG).info(
                            f"[WS] Closing idle connection {user_id[:16]} "
                            f"(idle {idle_s:.0f}s > window {self._activity_window}s)"
                        )
                        self._drop_conn(user_id)
                        continue

                    # Still within window → ping to prevent nginx idle-close
                    try:
                        ws.send(json.dumps({"t": "ping", "ts": now}))
                        logger.bind(tag=TAG).debug(
                            f"[WS] Keepalive ping sent to {user_id[:16]} (idle {idle_s:.0f}s)"
                        )
                    except ConnectionClosed:
                        logger.bind(tag=TAG).info(
                            f"[WS] Keepalive ping failed — connection dead for {user_id[:16]}"
                        )
                        self._drop_conn(user_id)
                    except Exception as exc:
                        logger.bind(tag=TAG).warning(
                            f"[WS] Keepalive error for {user_id[:16]}: {exc}"
                        )

                finally:
                    lock.release()

            # Stop the thread when no connections remain
            with self._pool_lock:
                if not self._conns:
                    self._keepalive_running = False
                    logger.bind(tag=TAG).debug("[WS] No connections — keepalive thread exiting")
                    return

        logger.bind(tag=TAG).debug("[WS] Keepalive thread stopped")

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def _stream(self, user_id: str, session_id: str, dialogue: list, **kwargs):
        """
        Inner generator — sends one chat message on the persistent connection
        and yields frames until done/err.  On ConnectionClosed, drops the
        connection and retries once with a fresh one (_conn_retry guard).
        """
        query           = self._last_user_query(dialogue)
        conversation_id = (
            kwargs.get("conversation_id", "")
            or self.session_conversation_map.get(session_id, "")
        )
        on_conversation_id      = kwargs.get("on_conversation_id")
        on_conversation_cleared = kwargs.get("on_conversation_cleared")
        inputs      = kwargs.get("inputs") or {}
        _conn_retry = kwargs.get("_conn_retry", False)  # True after a ConnectionClosed reconnect
        _conv_retry = kwargs.get("_conv_retry", False)  # True after a conv self-heal retry

        # ── Acquire connection ────────────────────────────────────────────
        try:
            ws, connect_ms = self._get_or_connect(user_id)
        except Exception as exc:
            logger.bind(tag=TAG).error(f"[WS] Connect failed ({user_id[:16]}): {exc}")
            yield " [System Error: WS connect failed] "
            return

        if connect_ms is not None:
            perf_metrics.record(
                "oriagent_websocket_connect_ms", connect_ms, session=session_id
            )
        else:
            logger.bind(tag=TAG).debug(f"[WS] Reusing connection for {user_id[:16]}")

        t0 = time.perf_counter()
        ttft_logged       = False
        last_hardware_obs = None

        # ── Send chat frame ───────────────────────────────────────────────
        chat_frame: dict = {"t": "chat", "text": query, "cid": conversation_id or ""}
        if inputs:
            chat_frame["inputs"] = inputs

        try:
            ws.send(json.dumps(chat_frame, ensure_ascii=False))
        except ConnectionClosed:
            self._drop_conn(user_id)
            if not _conn_retry:
                logger.bind(tag=TAG).info(
                    f"[WS] Connection dropped on send — reconnecting ({user_id[:16]})"
                )
                yield from self._stream(
                    user_id, session_id, dialogue,
                    **{**kwargs, "_conn_retry": True},
                )
                return
            yield " [System Error: WS connection dropped] "
            return

        # ── Receive stream ────────────────────────────────────────────────
        while True:
            try:
                raw = ws.recv(timeout=_RECV_TIMEOUT)
            except ConnectionClosed:
                self._drop_conn(user_id)
                if not _conn_retry:
                    logger.bind(tag=TAG).info(
                        f"[WS] Connection dropped mid-stream — reconnecting ({user_id[:16]})"
                    )
                    yield from self._stream(
                        user_id, session_id, dialogue,
                        **{**kwargs, "_conn_retry": True},
                    )
                    return
                yield " [System Error: WS connection dropped] "
                return
            except TimeoutError:
                self._drop_conn(user_id)
                logger.bind(tag=TAG).error(f"[WS] Recv timeout ({user_id[:16]})")
                yield " [System Error: WS timeout] "
                return

            try:
                frame = json.loads(raw)
            except (ValueError, TypeError):
                logger.bind(tag=TAG).warning(f"[WS] Non-JSON frame: {raw[:80]}")
                continue

            t = frame.get("t")

            # ── Text token ────────────────────────────────────────────────
            if t == "chunk":
                text = frame.get("d", "")
                if text:
                    if not ttft_logged:
                        ttft_ms = (time.perf_counter() - t0) * 1000
                        logger.bind(tag=TAG).info(f"[WS] TTFT={ttft_ms:.0f}ms")
                        perf_metrics.record(
                            "oriagent_websocket_ttft_ms", ttft_ms,
                            session=session_id,
                            conv_id=conversation_id or "new",
                        )
                        ttft_logged = True
                    yield text

            # ── Hardware / MCP command ────────────────────────────────────
            elif t == "cmd":
                obs = frame.get("d", "")
                if obs and obs != last_hardware_obs:
                    last_hardware_obs = obs
                    logger.bind(tag=TAG).info(f"[WS] Hardware cmd: {str(obs)[:100]}")
                    yield obs

            # ── Replace streamed text ─────────────────────────────────────
            elif t == "replace":
                text = frame.get("d", "")
                if text:
                    yield text

            # ── File attachment ───────────────────────────────────────────
            elif t == "file":
                logger.bind(tag=TAG).debug(
                    f"[WS] File: type={frame.get('type')} "
                    f"url={frame.get('url', '')[:60]}"
                )

            # ── Stream done ───────────────────────────────────────────────
            elif t == "done":
                total_ms = (time.perf_counter() - t0) * 1000
                logger.bind(tag=TAG).info(f"[WS] Done. Total={total_ms:.0f}ms")
                perf_metrics.record(
                    "oriagent_websocket_total_ms", total_ms, session=session_id
                )
                new_cid = frame.get("cid")
                if new_cid and new_cid != conversation_id:
                    conversation_id = new_cid
                    self.session_conversation_map[session_id] = conversation_id
                    if callable(on_conversation_id):
                        on_conversation_id(conversation_id)

                # Mark activity so keepalive knows this device is still in use
                with self._pool_lock:
                    self._last_activity[user_id] = time.time()
                break

            # ── Error from server ─────────────────────────────────────────
            elif t == "err":
                error_msg  = frame.get("msg", "Unknown error")
                error_code = frame.get("code", "")
                elapsed_ms = (time.perf_counter() - t0) * 1000
                perf_metrics.record(
                    "oriagent_websocket_error_ms", elapsed_ms,
                    session=session_id, error=error_msg[:60],
                )

                # Self-healing mirrors HTTP provider's exact conditions:
                #   conv_error     — server couldn't heal stale/completed conversation
                #   bad_history    — model rejects conversation with function-role messages
                is_bad_history = (
                    error_code == "llm_error"
                    and "function" in error_msg.lower()
                    and ("messages[" in error_msg or "role" in error_msg.lower())
                )
                is_recoverable = (
                    bool(conversation_id)
                    and not _conv_retry
                    and (error_code == "conv_error" or is_bad_history)
                )

                if is_recoverable:
                    reason = "conv_error" if error_code == "conv_error" else "bad function-role history"
                    logger.bind(tag=TAG).info(
                        f"[WS] Self-heal ({reason}) — resetting conversation"
                    )
                    self.session_conversation_map.pop(session_id, None)
                    if callable(on_conversation_cleared):
                        try:
                            on_conversation_cleared()
                        except Exception as cb_err:
                            logger.bind(tag=TAG).error(
                                f"on_conversation_cleared failed: {cb_err}"
                            )
                    yield from self._stream(
                        user_id, session_id, dialogue,
                        **{**kwargs, "conversation_id": "", "_conv_retry": True},
                    )
                    return

                logger.bind(tag=TAG).error(
                    f"[WS] Server error: {error_msg} (code={error_code})"
                )
                yield f" [LLM Error: {error_msg}] "
                break

            # pong and other unknown frame types are dropped silently

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _last_user_query(dialogue: list) -> str:
        try:
            return next(
                m.get("content", "")
                for m in reversed(dialogue)
                if m.get("role") == "user"
            )
        except StopIteration:
            return "Hello"

    @staticmethod
    def _http_to_ws(url: str) -> str:
        """Auto-convert HTTP chat-messages URL to WS chat URL."""
        if not url:
            return ""
        url = url.replace("https://", "wss://").replace("http://", "ws://")
        if "/v1/chat-messages" in url:
            return url.replace("/v1/chat-messages", "/ws/chat")
        return url.rstrip("/") + "/ws/chat"
