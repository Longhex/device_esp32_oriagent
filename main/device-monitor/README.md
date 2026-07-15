# device-monitor — mặt phẳng quản lý/giám sát thiết bị (MQTT/EMQX)

Service độc lập phục vụ **giám sát, điều khiển, quản lý thiết bị** qua MQTT (broker EMQX).
**Tách biệt hoàn toàn** với luồng AI audio xiaozhi (WebSocket) — không đụng tới code audio.
Cũng KHÁC với `xiaozhi-mqtt-gateway` (kênh truyền audio MQTT+UDP).

## Kiến trúc

```
ESP32 (MQTT client)  ──►  EMQX broker  ──►  consumer.py  ──►  HTTP API  ──►  web/app
        ▲                  (auth+ACL)        (registry)
        └──────────────────  command  ◄──────────────────────────────────────┘
```

## Quy ước topic

| Topic | Hướng | Mô tả |
|---|---|---|
| `devices/{client}/status` | device → server | online/offline, **retained + LWT** |
| `devices/{client}/telemetry` | device → server | pin, RSSI, heap, uptime, fw_ver |
| `devices/{client}/command` | server → device | reboot / set_config / ota ... |
| `devices/{client}/command/ack` | device → server | kết quả thực thi lệnh |

`{client}` = **Serial-Number** (vd `HKHT2606010011`) — định danh thiết bị, khai báo
trên server trước khi kích hoạt; dùng verbatim làm topic + MQTT username để thống nhất
1 khóa xuyên suốt DB ↔ MQTT ↔ web.

## Auth & ACL (EMQX 5.x, built-in DB)

- Authentication: `password_based:built_in_database` (username/password, sha256).
- Authorization: source `built_in_database`, `no_match=deny`, **đã xóa source `file` mặc định** (vì nó có luật `{allow, all}` làm vô hiệu ACL).
- Backend (`oriagent-monitor`): canonical `devices/#`; khi bật HK bridge còn subscribe bare `+` và publish `+/MONITOR` cho voice signaling.
- Mỗi thiết bị: canonical `devices/{client}/#`; HK bridge chỉ bổ sung publish `{client}`/`HAKAT_AI_MONITOR_ALL` và subscribe `{client}/MONITOR`.

`provision_auth.py` là **idempotent** — chạy lại an toàn. Đây là nguyên mẫu cho việc
manager-api sẽ cấp credential khi đăng ký thiết bị (phát qua OTA).

## Lưu trữ trạng thái

`store.py` (DeviceStore): luôn giữ in-memory (đọc nhanh cho HTTP) + **write-through Redis**
nếu có `REDIS_HOST` → state bền qua restart & chia sẻ cho manager-api/web. Không set
`REDIS_HOST` thì tự fallback in-memory (opt-in, tránh đấu nhầm redis lạ khi chạy tay).

Key Redis: `device-monitor:device:{client}` (JSON), `device-monitor:devices` (SET index).

## Chạy

### A) Trong stack (production) — đã tích hợp `docker-compose.prod.yml`

```bash
cd deploy
# 1) provision auth EMQX trước (backend user phải tồn tại) — chạy 1 lần
python ../main/device-monitor/provision_auth.py
# 2) build + chạy (consumer trỏ thẳng EMQX + Redis nội bộ stack)
docker compose -f docker-compose.prod.yml up -d --build xiaozhi-redis device-monitor
docker compose -f docker-compose.prod.yml logs device-monitor   # "Redis OK" + "connected"
```

Consumer chạy trong network `backend`: `EMQX_HOST=emqx`, `REDIS_HOST=xiaozhi-esp32-server-redis`.
HTTP API publish ở `127.0.0.1:8090` (đổi qua `MONITOR_HTTP_BIND/PORT`).

### B) Chạy tay (dev/test trên host)

```bash
pip install -r requirements.txt
python provision_auth.py [client_id ...]      # cấu hình auth/ACL
python consumer.py                            # HTTP API :8090 (in-memory, không Redis)
python sim_device.py HKHT2606010011 dev01_secret_2024 5   # giả lập ESP32 (Serial-Number)
```

### HTTP API (cho web/app đấu nối)

**Giám sát & điều khiển:**

| Method | Path | Mô tả |
|---|---|---|
| GET | `/healthz` | health check |
| GET | `/devices` | danh sách + trạng thái tất cả thiết bị |
| GET | `/devices/{serial}` | chi tiết 1 thiết bị |
| POST | `/devices/{serial}/command` | gửi lệnh `{"action","params"}` → trả `command_id` |

**Kích hoạt theo Serial-Number:**

