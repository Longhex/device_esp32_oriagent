import json
import time
import socket
import threading
import httpx
from config.logger import setup_logging
from core.providers.llm.base import LLMProviderBase
from core.utils import perf_metrics

TAG = __name__
logger = setup_logging()

# Pool config — shared across all devices using this provider instance.
# keepalive_expiry 300s giữ TCP+TLS sống qua nhiều turn của cùng user và giữa các users.
_HTTPX_TIMEOUT = httpx.Timeout(60.0, connect=5.0, read=60.0, write=10.0)
_HTTPX_LIMITS = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=50,
    keepalive_expiry=300.0,
)

# Method 5: TCP_NODELAY disables Nagle's algorithm — eliminates ~40ms buffering
# delay on small SSE chunks. Shared transport reuses the same pool settings.
_TCP_NODELAY_OPTIONS = [(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)]


class LLMProvider(LLMProviderBase):
    """
    Oriagent LLM Provider (REST API Streaming variant, Dify-based)
    Uses synchronous HTTP streaming to match the framework's sync generator interface.

    Connection pooling: a single httpx.Client is shared across all turns and all
    devices of this provider instance. Eliminates the ~300-600ms DNS+TCP+TLS
    handshake that the previous per-call `with httpx.Client(...)` paid each turn.
    """
    is_dify_provider = True  # Flag to distinguish Dify-based providers

    def __init__(self, config):
        # Configure API URL (priority: api_url > url > base_url)
        self.api_url = config.get("api_url") or config.get("url") or config.get("base_url")
        self.api_key = config.get("api_key")
        self.model_name = config.get("model_name", "oriagent-default")
        self.session_conversation_map = {}  # Map session IDs to Oriagent conversation IDs

        # Persistent pooled client with TCP_NODELAY (Method 5).
        # Transport carries pool limits + socket options so Client inherits both.
        # Try HTTP/2 (giảm thêm RTT cho multi-stream); fallback HTTP/1.1 nếu h2 chưa cài.
        try:
            _transport = httpx.HTTPTransport(
                http2=True,
                limits=_HTTPX_LIMITS,
                socket_options=_TCP_NODELAY_OPTIONS,
            )
            self.http_client = httpx.Client(timeout=_HTTPX_TIMEOUT, transport=_transport)
            self._http_proto = "h2"
        except Exception:
            _transport = httpx.HTTPTransport(
                limits=_HTTPX_LIMITS,
                socket_options=_TCP_NODELAY_OPTIONS,
            )
            self.http_client = httpx.Client(timeout=_HTTPX_TIMEOUT, transport=_transport)
            self._http_proto = "h1"
        logger.bind(tag=TAG).info(
            f"Oriagent HTTP pool ready (proto={self._http_proto}, "
            f"max_keepalive={_HTTPX_LIMITS.max_keepalive_connections}, "
            f"keepalive_expiry={_HTTPX_LIMITS.keepalive_expiry}s, TCP_NODELAY=on)"
        )

        # Task 3.3: pre-warm pool. Mở TCP+TLS sẵn trong background thread để
        # user turn đầu tiên không phải pay handshake (~300-500ms).
        if self.api_url:
            threading.Thread(
                target=self._warmup_pool, name="oriagent-pool-warmup", daemon=True,
            ).start()

    def _warmup_pool(self) -> None:
        """
        Establish 1 HTTP/2 connection tới api_url. Server có thể trả 400/404/405
        cho request không hợp lệ — không sao, miễn là TCP+TLS đã handshake xong và
        connection nằm trong pool keepalive.
        """
        t0 = time.perf_counter()
        try:
            r = self.http_client.head(self.api_url, timeout=5.0)
            elapsed = (time.perf_counter() - t0) * 1000
            logger.bind(tag=TAG).info(
                f"Oriagent pool pre-warmed in {elapsed:.0f}ms (status={r.status_code})"
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.bind(tag=TAG).warning(
                f"Oriagent pool pre-warm failed after {elapsed:.0f}ms: {e}. "
                f"First request sẽ phải mở connection."
            )

    def close(self):
        """Đóng pooled client. An toàn gọi nhiều lần."""
        client = getattr(self, "http_client", None)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    def __del__(self):
        # Best-effort cleanup khi GC. Không raise.
        try:
            self.close()
        except Exception:
            pass

    def _mask_token(self, token):
        if not token or len(str(token)) < 10:
            return "***"
        s_token = str(token)
        return f"{s_token[:6]}...{s_token[-4:]}"

    def response(self, session_id, dialogue, **kwargs):
        """
        Synchronous streaming generator via HTTP REST SSE to match Oriagent/Dify schema.
        Must be a sync generator (not async) to be compatible with the framework.
        """
        if not self.api_url:
            yield "Error: Oriagent API URL is not configured."
            return

        # Extract the latest user query
        try:
            last_msg = next(m for m in reversed(dialogue) if m.get("role") == "user")
            query = last_msg.get("content", "")
        except StopIteration:
            query = "Hello"

        # Priority: explicit kwarg > internal map
        conversation_id = kwargs.get("conversation_id", "") or self.session_conversation_map.get(session_id, "")
        on_conversation_id = kwargs.get("on_conversation_id")

        # Target payload structure matching Oriagent REST requirements
        request_payload = {
            "inputs": {},
            "query": query,
            "response_mode": "streaming",
            "conversation_id": conversation_id,
            "user": session_id,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        logger.bind(tag=TAG).info(
            f"Calling Oriagent API | URL: {self.api_url} | ConvID: {conversation_id or 'New'}"
        )

        # Track last yielded hardware observation to prevent duplicates within the same stream
        last_hardware_obs = None

        # Timing: log Conn (đến status_code) và TTFT (token text đầu tiên) để theo dõi pool hit/miss.
        t0 = time.perf_counter()
        ttft_logged = False

        try:
            # Reuse pooled connection (no per-call DNS+TCP+TLS handshake on cache hit).
            with self.http_client.stream(
                "POST", self.api_url, headers=headers, json=request_payload,
            ) as r:
                connect_ms = (time.perf_counter() - t0) * 1000
                logger.bind(tag=TAG).info(
                    f"Oriagent connect+headers={connect_ms:.0f}ms proto={self._http_proto}"
                )
                perf_metrics.record(
                    "oriagent_connect_ms", connect_ms,
                    proto=self._http_proto, session=session_id,
                )
                if r.status_code != 200:
                    error_body = r.read()
                    logger.bind(tag=TAG).error(f"Oriagent API Error (Status {r.status_code}): {error_body.decode()}")
                    yield f" [HTTP Error {r.status_code}: {error_body.decode()[:100]}] "
                    return

                for line in r.iter_lines():
                    if line.startswith("data: "):
                            try:
                                data_str = line[6:]
                                if data_str == "[DONE]":
                                    break
                                    
                                event = json.loads(data_str)
                                event_type = event.get("event")
                                
                                # Enhanced Logging: Log all event types for observability
                                logger.bind(tag=TAG).debug(f"Oriagent SSE Event: {event_type}")

                                # Persist conversation_id for subsequent turns
                                if not conversation_id and event.get("conversation_id"):
                                    conversation_id = event.get("conversation_id")
                                    self.session_conversation_map[session_id] = conversation_id
                                    if callable(on_conversation_id):
                                        on_conversation_id(conversation_id)
                                
                                # EVENT WHITELIST: Only yield actual text content (message or agent_message)
                                # This blocks prompt leakage from agent_thought or other diagnostic events
                                if event_type in ["message", "agent_message"] and event.get("answer"):
                                    if not ttft_logged:
                                        ttft_ms = (time.perf_counter() - t0) * 1000
                                        logger.bind(tag=TAG).info(
                                            f"Oriagent TTFT={ttft_ms:.0f}ms (first answer chunk)"
                                        )
                                        perf_metrics.record(
                                            "oriagent_ttft_ms", ttft_ms,
                                            session=session_id,
                                            conv_id=conversation_id or "new",
                                        )
                                        ttft_logged = True
                                    yield event["answer"]
                                # CATCH TOOL OUTPUT (Observation from agent_thought)
                                elif event_type == "agent_thought" and event.get("observation"):
                                    obs = event["observation"]
                                    try:
                                        # Parse and prettify JSON for log readability
                                        from core.utils.util import recursive_json_prettify
                                        parsed = json.loads(obs) if isinstance(obs, str) else obs
                                        pretty_obj = recursive_json_prettify(parsed)
                                        pretty_json = json.dumps(pretty_obj, indent=2, ensure_ascii=False)
                                        # Unescape for terminal rendering
                                        pretty_json = pretty_json.replace("\\n", "\n").replace('\\"', '"')
                                        logger.bind(tag=TAG).info(f"\n{'='*20} ORIAGENT TOOL OUTPUT {'='*20}\n{pretty_json}\n{'='*62}")
                                    except:
                                        logger.bind(tag=TAG).info(f"ORIAGENT TOOL RETURN: {obs}")
                                    
                                    # ULTIMATE FIX: Yield hardware commands without double-encoding
                                    is_hardware = False
                                    final_obs = obs
                                    if isinstance(obs, str):
                                        if '%' in obs or '"type": "mcp"' in obs:
                                            is_hardware = True
                                    elif isinstance(obs, dict):
                                        obs_json = json.dumps(obs, ensure_ascii=False)
                                        if '%' in obs_json or '"type": "mcp"' in obs_json:
                                            is_hardware = True
                                            final_obs = obs_json
                                            
                                    if is_hardware:
                                        # Deduplicate: Only yield if this is a NEW hardware command in this stream
                                        if final_obs != last_hardware_obs:
                                            last_hardware_obs = final_obs
                                            logger.bind(tag=TAG).info(f"!!! CRITICAL ORIAGENT YIELD !!! -> {str(final_obs)[:100]}")
                                            yield final_obs
                                        else:
                                            logger.bind(tag=TAG).debug("Skipping duplicate hardware observation in stream")
                                    else:
                                        logger.bind(tag=TAG).debug(f"Skipping internal tool observation")
                                elif event_type == "message_end":
                                    total_ms = (time.perf_counter() - t0) * 1000
                                    logger.bind(tag=TAG).debug(f"Oriagent message end. Total={total_ms:.0f}ms")
                                    perf_metrics.record(
                                        "oriagent_total_ms", total_ms, session=session_id,
                                    )
                                    break
                                elif event_type == "error":
                                    error_msg = event.get("message", "Unknown Oriagent error")
                                    logger.bind(tag=TAG).error(f"Oriagent API Internal Error: {error_msg}")
                                    perf_metrics.record(
                                        "oriagent_error_ms",
                                        (time.perf_counter() - t0) * 1000,
                                        session=session_id, error=str(error_msg)[:60],
                                    )
                                    yield f" [LLM Error: {error_msg}] "
                                    break
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            logger.bind(tag=TAG).error(f"Failed to connect to Oriagent: {str(e)}")
            yield f" [System Error: Connection to Oriagent failed] "

    def response_with_functions(self, session_id, dialogue, functions=None, **kwargs):
        """
        Wrapper for function-calling support. 
        Note: Specific Oriagent model configuration required for true function calling.
        """
        for token in self.response(session_id, dialogue, **kwargs):
            yield token, None
