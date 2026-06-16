#include "ws_client.h"
#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

// ─── Module state ─────────────────────────────────────────────────────────────
static WebSocketsClient  _ws;
static QueueHandle_t     _rx_q;
static QueueHandle_t     _tx_q;

// volatile: ghi từ NetworkTask, đọc từ DataTask/app — single-byte, ARM atomic
static volatile WsState  _state     = WS_STATE_WS_CONNECTING;
static volatile bool     _ws_ready  = false;

// Backoff state — chỉ truy cập từ NetworkTask, không cần mutex
static uint32_t _wifi_backoff_ms = CFG_BACKOFF_BASE_MS;
static uint32_t _ws_backoff_ms   = CFG_BACKOFF_BASE_MS;

// WS path cần lưu để gọi lại _ws.begin() sau WiFi restore
static char _ws_path[128];

// Callbacks
static ws_on_connected_fn    _cb_connected;
static ws_on_disconnected_fn _cb_disconnected;
static ws_on_chunk_fn        _cb_chunk;
static ws_on_done_fn         _cb_done;
static ws_on_error_fn        _cb_error;

// ─── Backoff helpers (NetworkTask only) ──────────────────────────────────────
static inline uint32_t _backoff_increase(uint32_t cur) {
    uint32_t next = cur * CFG_BACKOFF_FACTOR;
    return next > CFG_BACKOFF_MAX_MS ? CFG_BACKOFF_MAX_MS : next;
}

// ─── Push disconnect frame vào RX queue (notify DataTask) ────────────────────
// Gọi từ NetworkTask — non-blocking, drop nếu queue full.
static void _push_disconnect(void) {
    WsRxFrame f;
    f.type  = WS_RX_DISCONNECTED;
    f.len   = 0;
    f.data[0] = '\0';
    xQueueSend(_rx_q, &f, 0);
}

// ─── WS Event Callback ────────────────────────────────────────────────────────
// Chạy trong ngữ cảnh NetworkTask (gọi từ _ws.loop()).
// Chỉ: copy payload → queue + cập nhật backoff.  Không parse JSON.
static void _ws_event_cb(WStype_t ev, uint8_t* payload, size_t length) {
    switch (ev) {

        case WStype_CONNECTED:
            // TCP+WS handshake OK — đang chờ server gửi {"t":"connected"}
            _ws_backoff_ms = CFG_BACKOFF_BASE_MS;      // reset backoff khi WS handshake thành công
            _ws.setReconnectInterval(_ws_backoff_ms);
            _state = WS_STATE_WS_CONNECTING;            // chờ app-level confirm
            Serial.printf("[NET] WS handshake OK — waiting for server hello\n");
            break;

        case WStype_DISCONNECTED:
            // Chỉ notify DataTask khi đang READY — tránh duplicate khi:
            //   1. WiFi drop → WS drop (_reconnect_wifi sẽ push sau với reason=WIFI_DOWN)
            //   2. Lần reconnect WS thất bại (chưa bao giờ READY lần này)
            if (_state == WS_STATE_READY) {
                _ws_ready = false;
                _push_disconnect();
            } else {
                _ws_ready = false;
            }
            _state = WS_STATE_WS_CONNECTING;

            // Exponential backoff cho lần reconnect tiếp theo
            _ws_backoff_ms = _backoff_increase(_ws_backoff_ms);
            _ws.setReconnectInterval(_ws_backoff_ms);
            Serial.printf("[NET] WS disconnected — retry in %lums\n",
                          (unsigned long)_ws_backoff_ms);
            break;

        case WStype_TEXT:
            if (length == 0 || length >= CFG_FRAME_CAP) {
                if (length >= CFG_FRAME_CAP)
                    Serial.printf("[NET] Frame dropped: len=%u > cap=%d\n",
                                  (unsigned)length, CFG_FRAME_CAP);
                return;
            }
            {
                WsRxFrame f;
                f.type = WS_RX_RAW;
                f.len  = (uint16_t)length;
                memcpy(f.data, payload, length);
                f.data[length] = '\0';
                if (xQueueSend(_rx_q, &f, 0) != pdTRUE)
                    Serial.println("[NET] RX queue full — frame dropped");
            }
            break;

        default:
            break;
    }
}

