#pragma once
#include <stddef.h>
#include <stdint.h>
#include "config.h"

// ─── Connection state (quan sát được từ bên ngoài) ───────────────────────────
typedef enum : uint8_t {
    WS_STATE_WIFI_DOWN = 0,   // WiFi mất kết nối
    WS_STATE_WS_CONNECTING,   // WiFi OK, đang kết nối / reconnect WS
    WS_STATE_READY,           // WS connected + server xác nhận {"t":"connected"}
} WsState;

// ─── Internal RX frame types ─────────────────────────────────────────────────
typedef enum : uint8_t {
    WS_RX_RAW = 0,       // text frame thô — DataTask parse JSON
    WS_RX_DISCONNECTED,  // WS dropped — DataTask reset buffer
} WsRxType;

typedef struct {
    WsRxType type;
    uint16_t len;
    char     data[CFG_FRAME_CAP];
} WsRxFrame;

// Frame đẩy vào TX queue — NetworkTask gọi sendTXT()
typedef struct {
    char text[256];
    char conv_id[40];
} WsTxFrame;

// ─── Callbacks (chạy trong DataTask, Core 1) ─────────────────────────────────
typedef void (*ws_on_connected_fn)   (void);
typedef void (*ws_on_disconnected_fn)(WsState reason);  // WIFI_DOWN hoặc WS_CONNECTING
typedef void (*ws_on_chunk_fn)       (const char* text, size_t len);
typedef void (*ws_on_done_fn)        (const char* full_text, size_t full_len, const char* conv_id);
typedef void (*ws_on_error_fn)       (const char* msg, const char* code);

// ─── Public API ───────────────────────────────────────────────────────────────

void ws_client_init(ws_on_connected_fn    on_connected,
                    ws_on_disconnected_fn on_disconnected,
                    ws_on_chunk_fn        on_chunk,
                    ws_on_done_fn         on_done,
                    ws_on_error_fn        on_error);

// Thread-safe. Trả về false nếu TX queue đầy hoặc chưa ready.
bool ws_client_send_query(const char* text, const char* conv_id);

WsState     ws_client_state(void);
const char* ws_client_state_str(void);  // chuỗi để print Serial
bool        ws_client_is_ready(void);
