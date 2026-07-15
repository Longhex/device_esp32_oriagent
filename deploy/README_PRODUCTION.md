# Xiaozhi Production Deployment

This stack keeps `docker-compose_all.yml` untouched for local/dev use and adds a separate production-oriented setup that builds images from the current source tree.

## Files

- `docker-compose.prod.yml`: main stack, includes build-from-source services and the optional SSL profile.
- `docker-compose.test.yml`: local/no-domain override that exposes the edge router on `TEST_HTTP_PORT`.
- `.env.example`: variables for secrets, domain, ports, and resource limits.
- `nginx/edge-router.conf.template`: path-based router for `/`, `/xiaozhi/v1/`, and `/mcp/`.
- `scripts/recommend-resources.sh`: Linux helper that prints recommended CPU and memory limits for the current host.

## Prepare

1. Copy `.env.example` to `.env`.
2. Set a strong `MYSQL_PASSWORD`.
3. Keep `deploy/data/.config.yaml` pointing to the manager API inside Docker. This stack keeps compatibility with the existing internal host:

```yaml
manager-api:
  url: http://xiaozhi-esp32-server-web:8002/xiaozhi
```

4. Ensure `deploy/models/SenseVoiceSmall/model.pt` exists.
5. If using XiaoZhi native web search at scale (vài vạn người dùng), provide a `SEARCH_PROXY` in `.env` to avoid rate limits from search engines.

## Local / no-domain test

```bash
cd deploy
docker compose -f docker-compose.prod.yml -f docker-compose.test.yml up -d --build
```

Default entrypoint:

- Admin UI: `http://localhost:8080/`
- WebSocket: `ws://localhost:8080/xiaozhi/v1/`
- OTA: `http://localhost:8080/xiaozhi/ota/`
- Vision API: `http://localhost:8080/mcp/vision/explain`

## Production with Let's Encrypt

Requirements:

- `PUBLIC_DOMAIN` must resolve to the server.
- Ports `80` and `443` must be publicly reachable.

Run:

```bash
cd deploy
docker compose --profile ssl -f docker-compose.prod.yml up -d --build
```

Production endpoints:

- Admin UI: `https://device.oriagent.com/`
- Device signaling: MQTT `device.oriagent.com:1883`
- Device voice media: UDP AES-CTR `device.oriagent.com:8883/udp`
- WebSocket voice: disabled; `/xiaozhi/v1/` returns `410`
- OTA: `https://device.oriagent.com/xiaozhi/ota/`
- Vision API: `https://device.oriagent.com/mcp/vision/explain`

## EMQX — broker quản lý/giám sát thiết bị

`docker-compose.prod.yml` dùng EMQX cho cả topic voice HK (`{serial}`/`{serial}/MONITOR`) và management. Audio không đi qua broker; Opus đi trực tiếp qua UDP AES-CTR.

Cổng:

- `1883/tcp` MQTT, `8883/tcp` MQTT TLS và `8883/udp` voice AES-CTR — mở public qua firewall/VPS.
- `8083`/`8084` MQTT over WebSocket/WSS — cho app/web nếu cần kết nối trực tiếp.
- `18083` Dashboard quản trị — mặc định bind `127.0.0.1`, truy cập qua SSH tunnel:
  `ssh -L 18083:127.0.0.1:18083 user@server` rồi mở `http://localhost:18083`.

Chuẩn bị trong `.env`:

1. Đặt `EMQX_DASHBOARD_PASSWORD` mạnh và `EMQX_NODE_COOKIE` ngẫu nhiên.
2. ⚠️ EMQX 5.x **mặc định cho phép kết nối ẩn danh** khi chưa cấu hình authenticator. Trước khi mở cổng `1883`/`8883` ra public, **bắt buộc** bật authentication: Dashboard → Access Control → Authentication → tạo built-in DB (per-device username/password) hoặc HTTP authn trỏ về `manager-api`. Smoke-test xong nhớ khoá lại.

Kiểm tra nhanh sau khi `up`:

```bash
docker compose -f docker-compose.prod.yml exec emqx emqx ctl status   # "is started"
docker compose -f docker-compose.prod.yml exec emqx emqx ctl listeners # thấy tcp:default 1883...
```

Bước tiếp theo (chưa làm ở stack này): cấu hình authentication theo từng thiết bị (per-device credential, có thể wire HTTP authn trỏ về `manager-api`), rule-engine/bridge đẩy presence + telemetry về Redis/DB, và API cho web/app.

## Resource tuning

Compose cannot auto-scale CPU and memory limits by itself. For a Linux VPS, you can generate suggested values and paste them into `.env`:

```bash
cd deploy
sh scripts/recommend-resources.sh
```

## Notes

- The native `web_search` plugin runs inside `xiaozhi-server` through the normal plugin/function-call pipeline.
- The current web and mobile UIs can display an MCP access point and discovered MCP tools for an agent, but they do not edit third-party MCP server definitions. Those still come from `data/.mcp_server_settings.json`.
- Port `8004` is not used by the current runtime path, so this stack does not publish or depend on it.
- The outer `nginx-proxy + acme-companion` layer handles TLS and HTTP-to-HTTPS redirect.
- The app-specific `xiaozhi-edge-router` handles path-based routing to the Python server and the web/admin container.
- The web container still contains its own internal Nginx, so admin/API requests pass through one extra Nginx hop by design.
- After the first clean deployment, configure `server.secret` and `server.ota`; production MQTT-only does not consume `server.websocket`.
- If you reuse an existing `deploy/mysql/data` directory from the old stack, keep `MYSQL_IMAGE_TAG` aligned with the version that created that data directory. The default is `latest` here because the current local stack already uses `mysql:latest`.