// ─── WiFi reconnect (NetworkTask only) ───────────────────────────────────────
// Blocks NetworkTask (với vTaskDelay) cho đến khi WiFi khôi phục.
// DataTask vẫn chạy bình thường vì vTaskDelay chỉ suspend NetworkTask.
static void _reconnect_wifi(void) {
    if (_state != WS_STATE_WIFI_DOWN) {
        // Chỉ push disconnect nếu DataTask chưa được notify.
        // - READY       → WS chưa drop (WiFi mất trước TCP) → push với reason WIFI_DOWN
        // - WS_CONNECTING → WStype_DISCONNECTED callback đã push rồi → KHÔNG push lại
        if (_state == WS_STATE_READY) {
            _ws_ready = false;
            _state    = WS_STATE_WIFI_DOWN;   // set trước để DataTask đọc đúng reason
            _push_disconnect();
        } else {
            _ws_ready = false;
            _state    = WS_STATE_WIFI_DOWN;
        }
        Serial.printf("[NET] WiFi lost — backoff %lums\n",
                      (unsigned long)_wifi_backoff_ms);
    }

    // Đợi backoff_ms trước khi thử reconnect — chia nhỏ 500ms để không bỏ lỡ
    // WiFi recovery do hệ thống tự reconnect (setAutoReconnect=true)
    uint32_t waited = 0;
    while (waited < _wifi_backoff_ms) {
        vTaskDelay(pdMS_TO_TICKS(500));
        waited += 500;
        if (WiFi.status() == WL_CONNECTED) goto wifi_ok;
    }

    // Thử reconnect chủ động nếu vẫn chưa có
    Serial.println("[NET] Calling WiFi.reconnect()...");
    WiFi.reconnect();

    // Chờ thêm 10s cho WiFi stack xử lý
    for (int i = 0; i < 20; i++) {
        vTaskDelay(pdMS_TO_TICKS(500));
        if (WiFi.status() == WL_CONNECTED) goto wifi_ok;
    }

    // Vẫn thất bại → tăng backoff cho lần sau
    _wifi_backoff_ms = _backoff_increase(_wifi_backoff_ms);
    Serial.printf("[NET] WiFi reconnect failed — next retry in %lums\n",
                  (unsigned long)_wifi_backoff_ms);
    return;

wifi_ok:
    _wifi_backoff_ms = CFG_BACKOFF_BASE_MS;   // reset backoff
    Serial.printf("[NET] WiFi restored! IP: %d.%d.%d.%d\n",
                  WiFi.localIP()[0], WiFi.localIP()[1],
                  WiFi.localIP()[2], WiFi.localIP()[3]);

    // Force WS re-init: disconnect cũ, begin lại với fresh backoff
    _ws.disconnect();
    vTaskDelay(pdMS_TO_TICKS(200));
    _ws_backoff_ms = CFG_BACKOFF_BASE_MS;
    _ws.setReconnectInterval(_ws_backoff_ms);
    _ws.begin(CFG_WS_HOST, CFG_WS_PORT, _ws_path);
    _state = WS_STATE_WS_CONNECTING;
}