| Method | Path | Mô tả |
|---|---|---|
| POST | `/serials` | khai báo serial `{"serial","batch?"}` (status=declared) |
| GET | `/serials` | danh sách serial (ẩn password) |
| GET | `/serials/{serial}` | chi tiết 1 serial |
| POST | `/activate` | `{"serial","mac?"}` → nếu đã khai báo: cấp MQTT credential + ACL, trả `{mqtt:{endpoint,client_id,username,password,topics}}`. Serial chưa khai báo → 403 |
| DELETE | `/serials/{serial}` | gỡ thiết bị (unbind): xóa credential EMQX + clear retained + xóa Redis |

Luồng: admin `POST /serials` (khai báo trước) → thiết bị `POST /activate` (lúc boot) →
nhận credential → kết nối EMQX → được giám sát. Chỉ serial đã khai báo mới activate được.
`provision_auth.py` chỉ lo hạ tầng + backend user; credential thiết bị cấp lúc `/activate`.

## Biến môi trường

`EMQX_HOST`, `EMQX_MQTT_PORT`, `EMQX_API_BASE`, `EMQX_DASHBOARD_USER/PASSWORD`,
`MQTT_BACKEND_USER/PASS`, `MONITOR_HTTP_PORT`, `MQTT_PUBLIC_ENDPOINT` (host:port trả cho
thiết bị khi activate). Xem `common.py`.

## Module

| File | Vai trò |
|---|---|
| `common.py` | cấu hình env + topic helpers |
| `redis_client.py` | khởi tạo Redis dùng chung (opt-in qua REDIS_HOST) |
| `store.py` | `DeviceStore` — trạng thái thiết bị (in-memory + Redis) |
| `serial_store.py` | `SerialStore` — kho serial (declare/activate/list/remove) |
| `emqx_admin.py` | `EmqxAdmin` — authn/authz/credential qua EMQX REST API |
| `consumer.py` | MQTT consumer + HTTP API |
| `provision_auth.py` | setup hạ tầng EMQX + backend user (1 lần) |
| `sim_device.py` | ESP32 giả lập (test) |

## Kiểm thử

```bash
# Test E2E giám sát (tự bật/tắt consumer + device, tự dọn). EXIT 0 = all PASS.
python tests/e2e_test.py

# Test E2E kích hoạt theo Serial (cần stack container đang chạy). 8/8 PASS.
python tests/activation_e2e_test.py

# Test lẻ:
python tests/smoke_test.py     # pub/sub cơ bản (chạy TRƯỚC khi bật auth)
python tests/acl_test.py       # cô lập per-device (OWN granted, OTHER denied=128)
```

Kết quả E2E đã verify (device giả lập → EMQX → consumer → HTTP API) — **7/7 PASS**:
- ✅ Auth enforced (ẩn danh bị từ chối)
- ✅ Presence online (retained) + **offline tự động qua LWT** khi rớt kết nối
- ✅ Telemetry định kỳ
- ✅ Lệnh điều khiển round-trip + ack (set_config, ota, reboot)
- ✅ ACL cô lập per-device

Kiểm Redis (khi chạy bản container): state được mirror sang Redis của stack:

```bash
docker exec xiaozhi-prod-xiaozhi-redis-1 redis-cli GET device-monitor:device:HKHT2606010011
docker exec xiaozhi-prod-xiaozhi-redis-1 redis-cli SMEMBERS device-monitor:devices
```

> **Lưu ý vận hành:** topic `status` là **retained**. Khi gỡ/hủy đăng ký 1 thiết bị,
> phải **xóa retained message** (publish payload rỗng `retain=true` vào `devices/{client}/status`)
> và xóa key Redis, nếu không trạng thái cũ sẽ "sống lại" khi subscriber kết nối lại.
> manager-api nên làm việc này trong luồng unbind thiết bị.

## Tiến độ & còn lại

Đã xong:
- ✅ Broker EMQX + auth/ACL per-device.
- ✅ Consumer presence/telemetry/command + HTTP API.
- ✅ **Lưu trữ Redis** (write-through) — state bền & chia sẻ được.
- ✅ **Container hóa** vào `docker-compose.prod.yml` (trỏ EMQX + Redis nội bộ stack).
- ✅ **Kích hoạt theo Serial-Number**: declare → activate → cấp credential tự động → unbind.

Còn lại để production:
1. **Firmware ESP32**: thay `sim_device.py` bằng MQTT client thật (gọi `/activate` lấy credential, LWT, OTA). Nằm ở **repo khác**.
2. **Đưa API vào manager-api** (Java) — bọc các endpoint này dưới JWT/Shiro của console, gắn serial vào `ai_device`, để web/app dùng chung auth. Hiện API chạy ở device-monitor (HTTP stdlib, chưa auth).
3. **TLS thật** cho cổng 8883 (hiện EMQX dùng cert self-signed).
4. **Bảo mật `/activate`**: thêm xác thực thiết bị (HMAC/chứng chỉ) để tránh giả mạo serial; rate-limit.
