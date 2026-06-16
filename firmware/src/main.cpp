#include <Arduino.h>
#include <WiFi.h>
#include <Preferences.h>
#include "config.h"
#include "ws_client.h"

static char g_conv_id[40] = "";

// ─── NVS persist cho conversation_id ─────────────────────────────────────────
// Giữ context hội thoại qua reboot/mất điện. Flash có giới hạn ~100k write
// cycles → chỉ ghi khi cid THỰC SỰ đổi (so với _persisted_cid).
static Preferences _prefs;
static char        _persisted_cid[40] = "";

// Load cid đã lưu từ NVS vào g_conv_id (gọi 1 lần lúc boot).
static void conv_id_load(void) {
    _prefs.begin("haki", false);                 // namespace "haki", read-write
    size_t n = _prefs.getString("cid", g_conv_id, sizeof(g_conv_id));
    if (n == 0) g_conv_id[0] = '\0';             // chưa có → rỗng
    strncpy(_persisted_cid, g_conv_id, sizeof(_persisted_cid) - 1);
    _persisted_cid[sizeof(_persisted_cid) - 1] = '\0';
    if (g_conv_id[0])
        Serial.printf("[NVS] Resumed conv: %s\n", g_conv_id);
    else
        Serial.println("[NVS] No saved conv — fresh start");
}

// Ghi cid vào NVS, chỉ khi khác giá trị đã lưu (tránh wear flash).
static void conv_id_save(const char* cid) {
    if (!cid) cid = "";
    if (strncmp(cid, _persisted_cid, sizeof(_persisted_cid)) == 0)
        return;                                  // không đổi → bỏ qua
    _prefs.putString("cid", cid);
    strncpy(_persisted_cid, cid, sizeof(_persisted_cid) - 1);
    _persisted_cid[sizeof(_persisted_cid) - 1] = '\0';
    Serial.printf("[NVS] Saved conv: %s\n", cid[0] ? cid : "(cleared)");
}

// Xóa cid khỏi NVS + RAM (lệnh "clear" hoặc bắt đầu hội thoại mới).
static void conv_id_clear(void) {
    g_conv_id[0] = '\0';
    if (_persisted_cid[0]) {
        _prefs.remove("cid");
        _persisted_cid[0] = '\0';
    }
}

// ─── Callbacks ────────────────────────────────────────────────────────────────

static void on_ws_connected(void) {
    Serial.println("\n[APP] Oriagent ready.");
    // Resume: đã có conv cũ (boot từ NVS hoặc reconnect giữa phiên) → im lặng,
    // chờ user nói; KHÔNG auto-chào với cid="" (sẽ tạo conv mới, ghi đè NVS).
    // Chỉ chào lần đầu khi chưa có conversation nào.
    if (g_conv_id[0] == '\0')
        ws_client_send_query("Xin chào, bạn là ai?", "");
    else
        Serial.printf("[APP] Resuming conv %s — chờ user.\n", g_conv_id);
}

static void on_ws_disconnected(WsState reason) {
    Serial.printf("[APP] Disconnected. reason=%s\n",
                  reason == WS_STATE_WIFI_DOWN ? "WiFi lost" : "WS dropped");
    // TODO: dừng TTS, hiện icon "mất kết nối" trên màn hình
}

static void on_chunk(const char* text, size_t len) {
    Serial.write((const uint8_t*)text, len);
}

static void on_done(const char* full_text, size_t full_len, const char* conv_id) {
    Serial.printf("\n[APP] Done. len=%u conv=%s\n", (unsigned)full_len, conv_id);
    strncpy(g_conv_id, conv_id, sizeof(g_conv_id) - 1);
    g_conv_id[sizeof(g_conv_id) - 1] = '\0';
    conv_id_save(g_conv_id);          // persist — no-op nếu cid không đổi
}

static void on_error(const char* msg, const char* code) {
    Serial.printf("[APP] Error: %s (code=%s)\n", msg, code);
}

// ─── Setup ────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(400);
    Serial.println("\n=== Oriagent WS Client ===");

    // Auto-reconnect do hệ thống xử lý — NetworkTask sẽ gọi WiFi.reconnect()
    // nếu auto-reconnect không đủ nhanh
    WiFi.setAutoReconnect(true);
    WiFi.mode(WIFI_STA);
    WiFi.begin(CFG_WIFI_SSID, CFG_WIFI_PASS);
    Serial.print("[APP] WiFi");
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print('.'); }
    Serial.printf("\n[APP] IP: %d.%d.%d.%d  Heap: %u\n",
                  WiFi.localIP()[0], WiFi.localIP()[1],
                  WiFi.localIP()[2], WiFi.localIP()[3],
                  (unsigned)esp_get_free_heap_size());

    conv_id_load();                   // khôi phục context từ NVS (nếu có)

    ws_client_init(on_ws_connected, on_ws_disconnected,
                   on_chunk, on_done, on_error);

    Serial.printf("[APP] Init done. Heap: %u\n",
                  (unsigned)esp_get_free_heap_size());
}

// ─── Loop ─────────────────────────────────────────────────────────────────────
void loop() {
    // Serial Monitor commands
    static char  buf[200];
    static uint8_t blen = 0;

    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            if (blen > 0) {
                buf[blen] = '\0';
                blen = 0;

                if (strcmp(buf, "clear") == 0) {
                    conv_id_clear();          // xóa cả RAM lẫn NVS
                    Serial.println("[APP] Conv reset (RAM+NVS)");
                } else if (strcmp(buf, "status") == 0) {
                    Serial.printf("[APP] state=%s ready=%s conv=%s heap=%u\n",
                                  ws_client_state_str(),
                                  ws_client_is_ready() ? "y" : "n",
                                  g_conv_id[0] ? g_conv_id : "-",
                                  (unsigned)esp_get_free_heap_size());
                } else {
                    if (!ws_client_send_query(buf, g_conv_id))
                        Serial.println("[APP] Query dropped (not ready or queue full)");
                }
            }
        } else if (blen < sizeof(buf) - 1) {
            buf[blen++] = c;
        }
    }

    vTaskDelay(pdMS_TO_TICKS(100));
}