// ─── NetworkTask (Core 0) ─────────────────────────────────────────────────────
static void _network_task(void* /*arg*/) {
    snprintf(_ws_path, sizeof(_ws_path), "%s?token=%s&device_id=%s",
             CFG_WS_PATH_BASE, CFG_WS_TOKEN, CFG_DEVICE_ID);

    _ws.begin(CFG_WS_HOST, CFG_WS_PORT, _ws_path);
    _ws.onEvent(_ws_event_cb);
    _ws.setReconnectInterval(_ws_backoff_ms);
    _ws.enableHeartbeat(15000, 3000, 2);   // WS-level ping/pong giữ connection sống

    uint32_t last_wifi_check = 0;
    WsTxFrame tx;

    while (true) {
        uint32_t now = millis();

        // ── Kiểm tra WiFi định kỳ ──────────────────────────────────────────
        // Tần suất: mỗi CFG_WIFI_CHECK_MS để không spam log
        if (now - last_wifi_check >= CFG_WIFI_CHECK_MS) {
            last_wifi_check = now;
            if (WiFi.status() != WL_CONNECTED) {
                _reconnect_wifi();    // blocks với vTaskDelay, không block DataTask
                continue;            // restart loop sau reconnect
            }
        }

        // ── Xử lý WS (callback fires đồng bộ trong _ws.loop()) ───────────
        _ws.loop();

        // ── Gửi query từ TX queue (khi server đã sẵn sàng) ───────────────
        if (_ws_ready && xQueueReceive(_tx_q, &tx, 0) == pdTRUE) {
            // Kiểm tra lại _ws_ready sau dequeue — tránh sendTXT trên socket chết
            if (!_ws_ready) {
                // WS drop ngay sau khi dequeue — đẩy lại vào queue đầu nếu còn chỗ
                // Nếu không, query bị drop và người dùng cần retry
                Serial.println("[NET] WS dropped mid-dequeue — query may be lost");
            } else {
                StaticJsonDocument<320> doc;
                doc["t"]    = "chat";
                doc["text"] = tx.text;
                doc["cid"]  = tx.conv_id[0] ? tx.conv_id : "";
                char json_buf[320];
                size_t jlen = serializeJson(doc, json_buf, sizeof(json_buf));
                _ws.sendTXT((const uint8_t*)json_buf, jlen);
                Serial.printf("[NET] TX (conv=%s): %.50s%s\n",
                              tx.conv_id[0] ? tx.conv_id : "new",
                              tx.text, strlen(tx.text) > 50 ? "..." : "");
            }
        }

        vTaskDelay(pdMS_TO_TICKS(CFG_WS_TICK_MS));   // yield + feed WDT
    }
    vTaskDelete(NULL);
}

// ─── DataTask (Core 1) ───────────────────────────────────────────────────────
static void _data_task(void* /*arg*/) {
    static char   answer_buf[CFG_ANSWER_CAP];
    static char   conv_id_buf[40];
    static size_t answer_len;

    answer_buf[0]  = '\0';
    conv_id_buf[0] = '\0';
    answer_len     = 0;

    WsRxFrame frame;

    while (true) {
        if (xQueueReceive(_rx_q, &frame, portMAX_DELAY) != pdTRUE) continue;

        // ── Disconnected (WiFi loss hoặc WS drop) ────────────────────────
        if (frame.type == WS_RX_DISCONNECTED) {
            Serial.println("[DATA] Disconnected — buffer reset");
            answer_len    = 0;
            answer_buf[0] = '\0';
            WsState reason = _state;   // WIFI_DOWN hoặc WS_CONNECTING
            if (_cb_disconnected) _cb_disconnected(reason);
            continue;
        }

        // ── Parse JSON (StaticJsonDocument on stack, không heap) ──────────
        StaticJsonDocument<CFG_FRAME_CAP + 128> doc;
        if (deserializeJson(doc, frame.data, frame.len)) {
            Serial.printf("[DATA] JSON err: %.40s\n", frame.data);
            continue;
        }

        const char* t = doc["t"] | "";

        if (strcmp(t, "connected") == 0) {
            _ws_ready = true;
            _state    = WS_STATE_READY;
            // Reset WS backoff ở đây — đây mới là kết nối "thật" (auth OK)
            _ws_backoff_ms = CFG_BACKOFF_BASE_MS;
            Serial.printf("[DATA] Ready! app=%s device=%s\n",
                          doc["app_id"] | "?", doc["device_id"] | "?");
            if (_cb_connected) _cb_connected();

        } else if (strcmp(t, "chunk") == 0) {
            const char* chunk = doc["d"] | "";
            size_t clen = strlen(chunk);
            if (clen == 0) continue;

            if (answer_len + clen < CFG_ANSWER_CAP - 1) {
                memcpy(answer_buf + answer_len, chunk, clen);
                answer_len += clen;
                answer_buf[answer_len] = '\0';
            } else {
                size_t rem = (CFG_ANSWER_CAP - 1) - answer_len;
                if (rem > 0) {
                    memcpy(answer_buf + answer_len, chunk, rem);
                    answer_len = CFG_ANSWER_CAP - 1;
                    answer_buf[answer_len] = '\0';
                }
                Serial.println("[DATA] Answer buffer full — truncated");
            }
            if (_cb_chunk) _cb_chunk(chunk, clen);

        } else if (strcmp(t, "done") == 0) {
            const char* cid = doc["cid"] | "";
            if (cid[0]) {
                strncpy(conv_id_buf, cid, sizeof(conv_id_buf) - 1);
                conv_id_buf[sizeof(conv_id_buf) - 1] = '\0';
            }
            Serial.printf("[DATA] Done. len=%u conv=%s\n",
                          (unsigned)answer_len, conv_id_buf);
            if (_cb_done) _cb_done(answer_buf, answer_len, conv_id_buf);
            answer_len    = 0;
            answer_buf[0] = '\0';

        } else if (strcmp(t, "err") == 0) {
            const char* msg  = doc["msg"]  | "Unknown";
            const char* code = doc["code"] | "";
            Serial.printf("[DATA] Server err: %s (code=%s)\n", msg, code);
            answer_len    = 0;
            answer_buf[0] = '\0';
            if (_cb_error) _cb_error(msg, code);

        } else if (strcmp(t, "pong") == 0) {
            // heartbeat OK — không cần xử lý

        } else {
            Serial.printf("[DATA] Unknown frame: '%s'\n", t);
        }
    }
    vTaskDelete(NULL);
}

