import json
import time
import os
import re
import glob
import ipaddress
import uuid
from typing import Dict, List, Tuple
from urllib.parse import urlparse
from aiohttp import ClientSession, ClientTimeout, web

from core.auth import AuthManager
from core.mqtt_topics import (
    hk_device_publish_topic,
    hk_device_subscribe_topic,
)
from core.utils.util import (
    get_local_ip,
    get_vision_url,
    protocol_payload_json_for_log,
    sanitize_headers,
)
from core.api.base_handler import BaseHandler

TAG = __name__


MAC_IDENTITY_RE = re.compile(
    r"^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$"
)


def is_truthy_env(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_ota_identity(value: str) -> str:
    """Canonicalize MAC-shaped identities without changing real serials."""
    identity = str(value or "").strip()
    if MAC_IDENTITY_RE.fullmatch(identity):
        return identity.replace("-", ":").upper()
    return identity


def resolve_ota_serial_number(headers, device_id: str) -> tuple[str, bool]:
    """Resolve the OTA identity, falling back to the device MAC when needed.

    Returns ``(identity, used_mac_fallback)``.  ``aiohttp`` request headers are
    case-insensitive, so the lower-case lookup also accepts ``Serial-Number``.
    """
    serial_number = normalize_ota_identity(
        headers.get("serial-number", "")
    )
    if serial_number:
        return serial_number, False
    return normalize_ota_identity(device_id), True


def build_firmware_mqtt_config(
    mqtt_config: dict, topic_identity: str = ""
) -> dict:
    """Return the OTA MQTT contract, preserving provisioner topic authority.

    Device-monitor provisions EMQX ACLs and returns the corresponding topics.
    Those topics must be returned verbatim to firmware.  A locally generated
    topic is only a fallback for provisioners that do not return both topics.
    """
    required = ("endpoint", "client_id", "username", "password")
    if not isinstance(mqtt_config, dict) or not all(
        key in mqtt_config for key in required
    ):
        raise ValueError("Incomplete management MQTT config")

    result = {key: mqtt_config[key] for key in required}
    publish_topic = str(mqtt_config.get("publish_topic") or "").strip()
    subscribe_topic = str(mqtt_config.get("subscribe_topic") or "").strip()
    if publish_topic and subscribe_topic:
        result["publish_topic"] = publish_topic
        result["subscribe_topic"] = subscribe_topic
        return result

    topic_identity = str(topic_identity or result["client_id"]).strip()
    result["publish_topic"] = hk_device_publish_topic(topic_identity)
    result["subscribe_topic"] = hk_device_subscribe_topic(topic_identity)
    return result


def _is_truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_private_hostname(hostname: str) -> bool:
    if not hostname:
        return True
    if hostname.lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def _safe_basename(filename: str) -> str:
    # Prevent directory traversal
    return os.path.basename(filename)


def _parse_version(ver: str) -> Tuple[int, ...]:
    # conservative parser: split by non-digit, keep numeric parts
    parts = re.findall(r"\d+", ver)
    return tuple(int(p) for p in parts) if parts else (0,)


def _is_higher_version(a: str, b: str) -> bool:
    """Return True if version string a > b (semver-like numeric compare)."""
    ta = _parse_version(a)
    tb = _parse_version(b)
    # compare tuple lexicographically, but allow different lengths
    maxlen = max(len(ta), len(tb))
    for i in range(maxlen):
        ai = ta[i] if i < len(ta) else 0
        bi = tb[i] if i < len(tb) else 0
        if ai > bi:
            return True
        if ai < bi:
            return False
    return False


class OTAHandler(BaseHandler):
    def __init__(self, config: dict):
        super().__init__(config)
        auth_config = config["server"].get("auth", {})
        self.auth_enable = auth_config.get("enabled", False)
        # 设备白名单
        self.allowed_devices = set(auth_config.get("allowed_devices", []))
        secret_key = config["server"]["auth_key"]
        expire_seconds = auth_config.get("expire_seconds")
        self.auth = AuthManager(secret_key=secret_key, expire_seconds=expire_seconds)

        # firmware storage
        self.bin_dir = os.path.join(os.getcwd(), "data", "bin")
        # cache structure: { 'updated_at': timestamp, 'ttl': seconds, 'files_by_model': { model: [(version, filename), ...] } }
        self._bin_cache: Dict = {
            "updated_at": 0,
            "ttl": config.get("firmware_cache_ttl", 30),
            "files_by_model": {},
        }

    def _refresh_bin_cache_if_needed(self):
        now = int(time.time())
        ttl = int(self._bin_cache.get("ttl", 30))
        if now - int(
            self._bin_cache.get("updated_at", 0)
        ) < ttl and self._bin_cache.get("files_by_model"):
            return

        files_by_model: Dict[str, List[Tuple[str, str]]] = {}
        try:
            if not os.path.isdir(self.bin_dir):
                os.makedirs(self.bin_dir, exist_ok=True)

            # match files like model_1.2.3.bin (allow dots, dashes, underscores in model and version)
            pattern = os.path.join(self.bin_dir, "*.bin")
            for path in glob.glob(pattern):
                fname = os.path.basename(path)
                # filename format: {model}_{version}.bin
                m = re.match(r"^(.+?)_([0-9][A-Za-z0-9\.\-_]*)\.bin$", fname)
                if not m:
                    # skip files not conforming to naming rule
                    continue
                model = m.group(1)
                version = m.group(2)
                files_by_model.setdefault(model, []).append((version, fname))

            # sort versions for each model descending
            for model, items in files_by_model.items():
                items.sort(key=lambda it: _parse_version(it[0]), reverse=True)

            self._bin_cache["files_by_model"] = files_by_model
            self._bin_cache["updated_at"] = now
            self.logger.bind(tag=TAG).info(
                f"Firmware cache refreshed: {len(files_by_model)} models"
            )
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Failed to refresh firmware cache: {e}")
            # keep previous cache if any

    def _get_websocket_url(self, local_ip: str, port: int, request: web.Request = None) -> str:
        """获取websocket地址，支持通过请求头动态识别

        Args:
            local_ip: 本地IP地址
            port: 端口号
            request: 当前的HTTP请求对象

        Returns:
            str: websocket地址
        """
        server_config = self.config["server"]
        public_url = os.environ.get("PUBLIC_WEBSOCKET_URL", "").strip()
        public_domain = os.environ.get("PUBLIC_DOMAIN", "").strip()
        configured_url = str(server_config.get("websocket", "") or "").strip()

        if public_url:
            candidate = public_url
        elif public_domain:
            candidate = f"wss://{public_domain}/xiaozhi/v1/"
        elif configured_url and "你的" not in configured_url:
            candidate = configured_url
        elif request is not None:
            trust_proxy = _is_truthy(os.environ.get("TRUST_PROXY_HEADERS", "false"))
            forwarded_proto = request.headers.get("X-Forwarded-Proto", "") if trust_proxy else ""
            forwarded_host = request.headers.get("X-Forwarded-Host", "") if trust_proxy else ""
            host = forwarded_host or request.headers.get("Host", "") or request.host
            scheme = "wss" if forwarded_proto == "https" or request.scheme == "https" else "ws"
            candidate = f"{scheme}://{host}/xiaozhi/v1/"
        else:
            candidate = f"ws://{local_ip}:{port}/xiaozhi/v1/"

        parsed = urlparse(candidate)
        if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
            raise ValueError(f"Invalid public WebSocket URL: {candidate}")

        app_env = os.environ.get("APP_ENV", "development").strip().lower()
        if app_env == "production":
            if parsed.scheme != "wss":
                raise ValueError("Production WebSocket URL must use wss://")
            if _is_private_hostname(parsed.hostname):
                raise ValueError("Production WebSocket URL must not use a private host")

        if parsed.path.rstrip("/") != "/xiaozhi/v1":
            raise ValueError("WebSocket URL path must be /xiaozhi/v1/")
        return candidate.rstrip("/") + "/"

    def _get_public_http_origin(self, request: web.Request) -> str:
        trust_proxy = _is_truthy(os.environ.get("TRUST_PROXY_HEADERS", "false"))
        forwarded_proto = request.headers.get("X-Forwarded-Proto", "") if trust_proxy else ""
        forwarded_host = request.headers.get("X-Forwarded-Host", "") if trust_proxy else ""
        scheme = forwarded_proto or request.scheme
        host = forwarded_host or request.headers.get("Host", "") or request.host
        if scheme not in {"http", "https"}:
            raise ValueError(f"Invalid public HTTP scheme: {scheme}")
        if os.environ.get("APP_ENV", "development").strip().lower() == "production" and scheme != "https":
            raise ValueError("Production OTA download URL must use https://")
        return f"{scheme}://{host}"

    async def _get_management_mqtt_config(
        self, serial_number: str, mac: str, request_id: str = "-"
    ):
        """Provision/fetch management MQTT without affecting voice OTA."""
        # DEVICE_PROVISIONER_API is intentionally service-agnostic: today it
        # points at device-monitor, and can later point at a provisioning
        # service without changing the OTA contract.
        api_base = (
            os.environ.get("DEVICE_PROVISIONER_API", "").strip()
            or os.environ.get("DEVICE_MONITOR_API", "").strip()
        ).rstrip("/")
        if not api_base or not serial_number:
            return None
        log_prefix = f"[OTA-HANDSHAKE][request_id={request_id}]"
        activate_payload = {"serial": serial_number, "mac": mac}
        self.logger.bind(tag=TAG).info(
            f"{log_prefix} PROVISION_REQUEST "
            f"target={api_base}/activate payload="
            f"{protocol_payload_json_for_log(activate_payload)}"
        )
        try:
            async with ClientSession(timeout=ClientTimeout(total=5)) as session:
                async with session.post(
                    f"{api_base}/activate",
                    json=activate_payload,
                ) as response:
                    try:
                        payload = await response.json()
                    except Exception:
                        payload = None
                    status = response.status

                # Transitional opt-in: make an undeclared identity available
                # for the existing six-digit web binding flow. It is disabled
                # by default because it weakens the declared-serial gate.
                if status == 403 and is_truthy_env(
                    os.environ.get("AUTO_DECLARE_OTA_SERIAL", "false")
                ):
                    declare_payload = {"serial": serial_number, "batch": "ota-auto"}
                    self.logger.bind(tag=TAG).warning(
                        f"{log_prefix} AUTO_DECLARE_REQUEST target={api_base}/serials "
                        f"payload={protocol_payload_json_for_log(declare_payload)}"
                    )
                    async with session.post(
                        f"{api_base}/serials", json=declare_payload
                    ) as declare_response:
                        try:
                            declare_result = await declare_response.json()
                        except Exception:
                            declare_result = None
                        declare_status = declare_response.status
                    self.logger.bind(tag=TAG).info(
                        f"{log_prefix} AUTO_DECLARE_RESPONSE status={declare_status} "
                        f"payload={protocol_payload_json_for_log(declare_result) if declare_result is not None else '<non-json-response>'}"
                    )
                    if declare_status in {200, 201}:
                        self.logger.bind(tag=TAG).info(
                            f"{log_prefix} PROVISION_RETRY serial={serial_number}"
                        )
                        async with session.post(
                            f"{api_base}/activate", json=activate_payload
                        ) as retry_response:
                            try:
                                payload = await retry_response.json()
                            except Exception:
                                payload = None
                            status = retry_response.status
                response_summary = (
                    protocol_payload_json_for_log(payload)
                    if payload is not None
                    else "<non-json-response>"
                )
                self.logger.bind(tag=TAG).info(
                    f"{log_prefix} PROVISION_RESPONSE status={status} "
                    f"payload={response_summary}"
                )
                if status != 200:
                    self.logger.bind(tag=TAG).warning(
                        f"{log_prefix} Management MQTT provisioning skipped "
                        f"serial={serial_number} status={status}"
                    )
                    return None
                mqtt_config = payload.get("mqtt") if isinstance(payload, dict) else None
                if not isinstance(mqtt_config, dict):
                    return None
                try:
                    return build_firmware_mqtt_config(
                        mqtt_config, topic_identity=serial_number
                    )
                except ValueError:
                    self.logger.bind(tag=TAG).warning(
                        f"{log_prefix} Incomplete management MQTT config "
                        f"serial={serial_number}"
                    )
                    return None
        except Exception as exc:
            self.logger.bind(tag=TAG).warning(
                f"{log_prefix} Management MQTT provisioning unavailable "
                f"serial={serial_number}: {exc}"
            )
            return None

    async def handle_post(self, request):
        """处理 OTA POST 请求
        
        This handler will:
        - read device id/client id (as before)
        - attempt to determine device model and current firmware version (prefer headers, fallback to body)
        - check data/bin for newer firmware for that model
        - if found a newer firmware, set firmware.url to the download endpoint
        """
        request_id = (
            str(request.headers.get("X-Request-Id", "") or "").strip()[:64]
            or uuid.uuid4().hex[:12]
        )
        log_prefix = f"[OTA-HANDSHAKE][request_id={request_id}]"
        response = None
        try:
            data = await request.text()
            safe_headers = sanitize_headers(dict(request.headers))
            peer = request.remote or safe_headers.get("X-Real-IP", "-")
            self.logger.bind(tag=TAG).info(
                f"{log_prefix} RX_START method={request.method} "
                f"path={request.path} peer={peer}"
            )
            self.logger.bind(tag=TAG).info(
                f"{log_prefix} RX_HEADERS "
                f"payload={protocol_payload_json_for_log(safe_headers)}"
            )

            try:
                data_json = json.loads(data) if data else {}
            except Exception:
                data_json = {}
                self.logger.bind(tag=TAG).warning(
                    f"{log_prefix} RX_PAYLOAD invalid_json=true bytes={len(data)}"
                )
            else:
                self.logger.bind(tag=TAG).info(
                    f"{log_prefix} RX_PAYLOAD "
                    f"payload={protocol_payload_json_for_log(data_json)}"
                )

            device_id = request.headers.get("device-id", "")
            if device_id:
                self.logger.bind(tag=TAG).info(
                    f"{log_prefix} DEVICE_ID value={device_id}"
                )
            else:
                raise Exception("OTA request Device ID is empty")

            client_id = request.headers.get("client-id", "")
            if client_id:
                self.logger.bind(tag=TAG).info(
                    f"{log_prefix} CLIENT_ID value={client_id}"
                )
            else:
                raise Exception("OTA request ClientID is empty")

            serial_number, used_mac_fallback = resolve_ota_serial_number(
                request.headers, device_id
            )
            if used_mac_fallback:
                self.logger.bind(tag=TAG).warning(
                    f"{log_prefix} OTA request missing Serial-Number; "
                    f"using Device-Id as fallback identity={serial_number}"
                )

            server_config = self.config["server"]
            # Distinguish ports:
            # - websocket_port is used to construct websocket URL (server["port"])
            # - http_port is used to construct OTA download URLs (server["http_port"])
            websocket_port = int(server_config.get("port", 8000))
            http_port = int(server_config.get("http_port", 8003))
            local_ip = get_local_ip()

            # Determine device model (prefer headers)
            device_model = ""
            # header candidates
            for h in ("device-model", "device_model", "model"):
                if h in request.headers:
                    device_model = request.headers.get(h, "").strip()
                    break
            # body fallback
            if not device_model:
                try:
                    if "board" in data_json and isinstance(data_json["board"], dict):
                        device_model = data_json["board"].get("type", "")
                    elif "model" in data_json:
                        device_model = data_json.get("model", "")
                except Exception:
                    device_model = ""
            if not device_model:
                device_model = "default"

            # Determine device current version (prefer headers)
            device_version = ""
            for h in (
                "device-version",
                "device_version",
                "firmware-version",
                "app-version",
                "application-version",
            ):
                if h in request.headers:
                    device_version = request.headers.get(h, "").strip()
                    break
            if not device_version:
                try:
                    device_version = data_json.get("application", {}).get("version", "")
                except Exception:
                    device_version = ""
            if not device_version:
                device_version = "0.0.0"

            self.logger.bind(tag=TAG).info(
                f"{log_prefix} IDENTITY payload="
                f"{protocol_payload_json_for_log({'serial': serial_number, 'identity_source': 'device-id-fallback' if used_mac_fallback else 'serial-number-header', 'device_id': device_id, 'client_id': client_id, 'device_model': device_model, 'firmware_version': device_version})}"
            )

            return_json = {
                "server_time": {
                    "timestamp": int(round(time.time() * 1000)),
                    "timezone_offset": server_config.get("timezone_offset", 8) * 60,
                },
                "firmware": {
                    "version": device_version,
                    "url": "",
                },
            }

            mqtt_config = await self._get_management_mqtt_config(
                serial_number, device_id, request_id=request_id
            )
            if mqtt_config:
                return_json["mqtt"] = mqtt_config
                self.logger.bind(tag=TAG).info(
                    f"{log_prefix} MQTT_CONFIG_READY serial={serial_number} "
                    f"payload={protocol_payload_json_for_log(mqtt_config)}"
                )

            transport_mode = os.environ.get(
                "TRANSPORT_MODE", "websocket_legacy"
            ).strip().lower()
            if transport_mode == "mqtt_udp_hk":
                if not mqtt_config:
                    raise ValueError(
                        "MQTT-only voice requires successful device identity provisioning"
                    )
                return_json["transport"] = {
                    "type": "mqtt_udp",
                    "version": 3,
                }
                self.logger.bind(tag=TAG).info(
                    f"{log_prefix} TRANSPORT_SELECTED type=mqtt_udp version=3 "
                    f"serial={serial_number}"
                )
            else:
                token = ""
                if self.auth_enable:
                    if self.allowed_devices:
                        if device_id not in self.allowed_devices:
                            token = self.auth.generate_token(client_id, device_id)
                    else:
                        token = self.auth.generate_token(client_id, device_id)
                return_json["websocket"] = {
                    "url": self._get_websocket_url(local_ip, websocket_port, request),
                    "token": token,
                    "version": int(server_config.get("websocket_protocol_version", 1)),
                }
                self.logger.bind(tag=TAG).info(
                    f"Sending WebSocket voice config device={device_id} "
                    f"url={return_json['websocket']['url']}"
                )

            # Now check firmware files for updates
            try:
                self._refresh_bin_cache_if_needed()
                files_by_model = self._bin_cache.get("files_by_model", {})
                candidates = files_by_model.get(device_model, [])

                self.logger.bind(tag=TAG).info(
                    f"Checking firmware for model {device_model}, found {len(candidates)} candidates"
                )

                chosen_url = ""
                chosen_version = device_version

                # candidates are sorted descending by version
                for ver, fname in candidates:
                    if _is_higher_version(ver, device_version):
                        # build download url (only allow download via our download endpoint)
                        chosen_version = ver
                        public_origin = self._get_public_http_origin(request)
                        chosen_url = f"{public_origin}/xiaozhi/ota/download/{fname}"
                        break

                if chosen_url:
                    return_json["firmware"]["version"] = chosen_version
                    return_json["firmware"]["url"] = chosen_url
                    self.logger.bind(tag=TAG).info(
                        f"Sending firmware {chosen_version} to device {device_id} [If URL prefix is wrong, check server.vision_explain in config]-> {chosen_url} "
                    )
                else:
                    self.logger.bind(tag=TAG).info(
                        f"Device {device_id} firmware is already up-to-date: {device_version}"
                    )

            except Exception as e:
                self.logger.bind(tag=TAG).error(f"Error checking firmware version: {e}")

            response = web.Response(
                text=json.dumps(return_json, separators=(",", ":")),
                content_type="application/json",
            )
            self.logger.bind(tag=TAG).info(
                f"{log_prefix} TX_RESPONSE status={response.status} "
                f"payload={protocol_payload_json_for_log(return_json)}"
            )
        except Exception as e:
            self.logger.bind(tag=TAG).error(
                f"{log_prefix} FAILED error_type={type(e).__name__} error={e}"
            )
            return_json = {"success": False, "message": "request error."}
            response = web.Response(
                text=json.dumps(return_json, separators=(",", ":")),
                content_type="application/json",
            )
            self.logger.bind(tag=TAG).info(
                f"{log_prefix} TX_RESPONSE status={response.status} outcome=error "
                f"payload={protocol_payload_json_for_log(return_json)}"
            )
        finally:
            response.headers["X-Request-Id"] = request_id
            self._add_cors_headers(response)
            return response

    async def handle_get(self, request):
        """处理 OTA GET 请求"""
        try:
            if os.environ.get("TRANSPORT_MODE", "").strip().lower() == "mqtt_udp_hk":
                response = web.Response(
                    text="OTA interface is running normally. Device voice transport is MQTT + UDP AES-CTR.",
                    content_type="text/plain",
                )
                return response
            server_config = self.config["server"]
            local_ip = get_local_ip()
            # use websocket port for websocket URL
            websocket_port = int(server_config.get("port", 8000))
            # pass request for smart detection
            websocket_url = self._get_websocket_url(local_ip, websocket_port, request)
            message = f"OTA interface is running normally. Websocket address sent to device is: {websocket_url}"
            response = web.Response(text=message, content_type="text/plain")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"OTA GET request exception: {e}")
            response = web.Response(text="OTA interface exception", content_type="text/plain")
        finally:
            self._add_cors_headers(response)
            return response

    async def handle_download(self, request):
        """
        下载固件接口
        URL: /xiaozhi/ota/download/{filename}
        - 只允许下载 data/bin 目录下的 .bin 文件
        - filename 必须是 basename 且匹配安全的模式
        """
        try:
            fname = request.match_info.get("filename", "")
            if not fname:
                raise web.HTTPBadRequest(text="filename required")

            # sanitize
            fname = _safe_basename(fname)
            # pattern: allow letters, numbers, dot, underscore, dash
            if not re.match(r"^[A-Za-z0-9\.\-_]+\.bin$", fname):
                raise web.HTTPBadRequest(text="invalid filename")

            file_path = os.path.join(self.bin_dir, fname)
            # ensure realpath is under bin_dir
            file_real = os.path.realpath(file_path)
            bin_dir_real = os.path.realpath(self.bin_dir)
            if (
                not file_real.startswith(bin_dir_real + os.sep)
                and file_real != bin_dir_real
            ):
                raise web.HTTPForbidden(text="forbidden")

            if not os.path.isfile(file_real):
                raise web.HTTPNotFound(text="file not found")

            # use FileResponse to stream file
            resp = web.FileResponse(path=file_real)
        except web.HTTPError as e:
            resp = e
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Firmware download exception: {e}")
            resp = web.Response(text="download error", status=500)
        finally:
            try:
                self._add_cors_headers(resp)
            except Exception:
                pass
            return resp
