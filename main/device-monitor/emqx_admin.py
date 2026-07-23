"""EmqxAdmin — thao tác authn/authz/credential trên EMQX 5.x qua REST API.

Dùng chung cho:
- provision_auth.py: cấu hình hàng loạt (bulk) khi setup.
- consumer.py /activate: cấp credential cho 1 thiết bị khi kích hoạt theo Serial-Number.

Không print/exit — trả giá trị + raise để caller tự xử lý.
"""
import json
import urllib.request
import urllib.error
import urllib.parse

import common

AUTHN_ID = "password_based:built_in_database"


class EmqxError(Exception):
    pass


class EmqxAdmin:
    def __init__(self, api_base=None, user=None, password=None, logger=None):
        self.api = (api_base or common.EMQX_API_BASE).rstrip("/")
        self.user = user or common.EMQX_DASHBOARD_USER
        self.password = password or common.EMQX_DASHBOARD_PASSWORD
        self.log = logger or (lambda m: None)
        self._token = None

    # ---------- low-level ----------
    def _request(self, method, path, body=None, auth=True, ok_conflict=False, silent=False):
        url = f"{self.api}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if auth and self._token:
            req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode()
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            if ok_conflict and e.code in (400, 409):
                return e.code, raw
            if not silent:
                self.log(f"  ! {method} {path} -> HTTP {e.code}: {raw}")
            return e.code, raw

    # ---------- auth ----------
    def login(self):
        if not self.password:
            raise EmqxError("EMQX dashboard password is not configured")
        status, data = self._request(
            "POST", "/login", body={"username": self.user, "password": self.password}, auth=False)
        if status != 200 or not data or "token" not in data:
            raise EmqxError(f"EMQX login failed status={status} data={data}")
        self._token = data["token"]
        self.log("[emqx] login ok")
        return self

    # ---------- setup authn/authz (idempotent) ----------
    def ensure_authenticator(self):
        status, _ = self._request("GET", f"/authentication/{AUTHN_ID}", silent=True)
        if status == 200:
            self.log("[emqx] authn built_in_database đã có")
            return
        body = {
            "mechanism": "password_based",
            "backend": "built_in_database",
            "user_id_type": "username",
            "password_hash_algorithm": {"name": "sha256", "salt_position": "suffix"},
        }
        status, _ = self._request("POST", "/authentication", body=body, ok_conflict=True)
        self.log(f"[emqx] tạo authn built_in_database -> {status}")

    def ensure_authz(self):
        status, _ = self._request("GET", "/authorization/sources/built_in_database", silent=True)
        if status != 200:
            status, _ = self._request("POST", "/authorization/sources",
                                      body={"type": "built_in_database"}, ok_conflict=True)
            self.log(f"[emqx] tạo authz built_in_database -> {status}")
        # Xóa source 'file' mặc định ({allow, all}) làm vô hiệu ACL
        s, _ = self._request("DELETE", "/authorization/sources/file", silent=True)
        if s in (200, 204):
            self.log("[emqx] đã xóa authz source 'file' mặc định")
        self._request("PUT", "/authorization/settings",
                      body={"no_match": "deny", "deny_action": "ignore", "cache": {"enable": True}})

    # ---------- user + ACL ----------
    def upsert_user(self, username, password):
        status, _ = self._request(
            "POST", f"/authentication/{AUTHN_ID}/users",
            body={"user_id": username, "password": password}, ok_conflict=True)
        if status in (400, 409):  # đã tồn tại -> đổi mật khẩu
            self._request("PUT", f"/authentication/{AUTHN_ID}/users/{username}",
                          body={"password": password})
            status = 200
        return status

    def set_device_acl(self, username, topics_prefix=None):
        """Set canonical ACL plus the minimum current-HK compatibility rules."""
        prefix = topics_prefix or f"devices/{username}/#"
        rules = [{"permission": "allow", "action": "all", "topic": prefix}]
        if common.ENABLE_HK_LEGACY_BRIDGE:
            rules.extend([
                {
                    "permission": "allow",
                    "action": "publish",
                    "topic": username,
                },
                {
                    "permission": "allow",
                    "action": "publish",
                    "topic": common.LEGACY_MONITOR_TOPIC,
                },
                {
                    "permission": "allow",
                    "action": "subscribe",
                    "topic": common.legacy_command_topic(username),
                },
                {
                    "permission": "allow",
                    "action": "publish",
                    "topic": common.hk_device_publish_topic(username),
                },
                {
                    "permission": "allow",
                    "action": "subscribe",
                    "topic": common.hk_device_subscribe_topic(username),
                },
            ])
        self._request("DELETE",
                      f"/authorization/sources/built_in_database/rules/users/{username}", silent=True)
        status, _ = self._request(
            "POST", "/authorization/sources/built_in_database/rules/users",
            body=[{"username": username, "rules": rules}],
            ok_conflict=True)
        return status

    def set_hk_client_acl(self, clientid):
        """Restrict an HK firmware MQTT client ID to its own signaling topics."""
        rules = [
            {
                "permission": "allow",
                "action": "publish",
                "topic": common.hk_device_publish_topic(clientid),
            },
            {
                "permission": "allow",
                "action": "subscribe",
                "topic": common.hk_device_subscribe_topic(clientid),
            },
        ]
        quoted_clientid = urllib.parse.quote(str(clientid), safe="")
        self._request(
            "DELETE",
            "/authorization/sources/built_in_database/rules/clients/"
            + quoted_clientid,
            silent=True,
        )
        status, _ = self._request(
            "POST",
            "/authorization/sources/built_in_database/rules/clients",
            body=[{"clientid": clientid, "rules": rules}],
            ok_conflict=True,
        )
        return status

    def set_full_acl(self, username, topic="devices/#"):
        rules = [{"permission": "allow", "action": "all", "topic": topic}]
        if common.ENABLE_HK_LEGACY_BRIDGE:
            rules.extend([
                {
                    "permission": "allow",
                    "action": "subscribe",
                    "topic": "+",
                },
                {
                    "permission": "allow",
                    "action": "subscribe",
                    "topic": common.LEGACY_MONITOR_TOPIC,
                },
                {
                    "permission": "allow",
                    "action": "publish",
                    "topic": "+/MONITOR",
                },
                {
                    "permission": "allow",
                    "action": "subscribe",
                    "topic": common.SUB_ALL_HK_UPLINK,
                },
                {
                    "permission": "allow",
                    "action": "publish",
                    "topic": f"+/{common.HK_MQTT_DOWNLINK_SUFFIX}",
                },
            ])
        self._request("DELETE",
                      f"/authorization/sources/built_in_database/rules/users/{username}", silent=True)
        status, _ = self._request(
            "POST", "/authorization/sources/built_in_database/rules/users",
            body=[{"username": username, "rules": rules}],
            ok_conflict=True)
        return status

    def delete_user(self, username):
        self._request("DELETE", f"/authentication/{AUTHN_ID}/users/{username}", silent=True)
        self._request("DELETE",
                      f"/authorization/sources/built_in_database/rules/users/{username}", silent=True)

    def provision_device(self, username, password):
        """Tạo/cập nhật credential + ACL cho 1 thiết bị (dùng khi activate)."""
        self.upsert_user(username, password)
        self.set_device_acl(username)
