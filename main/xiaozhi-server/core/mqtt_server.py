import asyncio
import json
import os
import queue
import uuid
import threading
import time
import paho.mqtt.client as mqtt
from config.logger import setup_logging, bind_log_context
from core.auth import AuthenticationError
from core.mqtt_topics import hk_uplink_subscription, parse_hk_uplink_topic
from core.utils.util import get_local_ip

# Try to import our new UDP manager
try:
    from core.udp_server import udp_manager
except ImportError:
    udp_manager = None

TAG = "mqtt_server"
HK_SIGNALING_CONTRACT = "hk_legacy"


def is_hk_signaling_contract():
    return os.environ.get("MQTT_SIGNALING_CONTRACT", "canonical").strip().lower() == HK_SIGNALING_CONTRACT


def build_hk_server_hello(base_hello, session_id, udp_config):
    """Convert the shared AI hello into the contract parsed by HK firmware."""
    try:
        message = json.loads(base_hello) if isinstance(base_hello, str) else dict(base_hello)
    except (TypeError, ValueError, json.JSONDecodeError):
        return base_hello
    if message.get("type") != "hello":
        return base_hello
    message["transport"] = "udp"
    message["session_id"] = session_id
    message["udp"] = dict(udp_config)
    return json.dumps(message, separators=(",", ":"))


