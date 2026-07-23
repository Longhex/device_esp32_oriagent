"""Provision authentication + authorization (ACL) trên EMQX 5.x — IDEMPOTENT.

Thiết lập 1 lần khi setup:
- Authenticator password_based + built_in_database, authz built_in_database (no_match=deny).
- Tài khoản backend (consumer): full quyền devices/#.
- (tùy chọn) tài khoản demo theo Serial-Number để test nhanh.

Trong production, credential từng thiết bị được cấp lúc KÍCH HOẠT (consumer /activate),
không cần liệt kê ở đây. Script này chỉ lo phần hạ tầng + backend + demo.

Chạy:  python provision_auth.py [serial ...]
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import common
from emqx_admin import EmqxAdmin, EmqxError

def main():
    serials = sys.argv[1:]
    log = lambda m: print(m, flush=True)
    try:
        common.validate_runtime_secrets(require_dashboard=True)
    except RuntimeError as exc:
        print(f"CONFIG ERROR: {exc}")
        sys.exit(1)
    try:
        emqx = EmqxAdmin(logger=log).login()
    except EmqxError as e:
        print(f"LOGIN FAILED: {e}")
        sys.exit(1)

    emqx.ensure_authenticator()
    emqx.ensure_authz()

    # Backend / consumer: full devices/#
    emqx.upsert_user(common.BACKEND_USERNAME, common.BACKEND_PASSWORD)
    emqx.set_full_acl(common.BACKEND_USERNAME, "devices/#")
    print(f"  [user] {common.BACKEND_USERNAME} (backend, full devices/#)")

    if common.MQTT_SHARED_TEST_SERIALS:
        try:
            username, password = common.shared_test_credentials(
                next(iter(common.MQTT_SHARED_TEST_SERIALS))
            )
        except RuntimeError as exc:
            print(f"CONFIG ERROR: {exc}")
            sys.exit(1)
        emqx.upsert_user(username, password)
        for client_id in common.MQTT_SHARED_TEST_SERIALS:
            emqx.set_hk_client_acl(client_id)
            print(
                f"  [shared-test-client] {client_id} "
                f"(user={username}, client-id scoped HK ACL)"
            )

    # Demo theo Serial-Number
    demo_password = os.getenv("PROVISION_DEMO_PASSWORD", "")
    if serials and not demo_password:
        print("CONFIG ERROR: PROVISION_DEMO_PASSWORD is required when provisioning demo serials")
        sys.exit(1)
    for serial in serials:
        emqx.provision_device(serial, demo_password)
        print(f"  [user] {serial} (device, devices/{serial}/#)")

    print("PROVISION DONE")


if __name__ == "__main__":
    main()
