"""Provision authentication + authorization (ACL) trên EMQX 5.x — IDEMPOTENT.

Thiết lập 1 lần khi setup:
- Authenticator password_based + built_in_database, authz built_in_database (no_match=deny).
- Tài khoản backend (consumer): full quyền devices/#.
- (tùy chọn) tài khoản demo theo Serial-Number để test nhanh.

Trong production, credential từng thiết bị được cấp lúc KÍCH HOẠT (consumer /activate),
không cần liệt kê ở đây. Script này chỉ lo phần hạ tầng + backend + demo.

Chạy:  python provision_auth.py [serial ...]
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import common
from emqx_admin import EmqxAdmin, EmqxError

# Serial demo để test nhanh (production: cấp lúc activate).
DEMO_DEVICES = {
    "HKHT2606010011": "dev01_secret_2024",
}


def main():
    serials = sys.argv[1:] or list(DEMO_DEVICES.keys())
    log = lambda m: print(m, flush=True)
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

    # Demo theo Serial-Number
    for serial in serials:
        password = DEMO_DEVICES.get(serial, f"{serial}_secret")
        emqx.provision_device(serial, password)
        print(f"  [user] {serial} (device, devices/{serial}/#)")

    print("PROVISION DONE")


if __name__ == "__main__":
    main()
