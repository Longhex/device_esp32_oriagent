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
from typing import Callable, Dict, Optional, Tuple

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

        # Tracks whether the previous stream on this connection ended cleanly
        # (i.e., received a done/err frame). False means the stream was abandoned
        # mid-flight (user abort), so there are stale frames in the socket buffer.
        self._stream_clean: Dict[str, bool] = {}  # user_id → True if buffer is clean

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

    def warmup(
        self,
        user_id: str,
        session_id: str = "",
        trigger: str = "listen_start",
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """Open or reuse the per-device Oriagent WS without sending a chat request."""
        if callable(is_cancelled) and is_cancelled():
            return False
        if not self.ws_url or not self.api_key or not user_id:
            logger.bind(tag=TAG).warning(
                "[TIMING] event=oriagent_ws_warm_skipped trigger={} reason=missing_config_or_user wall_ms={}",
                trigger,
                int(time.time() * 1000),
            )
            return False

        lock = self._get_device_lock(user_id)
        warm_started = time.perf_counter()
        logger.bind(tag=TAG).info(
            "[TIMING] event=oriagent_ws_warm_requested device={} session={} trigger={} wall_ms={}",
            user_id[:16],
            session_id or "-",
            trigger,
            int(time.time() * 1000),
        )
        if not lock.acquire(timeout=_LOCK_TIMEOUT):
            logger.bind(tag=TAG).warning(
                "[TIMING] event=oriagent_ws_warm_busy device={} session={} trigger={} wall_ms={}",
                user_id[:16],
                session_id or "-",
                trigger,
                int(time.time() * 1000),
            )
            return False

        try:
            if callable(is_cancelled) and is_cancelled():
                return False
            _, connect_ms = self._get_or_connect(user_id)
            if callable(is_cancelled) and is_cancelled():
                self._drop_conn(user_id, reason="warmup_cancelled")
                logger.bind(tag=TAG).info(
                    "[TIMING] event=oriagent_ws_warm_cancelled device={} session={} trigger={} wall_ms={}",
                    user_id[:16],
                    session_id or "-",
                    trigger,
                    int(time.time() * 1000),
                )
                return False
            elapsed_ms = (time.perf_counter() - warm_started) * 1000
            if connect_ms is not None:
                perf_metrics.record(
                    "oriagent_websocket_connect_ms",
                    connect_ms,
                    session=session_id or user_id,
                )
            logger.bind(tag=TAG).info(
                "[TIMING] event=oriagent_ws_warm_ready device={} session={} trigger={} wall_ms={} elapsed_ms={:.3f} reused={}",
                user_id[:16],
                session_id or "-",
                trigger,
                int(time.time() * 1000),
                elapsed_ms,
                connect_ms is None,
            )
            return True
        except Exception as exc:
            logger.bind(tag=TAG).error(
                "[TIMING] event=oriagent_ws_warm_failed device={} session={} trigger={} wall_ms={} error={}",
                user_id[:16],
                session_id or "-",
                trigger,
                int(time.time() * 1000),
                exc,
            )
            return False
        finally:
            lock.release()

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
            "[TIMING] event=oriagent_ws_opened device={} wall_ms={} connect_ms={:.3f}",
            user_id[:16],
            int(time.time() * 1000),
            connect_ms,
        )

        with self._pool_lock:
            self._conns[user_id]         = ws
            self._stream_clean[user_id]  = True   # fresh connection — buffer is clean
            self._last_activity[user_id] = time.time()
            self._ensure_keepalive_running()

        return ws, connect_ms

    def _drop_conn(self, user_id: str, reason: str = "unspecified") -> None:
        """Remove and close a device's pooled connection."""
        with self._pool_lock:
            ws = self._conns.pop(user_id, None)
            self._last_activity.pop(user_id, None)
            self._stream_clean.pop(user_id, None)
        if ws is not None:
            logger.bind(tag=TAG).info(
                "[TIMING] event=oriagent_ws_closed device={} wall_ms={} reason={}",
                user_id[:16],
                int(time.time() * 1000),
                reason,
            )
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

        # ── Drain stale buffer from a previously aborted stream ───────────
        # When user aborts mid-stream, the generator is abandoned without reading
        # the server's done/err frame.  Those frames remain in the socket buffer
        # and would be returned by the next ws.recv() — causing the new request
        # to play the previous turn's audio response (1-turn shift bug).
        if not self._stream_clean.get(user_id, True):
            logger.bind(tag=TAG).warning(
                f"[WS] Stale buffer detected for {user_id[:16]} — draining before new request"
            )
            drained_ok = self._drain_stale(ws, user_id)
            if not drained_ok:
                # _drain_stale already dropped the connection; reconnect now
                try:
                    ws, connect_ms = self._get_or_connect(user_id)
                except Exception as exc:
                    logger.bind(tag=TAG).error(f"[WS] Reconnect after drain failed ({user_id[:16]}): {exc}")
                    yield " [System Error: WS reconnect failed] "
                    return
                if connect_ms is not None:
                    perf_metrics.record(
                        "oriagent_websocket_connect_ms", connect_ms, session=session_id
                    )

        # Mark buffer as dirty before sending — will be reset to True on done/err
        self._stream_clean[user_id] = False

        # ── Send chat frame ───────────────────────────────────────────────
        chat_frame: dict = {"t": "chat", "text": query, "cid": conversation_id or ""}
        if inputs:
            chat_frame["inputs"] = inputs

        try:
            ws.send(json.dumps(chat_frame, ensure_ascii=False))
            logger.bind(tag=TAG).info(
                "[TIMING] event=oriagent_request_sent device={} session={} wall_ms={} reused={} query_chars={}",
                user_id[:16],
                session_id or "-",
                int(time.time() * 1000),
                connect_ms is None,
                len(query),
            )
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
                        logger.bind(tag=TAG).info(
                            "[TIMING] event=oriagent_first_response device={} session={} wall_ms={} ttft_ms={:.3f}",
                            user_id[:16],
                            session_id or "-",
                            int(time.time() * 1000),
                            ttft_ms,
                        )
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

                # Mark buffer clean — no stale frames remain
                self._stream_clean[user_id] = True
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
                    self._stream_clean[user_id] = True  # err frame is terminal; buffer clean before retry
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
                self._stream_clean[user_id] = True  # err frame = terminal, buffer clean
                yield f" [LLM Error: {error_msg}] "
                break

            # pong and other unknown frame types are dropped silently

    # ------------------------------------------------------------------
    # Stale-buffer drain
    # ------------------------------------------------------------------

    def _drain_stale(self, ws, user_id: str) -> bool:
        """
        Drain leftover frames from a previously aborted stream.

        Reads frames until a terminal done/err frame is received or a
        timeout/error occurs.  Returns True if drained cleanly, False if
        the connection had to be dropped (caller should reconnect).
        """
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                raw = ws.recv(timeout=min(2.0, remaining))
                try:
                    frame = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                t = frame.get("t")
                if t in ("done", "err"):
                    logger.bind(tag=TAG).info(
                        f"[WS] Stale buffer drained cleanly for {user_id[:16]}"
                    )
                    self._stream_clean[user_id] = True
                    return True
            except ConnectionClosed:
                self._drop_conn(user_id)
                return False
            except TimeoutError:
                break
            except Exception as exc:
                logger.bind(tag=TAG).warning(
                    f"[WS] Error draining stale buffer for {user_id[:16]}: {exc}"
                )
                break

        # Drain timed out or errored — drop connection to guarantee clean state
        logger.bind(tag=TAG).warning(
            f"[WS] Drain timeout for {user_id[:16]} — dropping connection for clean restart"
        )
        self._drop_conn(user_id)
        return False

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
