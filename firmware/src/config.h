#pragma once

// ─── WiFi ─────────────────────────────────────────────────────────────────────
#define CFG_WIFI_SSID       "YOUR_WIFI_SSID"
#define CFG_WIFI_PASS       "YOUR_WIFI_PASSWORD"

// ─── Oriagent WS Gateway ─────────────────────────────────────────────────────
// Token và device_id truyền qua query param — server Flask đọc request.args
#define CFG_WS_HOST         "192.168.1.100"   // IP hoặc hostname của oriagent
#define CFG_WS_PORT         5001
#define CFG_WS_PATH_BASE    "/ws/chat"
#define CFG_WS_TOKEN        "app-XXXXXXXXXXXXXXXX"  // App API key
#define CFG_DEVICE_ID       "esp32-001"             // Stable device ID (dùng MAC để unique)

// ─── Memory tunables ─────────────────────────────────────────────────────────
//
// CFG_FRAME_CAP: kích thước tối đa 1 WS text frame.
//   LLM chunk thường 10-80 bytes, tăng nếu server gom nhiều token/frame.
//   RX queue = CFG_QUEUE_DEPTH × (CFG_FRAME_CAP + 3) bytes heap.
#define CFG_FRAME_CAP       512

// CFG_QUEUE_DEPTH: số frame buffer giữa NetworkTask và DataTask.
//   Tăng nếu gặp "RX queue full" khi LLM stream nhanh.
#define CFG_QUEUE_DEPTH     10

// CFG_TX_DEPTH: số query buffer từ DataTask/main sang NetworkTask.
#define CFG_TX_DEPTH        4

// CFG_ANSWER_CAP: buffer ghép toàn bộ câu trả lời (tĩnh, BSS segment).
//   Nếu ESP32 không có PSRAM, giảm xuống 2048 để tiết kiệm heap.
#define CFG_ANSWER_CAP      4096

// ─── FreeRTOS Task config ────────────────────────────────────────────────────
//
// NetworkTask — Core 0, cùng với WiFi/lwIP stack để giảm context switch.
// DataTask    — Core 1, isolated, an toàn cho Serial/TTS/LCD.
#define CFG_NET_STACK       4096
#define CFG_NET_PRIO        5      // cao hơn DataTask để giữ network alive
#define CFG_NET_CORE        0

#define CFG_DATA_STACK      7168   // cần thêm stack cho ArduinoJson parse
#define CFG_DATA_PRIO       3
#define CFG_DATA_CORE       1

// ─── Timing ──────────────────────────────────────────────────────────────────
#define CFG_WS_TICK_MS          1       // webSocket.loop() period (ms)
#define CFG_PING_INTERVAL_S     30      // heartbeat ping tới server

// ─── Exponential Backoff ─────────────────────────────────────────────────────
// Áp dụng cho cả WiFi reconnect và WS reconnect.
// Mỗi lần thất bại: delay × CFG_BACKOFF_FACTOR (nhân đôi), tối đa CFG_BACKOFF_MAX_MS.
// Reset về BASE khi kết nối lại thành công.
//
// Progression: 1s → 2s → 4s → 8s → 16s → 32s → 60s (giữ nguyên)
#define CFG_BACKOFF_BASE_MS     1000
#define CFG_BACKOFF_MAX_MS      60000
#define CFG_BACKOFF_FACTOR      2

// Kiểm tra WiFi status mỗi N ms trong NetworkTask.
// Không cần quá nhanh vì WiFi event handler đã bắt disconnect sự kiện.
#define CFG_WIFI_CHECK_MS       5000