// ─── Public API ───────────────────────────────────────────────────────────────

void ws_client_init(ws_on_connected_fn    on_connected,
                    ws_on_disconnected_fn on_disconnected,
                    ws_on_chunk_fn        on_chunk,
                    ws_on_done_fn         on_done,
                    ws_on_error_fn        on_error) {
    _cb_connected    = on_connected;
    _cb_disconnected = on_disconnected;
    _cb_chunk        = on_chunk;
    _cb_done         = on_done;
    _cb_error        = on_error;
    _state           = WS_STATE_WS_CONNECTING;
    _ws_ready        = false;
    _wifi_backoff_ms = CFG_BACKOFF_BASE_MS;
    _ws_backoff_ms   = CFG_BACKOFF_BASE_MS;

    _rx_q = xQueueCreate(CFG_QUEUE_DEPTH, sizeof(WsRxFrame));
    _tx_q = xQueueCreate(CFG_TX_DEPTH,    sizeof(WsTxFrame));
    configASSERT(_rx_q != NULL);
    configASSERT(_tx_q != NULL);

    Serial.printf("[WS] RX queue: %u×%u=%u B | TX: %u×%u=%u B\n",
                  CFG_QUEUE_DEPTH, (unsigned)sizeof(WsRxFrame),
                  (unsigned)(CFG_QUEUE_DEPTH * sizeof(WsRxFrame)),
                  CFG_TX_DEPTH, (unsigned)sizeof(WsTxFrame),
                  (unsigned)(CFG_TX_DEPTH * sizeof(WsTxFrame)));

    xTaskCreatePinnedToCore(_network_task, "WSNet",
                            CFG_NET_STACK,  NULL,
                            CFG_NET_PRIO,   NULL, CFG_NET_CORE);
    xTaskCreatePinnedToCore(_data_task,    "WSData",
                            CFG_DATA_STACK, NULL,
                            CFG_DATA_PRIO,  NULL, CFG_DATA_CORE);

    Serial.println("[WS] NetworkTask(C0) + DataTask(C1) started");
}

bool ws_client_send_query(const char* text, const char* conv_id) {
    if (!text || text[0] == '\0') return false;
    WsTxFrame tx;
    strncpy(tx.text,    text,              sizeof(tx.text)    - 1);
    strncpy(tx.conv_id, conv_id ? conv_id : "", sizeof(tx.conv_id) - 1);
    tx.text[sizeof(tx.text)       - 1] = '\0';
    tx.conv_id[sizeof(tx.conv_id) - 1] = '\0';
    bool ok = (xQueueSend(_tx_q, &tx, 0) == pdTRUE);
    if (!ok) Serial.println("[WS] TX queue full — query dropped");
    return ok;
}

WsState ws_client_state(void)          { return _state; }
bool    ws_client_is_ready(void)       { return _ws_ready; }

const char* ws_client_state_str(void) {
    switch (_state) {
        case WS_STATE_WIFI_DOWN:      return "WIFI_DOWN";
        case WS_STATE_WS_CONNECTING:  return "WS_CONNECTING";
        case WS_STATE_READY:          return "READY";
        default:                      return "UNKNOWN";
    }
}