def is_test_inject_text_enabled() -> bool:
    return os.environ.get("ENABLE_TEST_INJECT_TEXT", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def extract_injected_text(payload: str):
    if not isinstance(payload, str) or not payload.startswith("INJECT_TEXT:"):
        return None
    return payload.split(":", 1)[1].strip()


def _summarize_state_payload(payload: str):
    try:
        data = json.loads(payload)
    except Exception:
        return None, {}

    if not isinstance(data, dict):
        return None, {}

    return data.get("type"), data

class VirtualWebsocket:
    """Mocks the websockets.ServerConnection to minimize refactoring in ConnectionHandler"""
    def __init__(
        self,
        device_id,
        session_id,
        mqtt_client,
        loop,
        logger=None,
        hk_udp_config=None,
        mqtt_downlink_topic=None,
    ):
        self.device_id = device_id
        self.session_id = session_id
        self.mqtt_client = mqtt_client
        self.loop = loop
        self.logger = bind_log_context(
            logger or setup_logging(),
            transport="HYBRID",
            phase="SIGNAL",
            device_id=device_id,
            session_id=session_id,
        )
        self.closed = False
        self.close_requested = False
        self._sentinel_enqueued = False
        self._message_queue = asyncio.Queue()
        self.connection_handler = None
        self.hk_udp_config = hk_udp_config
        self.mqtt_downlink_topic = mqtt_downlink_topic
        self.remote_address = (device_id, 0)

        class MockRequest:
            def __init__(self, device_id):
                self.headers = {
                    "device-id": device_id,
                    "client-id": device_id,
                    "x-real-ip": "mqtt-gateway",
                }
                self.path = "/mqtt_gateway?from=mqtt_gateway"
        self.request = MockRequest(device_id)

    async def send(self, message):
        if self.closed:
            return
            
        if isinstance(message, bytes):
            if udp_manager:
                session = udp_manager.get_session(self.session_id)
                if session:
                    session.send_audio(message)
                else:
                    self.logger.bind(tag=TAG).debug(f"UDP Session {self.session_id} not found for audio.")
            return

        if self.hk_udp_config:
            message = build_hk_server_hello(
                message, self.session_id, self.hk_udp_config
            )
        topic = self.mqtt_downlink_topic or f"{self.device_id}/MONITOR"
        try:
            self.mqtt_client.publish(topic, message)
            self.logger.bind(tag=TAG).debug(f"Published to {topic}: {message[:200]}")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Error publishing MQTT: {e}")

    def _enqueue_sentinel_threadsafe(self):
        if self._sentinel_enqueued:
            return

        def _enqueue():
            if self._sentinel_enqueued:
                return
            try:
                self._message_queue.put_nowait(None)
                self._sentinel_enqueued = True
            except asyncio.QueueFull:
                # The queue is unbounded today, but keep this defensive path to
                # avoid raising from close() if that changes later.
                pass

        self.loop.call_soon_threadsafe(_enqueue)

    async def close(self, code=None, reason="unknown"):
        if self.close_requested:
            return

        self.close_requested = True
        self.logger.bind(tag=TAG).info(
            f"[MQTT] closing virtual websocket device={self.device_id} session={self.session_id} reason={reason}"
        )
        self._enqueue_sentinel_threadsafe()
        self.closed = True

    def put_message_threadsafe(self, message):
        if not self.close_requested:
            self.loop.call_soon_threadsafe(self._message_queue.put_nowait, message)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.closed:
            raise StopAsyncIteration
        msg = await self._message_queue.get()
        if msg is None:  # Sentinel to close
            self.closed = True
            raise StopAsyncIteration
        return msg


class MqttServer:
    def __init__(self, config: dict, websocket_server):
        self.config = config
        self.logger = bind_log_context(setup_logging(), transport="HYBRID", phase="SIGNAL")
        self.ws_server = websocket_server # Reuse modules and auth from ws_server
        self.client = mqtt.Client(client_id=f"xiaozhi-server-{uuid.uuid4().hex[:8]}")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.loop = asyncio.get_running_loop()
        self.active_sessions = {} # device_id -> VirtualWebsocket
        self.session_meta = {}
        self.completed_cleanups = set()
        self.last_hello_by_device = {}
        self.hk_signaling = is_hk_signaling_contract()

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.logger.bind(tag=TAG).info("Connected to MQTT Broker!")
            if self.hk_signaling:
                # Compatibility window: accept the old bare-serial uplink and
                # the OTA-advertised {serial}/AI_MONITOR uplink.
                self.client.subscribe("+")
                self.client.subscribe(hk_uplink_subscription())
                self.logger.bind(tag=TAG).info(
                    "HK MQTT signaling enabled: subscribed to legacy and OTA-advertised topics"
                )
            else:
                self.client.subscribe("devices/+/signaling")
                self.client.subscribe("devices/+/state")
        else:
            self.logger.bind(tag=TAG).error(f"Failed to connect to MQTT, return code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode('utf-8')
            topic = msg.topic

            if self.hk_signaling:
                if topic in {
                    "HAKAT_AI_MONITOR_ALL",
                    "HAKAT_AI_REMOTE_ALL",
                    "DEVICE_OFFLINE",
                }:
                    return
                try:
                    device_id, downlink_topic = parse_hk_uplink_topic(topic)
                except ValueError:
                    device_id = None

                if device_id is not None:
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        self.logger.bind(tag=TAG).warning(
                            f"Ignoring invalid HK signaling JSON topic={topic}"
                        )
                        return
                    if not isinstance(data, dict):
                        return
                    if data.get("type") == "hello":
                        self.loop.call_soon_threadsafe(
                            asyncio.create_task,
                            self.handle_hk_hello(
                                device_id, payload, data, downlink_topic
                            ),
                        )
                        return
                    session = self.active_sessions.get(device_id)
                    if session:
                        meta = self.session_meta.get(session.session_id)
                        if meta:
                            meta["last_activity"] = time.time()
                        session.put_message_threadsafe(payload)
                    return

                if "/" not in topic:
                    self.logger.bind(tag=TAG).warning(
                        f"Ignoring invalid HK signaling topic={topic}"
                    )
                    return
            
            parts = topic.split('/')
            if len(parts) >= 3 and parts[0] == "devices":
                device_id = parts[1]
                subtopic = parts[2]
                
                if subtopic == "signaling":
                    # Handle call_invite
                    self.loop.call_soon_threadsafe(
                        asyncio.create_task, self.handle_signaling(payload)
                    )
                elif subtopic == "state":
                    injected_text = extract_injected_text(payload)
                    if injected_text:
                        if is_test_inject_text_enabled():
                            session = self.active_sessions.get(device_id)
                            if session and session.connection_handler:
                                self.logger.bind(tag=TAG).warning(
                                    "[TEST-ONLY] INJECT_TEXT accepted for device={}",
                                    device_id,
                                )
                                session.connection_handler.executor.submit(
                                    session.connection_handler.chat,
                                    injected_text,
                                )
                        else:
                            self.logger.bind(tag=TAG).warning(
                                "[TEST-ONLY] INJECT_TEXT ignored because ENABLE_TEST_INJECT_TEXT is disabled"
                            )
                        return
                    # Handle state or JSON commands for existing session
                    session = self.active_sessions.get(device_id)
                    state_type, state_data = _summarize_state_payload(payload)
                    if state_type == "hello":
                        self.last_hello_by_device[device_id] = {
                            "payload": payload,
                            "data": state_data,
                            "captured_at": time.time(),
                        }
                        audio_params = state_data.get("audio_params", {})
                        self.logger.bind(tag=TAG).info(
                            "[MQTT] hello from device {}: format={} sample_rate={} frame_duration={} active_session={}",
                            device_id,
                            audio_params.get("format", "-"),
                            audio_params.get("sample_rate", "-"),
                            audio_params.get("frame_duration", "-"),
                            "yes" if session else "no",
                        )
                    elif state_type and session:
                        self.logger.bind(tag=TAG).debug(
                            "[MQTT] state message type={} from device {} active_session=yes",
                            state_type,
                            device_id,
                        )
                    if session:
                        meta = self.session_meta.get(session.session_id)
                        if meta:
                            meta["last_activity"] = time.time()
                        session.put_message_threadsafe(payload)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Error handling MQTT message: {e}")

    async def handle_hk_hello(
        self, device_id, payload, hello_data, downlink_topic=None
    ):
        """Open the voice session expected by HK MqttProtocol::OpenAudioChannel."""
        try:
            if hello_data.get("transport") != "udp":
                self.logger.bind(tag=TAG).warning(
                    f"Rejected HK hello device={device_id}: transport must be udp"
                )
                return
            if udp_manager is None:
                self.logger.bind(tag=TAG).error("HK hello rejected: UDP manager unavailable")
                return

            old_ws = self.active_sessions.get(device_id)
            if old_ws:
                await self.cleanup_session(
                    device_id, old_ws.session_id, reason="replaced_by_new_hello"
                )

            session_id = uuid.uuid4().hex[:16].upper()
            shared_asr_queue = queue.Queue()
            output_audio = self.config.get("xiaozhi", {}).get("audio_params", {})
            output_sample_rate = int(output_audio.get("sample_rate", 24000))
            frame_duration = int(output_audio.get("frame_duration", 60))
            udp_session = udp_manager.create_hk_session(
                device_id,
                session_id,
                shared_asr_queue,
                output_sample_rate=output_sample_rate,
                frame_duration=frame_duration,
            )
            public_udp_host = os.environ["PUBLIC_UDP_HOST"].strip()
            udp_config = udp_session.hello_udp_config(
                public_udp_host, udp_manager.port
            )

            virtual_ws = VirtualWebsocket(
                device_id,
                session_id,
                self.client,
                self.loop,
                self.logger,
                hk_udp_config=udp_config,
                mqtt_downlink_topic=downlink_topic,
            )
            self.active_sessions[device_id] = virtual_ws
            self.session_meta[session_id] = {
                "device_id": device_id,
                "session_id": session_id,
                "created_at": time.time(),
                "last_activity": time.time(),
                "cleanup_started": False,
                "contract": HK_SIGNALING_CONTRACT,
            }

            from core.connection import ConnectionHandler

            handler = ConnectionHandler(
                self.config,
                self.ws_server._vad,
                self.ws_server._asr,
                self.ws_server._llm,
                self.ws_server._memory,
                self.ws_server._intent,
                self.ws_server,
            )
            handler.session_id = session_id
            handler.asr_audio_queue = shared_asr_queue
            virtual_ws.connection_handler = handler
            asyncio.create_task(
                self.run_connection_handler(
                    handler, virtual_ws, device_id, session_id
                )
            )
            # Queue the device hello only after the virtual connection exists;
            # helloHandle will reply through VirtualWebsocket, which injects the
            # UDP key/nonce and publishes to the matching old/new downlink.
            virtual_ws.put_message_threadsafe(payload)
            self.logger.bind(tag=TAG).info(
                f"[HK-MQTT] hello accepted device={device_id} session={session_id} "
                f"udp={public_udp_host}:{udp_manager.port}"
            )
        except Exception as exc:
            self.logger.bind(tag=TAG).error(
                f"HK hello failed device={device_id}: {exc}"
            )

    async def handle_signaling(self, payload):
        try:
            data = json.loads(payload)
            if data.get("type") == "call_invite":
                device_id = data.get("device_id")
                token = data.get("token", "")
                self.logger.bind(tag=TAG).info(
                    "[MQTT] call_invite received device={} format={} sample_rate={}",
                    device_id,
                    data.get("audio_format", "-"),
                    data.get("sample_rate", "-"),
                )
                
                # 1. Authentication
                if self.ws_server.auth_enable:
                    client_id = data.get("client_id", device_id)
                    try:
                        if self.ws_server.allowed_devices and device_id in self.ws_server.allowed_devices:
                            pass # Whitelisted
                        else:
                            if token.startswith("Bearer "):
                                token = token[7:]
                            if not self.ws_server.auth.verify_token(token, client_id=client_id, username=device_id):
                                raise AuthenticationError("Invalid token")
                    except Exception as e:
                        self.logger.bind(tag=TAG).warning(
                            "[MQTT] auth failed device={} reason={}",
                            device_id,
                            e,
                        )
                        self.logger.bind(tag=TAG).error(f"Auth failed for {device_id} via MQTT: {e}")
                        self.client.publish(f"devices/{device_id}/command", json.dumps({"type": "error", "message": f"Auth failed: {e}"}))
                        return

                self.logger.bind(tag=TAG).info(f"[MQTT] auth success device={device_id}")
                self.logger.bind(tag=TAG).info(f"Signaling auth success for device {device_id}")

                # 2. Reserve a session immediately so devices can receive call_accept
                # as early as possible instead of waiting behind per-device setup.
                session_id = str(uuid.uuid4().hex)[:8].upper() # 8 char ASCII
                shared_asr_queue = queue.Queue()

                # 3. Create VirtualWebsocket and register active session first.
                if device_id in self.active_sessions:
                    # Close old session
                    old_ws = self.active_sessions[device_id]
                    self.logger.bind(tag=TAG).info(
                        "[MQTT] replacing existing session device={}",
                        device_id,
                    )
                    await self.cleanup_session(
                        device_id,
                        old_ws.session_id,
                        reason="replaced",
                    )
                
                virtual_ws = VirtualWebsocket(device_id, session_id, self.client, self.loop, self.logger)
                self.active_sessions[device_id] = virtual_ws
                self.session_meta[session_id] = {
                    "device_id": device_id,
                    "session_id": session_id,
                    "created_at": time.time(),
                    "last_activity": time.time(),
                    "cleanup_started": False,
                }
                self.logger.bind(tag=TAG).info(
                    "[MQTT] session created device={} session={}",
                    device_id,
                    session_id,
                )

                # Attach UDP session before handler startup so early audio is buffered
                # instead of being dropped while the backend finishes per-device setup.
                if udp_manager:
                    udp_manager.create_session(device_id, session_id, shared_asr_queue)

                # Send call_accept on the fast path. This is the signal devices use to
                # turn green / beep, so keep it ahead of heavier handler initialization.
                accept_msg = {
                    "type": "call_accept",
                    "session_id": session_id,
                    "server_ip": os.environ.get("PUBLIC_UDP_HOST", "").strip() or get_local_ip(),
                    "udp_port": getattr(udp_manager, 'port', 5000) if udp_manager else 5000
                }
                self.client.publish(f"devices/{device_id}/command", json.dumps(accept_msg))
                self.logger.bind(tag=TAG).info(
                    "[MQTT] call_accept sent device={} session={} udp_port={}",
                    device_id,
                    session_id,
                    accept_msg["udp_port"],
                )

                # Yield once so bursts of invites can fan out call_accept messages instead
                # of monopolizing the loop with per-device setup.
                await asyncio.sleep(0)

                # Import dynamically to avoid circular dependencies, then start the full
                # connection lifecycle in background using the shared queue above.
                from core.connection import ConnectionHandler
                handler = ConnectionHandler(
                    self.config,
                    self.ws_server._vad,
                    self.ws_server._asr,
                    self.ws_server._llm,
                    self.ws_server._memory,
                    self.ws_server._intent,
                    self.ws_server
                )
                virtual_ws.connection_handler = handler
                handler.session_id = session_id
                handler.asr_audio_queue = shared_asr_queue
                self.logger.bind(tag=TAG).info(
                    "[HYBRID-LIFECYCLE] connection_handler_created device={} session={} queue_id={}",
                    device_id,
                    session_id,
                    id(shared_asr_queue),
                )

                asyncio.create_task(self.run_connection_handler(handler, virtual_ws, device_id, session_id))

        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Signaling error: {e}")

    async def cleanup_session(self, device_id, session_id, reason):
        if session_id in self.completed_cleanups:
            self.logger.bind(tag=TAG).info(
                "[MQTT] cleanup_skip device={} session={} reason={} already_cleaned=true",
                device_id,
                session_id,
                reason,
            )
            return False

        meta = self.session_meta.get(session_id)
        if meta and meta.get("cleanup_started"):
            self.logger.bind(tag=TAG).info(
                "[MQTT] cleanup_skip device={} session={} reason={} already_cleaned=false cleanup_in_progress=true",
                device_id,
                session_id,
                reason,
            )
            return False

        if meta is None and self.active_sessions.get(device_id, None) is None:
            if udp_manager and not udp_manager.get_session(session_id):
                self.completed_cleanups.add(session_id)
                self.logger.bind(tag=TAG).info(
                    "[MQTT] cleanup_skip device={} session={} reason={} already_cleaned=true",
                    device_id,
                    session_id,
                    reason,
                )
                return False

        if meta is None:
            meta = {
                "device_id": device_id,
                "session_id": session_id,
                "created_at": time.time(),
                "last_activity": time.time(),
                "cleanup_started": True,
            }
            self.session_meta[session_id] = meta
        else:
            meta["cleanup_started"] = True

        self.logger.bind(tag=TAG).info(
            "[MQTT] cleanup_started device={} session={} reason={}",
            device_id,
            session_id,
            reason,
        )

        try:
            ws = self.active_sessions.get(device_id)
            if ws and ws.session_id == session_id:
                await ws.close(reason=reason)
                del self.active_sessions[device_id]

            if udp_manager:
                udp_manager.close_session(session_id, reason=reason)

            self.session_meta.pop(session_id, None)
            self.completed_cleanups.add(session_id)

            self.logger.bind(tag=TAG).info(
                "[MQTT] cleanup_done device={} session={} reason={}",
                device_id,
                session_id,
                reason,
            )
            return True
        except Exception as e:
            if meta is not None:
                meta["cleanup_started"] = False
            self.logger.bind(tag=TAG).error(
                f"[MQTT] cleanup_failed device={device_id} session={session_id} reason={reason} error={e}"
            )
            raise

    async def run_connection_handler(self, handler, virtual_ws, device_id, session_id):
        try:
            self.logger.bind(tag=TAG).info(
                "[HYBRID-LIFECYCLE] run_connection_handler_start device={} session={} queue_id={}",
                device_id,
                session_id,
                id(handler.asr_audio_queue),
            )
            await handler.handle_connection(virtual_ws)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Connection handler crashed for {device_id}: {e}")
        finally:
            self.logger.bind(tag=TAG).info(
                "[MQTT] session handler finished device={} session={}",
                device_id,
                session_id,
            )
            await self.cleanup_session(device_id, session_id, reason="handler_done")

    async def start(self):
        import os
        mqtt_config = self.config.get("mqtt", {})
        host = os.environ.get("MQTT_HOST", mqtt_config.get("host", "127.0.0.1"))
        port = int(os.environ.get("MQTT_PORT", mqtt_config.get("port", 1883)))
        username = os.environ.get("MQTT_USERNAME", mqtt_config.get("username", ""))
        password = os.environ.get("MQTT_PASSWORD", mqtt_config.get("password", ""))

        if username and password:
            self.client.username_pw_set(username, password)

        try:
            # We use connect_async and loop_start which runs network loop in background thread
            self.client.connect_async(host, port, 60)
            self.client.loop_start()
            self.logger.bind(tag=TAG).info(f"MQTT Server starting connection to {host}:{port}")
            if is_test_inject_text_enabled():
                self.logger.bind(tag=TAG).warning(
                    "[TEST-ONLY] INJECT_TEXT hook enabled via ENABLE_TEST_INJECT_TEXT"
                )
            self._cleanup_task = self.loop.create_task(self._idle_cleanup_loop())
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Failed to start MQTT client: {e}")

    async def stop(self):
        if hasattr(self, '_cleanup_task'):
            self._cleanup_task.cancel()

        try:
            self.client.loop_stop()
        except Exception as e:
            self.logger.bind(tag=TAG).warning(f"Failed to stop MQTT loop cleanly: {e}")

        try:
            self.client.disconnect()
        except Exception as e:
            self.logger.bind(tag=TAG).warning(f"Failed to disconnect MQTT client cleanly: {e}")

    async def _idle_cleanup_loop(self):
        timeout_env = os.environ.get("HYBRID_SESSION_IDLE_TIMEOUT_SECONDS", "120")
        try:
            timeout = float(timeout_env)
        except ValueError:
            self.logger.bind(tag=TAG).warning(f"Invalid HYBRID_SESSION_IDLE_TIMEOUT_SECONDS={timeout_env}, fallback to 120")
            timeout = 120.0

        while True:
            try:
                await asyncio.sleep(10)
                await self.cleanup_idle_sessions_once(timeout=timeout)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.bind(tag=TAG).error(f"Error in idle cleanup loop: {e}")

    async def cleanup_idle_sessions_once(self, timeout=None, now=None):
        if timeout is None:
            timeout_env = os.environ.get("HYBRID_SESSION_IDLE_TIMEOUT_SECONDS", "120")
            try:
                timeout = float(timeout_env)
            except ValueError:
                timeout = 120.0
        if now is None:
            now = time.time()

        for session_id, meta in list(self.session_meta.items()):
            if meta.get("cleanup_started"):
                continue

            last_active = meta.get("last_activity", now)
            if udp_manager:
                udp_session = udp_manager.get_session(session_id)
                if udp_session:
                    last_active = max(last_active, udp_session.last_active_time)

            if now - last_active > timeout:
                device_id = meta["device_id"]
                self.logger.bind(tag=TAG).info(
                    f"[MQTT] session idle timeout device={device_id} session={session_id} idle={now - last_active:.1f}s"
                )
                await self.cleanup_session(device_id, session_id, reason="idle_timeout")
