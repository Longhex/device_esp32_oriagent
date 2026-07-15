# Giao tiếp thực tế giữa server và firmware ESP32

> Phạm vi: tài liệu này được truy vết từ **source server hiện tại**. Thư mục `firmware/` trong repository không được dùng làm chuẩn vì firmware sản phẩm nằm ở một source khác. Firmware ngoài repo phải triển khai theo contract được mô tả tại đây.
>
> Cập nhật theo source ngày 2026-07-15. Production hiện dùng MQTT-only + UDP AES-CTR theo Plan 09; các phần WebSocket/canonical hybrid được giữ làm tài liệu fallback/lịch sử.

## 1. Kết luận nhanh

Server có hai đường hội thoại chính và một đường quản lý độc lập:

| Mặt phẳng | Kết nối | Dữ liệu chính | Trạng thái thực tế |
|---|---|---|---|
| Hội thoại production HK | MQTT signaling/control + UDP AES-CTR | JSON qua MQTT, Opus qua UDP mã hóa | Server đã triển khai; firmware phải chọn `MqttProtocol` làm voice chính |
| WebSocket legacy | WebSocket | JSON text + audio Opus binary hai chiều | Listener bị tắt trong mode production MQTT-only; edge trả `410` |
| Quản lý thiết bị | MQTT/EMQX | presence, telemetry, command, ack dưới dạng JSON | Độc lập với voice transport |
| Khởi động/cập nhật | HTTP(S) | JSON OTA discovery, firmware `.bin`, ảnh multipart | Luôn chạy cùng server |

Luồng AI bên trong server không thay đổi theo transport:

```text
ESP32 microphone
  -> Opus frames
  -> server VAD
  -> ASR (audio thành text)
  -> LLM/tool
  -> TTS (text thành Opus)
  -> ESP32 speaker
```

Production đặt `TRANSPORT_MODE=mqtt_udp_hk`, `FIRMWARE_TRANSPORT_POLICY=mqtt_only` và `MQTT_SIGNALING_CONTRACT=hk_legacy`. Server không mở listener port 8000. `websocket_legacy` và canonical `mqtt_udp_hybrid` chỉ còn là mode fallback/dev.

## 2. Bốn loại dữ liệu và đường truyền

| Dữ liệu/tín hiệu | WebSocket legacy | Hybrid MQTT + UDP | Ghi chú |
|---|---|---|---|
| Audio device -> server | WebSocket binary | UDP binary | Mỗi payload là một Opus frame/packet |
| Audio server -> device | WebSocket binary | UDP binary | Không phải WAV/MP3 và không bọc JSON/base64 |
| Hello, listen, abort, STT, TTS | WebSocket text JSON | MQTT payload UTF-8 JSON | Hybrid dùng các topic khác nhau theo chiều |
| Văn bản người dùng nhập trực tiếp | `listen/detect` JSON | Cùng JSON trên MQTT state | Không có message `type: "text"` chung |
| IoT/MCP/function control | WebSocket text JSON | MQTT payload UTF-8 JSON | Cùng schema nghiệp vụ vì dùng chung `ConnectionHandler` |
| Ping/pong | WebSocket text JSON | Có thể đi qua MQTT state/MONITOR | Chỉ phản hồi khi config bật ping |
| OTA discovery | HTTP POST JSON | HTTP POST JSON | MQTT-only trả credential per-serial và không có section WebSocket |
| Firmware update | HTTP GET binary `.bin` | HTTP GET binary `.bin` | Không đi qua WS/MQTT/UDP |
| Ảnh camera/Vision | HTTP multipart binary | HTTP multipart binary | Tối đa 5 MB; URL/token được cấp qua MCP |
| Presence/telemetry | MQTT JSON | MQTT JSON | Thuộc device-monitor, không phải voice session |

## 3. Khởi động và discovery qua HTTP

### 3.1 OTA/discovery request

Firmware gọi:

```http
POST /xiaozhi/ota/ HTTP/1.1
Content-Type: application/json
Device-Id: AA:BB:CC:DD:EE:FF
Client-Id: <client-id-on-device>
Device-Model: <model>              # nên gửi
Device-Version: 1.2.3             # nên gửi
Serial-Number: HKHT2606010011     # bắt buộc trong mode MQTT-only
```

Body mẫu:

```json
{
  "application": {
    "version": "1.2.3",
    "elf_sha256": "..."
  },
  "board": {
    "type": "oriagent-board-v1",
    "mac": "AA:BB:CC:DD:EE:FF"
  }
}
```

`Device-Id` và `Client-Id` hiện là bắt buộc. Model/version có thể lấy từ header hoặc body; nếu thiếu, server dùng `default` và `0.0.0`.

### 3.2 Response WebSocket fallback/dev

```json
{
  "server_time": {
    "timestamp": 1780000000000,
    "timezone_offset": 420
  },
  "firmware": {
    "version": "1.2.3",
    "url": ""
  },
  "websocket": {
    "url": "wss://device.example.com/xiaozhi/v1/",
    "token": "<JWT-or-empty>"
  }
}
```

Nếu có bản mới trong `data/bin/{model}_{version}.bin`, `firmware.url` trỏ tới:

```text
GET /xiaozhi/ota/download/{filename}.bin
```

Response là byte stream của file `.bin`. Firmware tự kiểm tra version/hash và thực hiện OTA flash; server không đẩy firmware qua WebSocket.

### 3.3 Response production MQTT-only

`Serial-Number` phải được khai báo trước và `device-monitor` phải provision EMQX thành công. Response không có section `websocket`:

```json
{
  "mqtt": {
    "endpoint": "host:1883",
    "client_id": "HKHT2606010011",
    "username": "HKHT2606010011",
    "password": "..."
  },
  "transport": {
    "type": "mqtt_udp",
    "version": 3
  }
}
```

Credential này dùng chung broker nhưng ACL tách topic voice `{serial}`/`{serial}/MONITOR` và management. Nếu provision lỗi, OTA MQTT-only fail-closed thay vì fallback WebSocket.

## 4. Phương thức A — WebSocket legacy (fallback/dev, tắt ở production)

### 4.1 Mở kết nối

URL thường là:

```text
wss://<domain>/xiaozhi/v1/
```

Handshake cần các header:

```http
Device-Id: AA:BB:CC:DD:EE:FF
Client-Id: <client-id>
Authorization: Bearer <token-from-OTA>
Protocol-Version: 1
```

- `Device-Id` bắt buộc. Server cũng chấp nhận query `?device-id=...&client-id=...&authorization=...`, chủ yếu để test.
- Nếu auth bị tắt, `Authorization` không bắt buộc.
- Nếu auth bật, token phải đúng với cặp `client_id` và `device_id`, trừ thiết bị nằm trong whitelist.
- `Protocol-Version` hiện hỗ trợ giá trị `1`; nếu thiếu, server mặc định là `1`. Giá trị không được hỗ trợ nhận lỗi `unsupported_protocol_version` rồi socket đóng với code `1002`.
- Nginx/reverse proxy phải forward upgrade WebSocket tới port server `8000`.

### 4.2 Hello và tham số audio

Ngay sau khi socket mở, firmware gửi WebSocket **text frame**:

```json
{
  "type": "hello",
  "version": 1,
  "transport": "websocket",
  "audio_params": {
    "format": "opus",
    "sample_rate": 24000,
    "channels": 1,
    "frame_duration": 60
  },
  "features": {
    "mcp": true
  }
}
```

Server trả:

```json
{
  "type": "hello",
  "version": 1,
  "transport": "websocket",
  "audio_params": {
    "format": "opus",
    "sample_rate": 24000,
    "channels": 1,
    "frame_duration": 60
  },
  "session_id": "<uuid>"
}
```

Lưu ý thực tế từ code:

- `format` từ client được dùng để đặt `conn.audio_format`.
- Server lưu `audio_params` client riêng cho uplink/ASR và validate Opus mono, frame 60 ms.
- Server hello giữ `audio_params` downlink/TTS, mặc định 24 kHz. Firmware hiện gửi uplink 16 kHz và decoder tự đổi theo downlink 24 kHz.
- `features.mcp=true` kích hoạt chuỗi MCP initialize. Nếu firmware không triển khai MCP, gửi `false` hoặc bỏ `features`.

### 4.3 Device gửi audio và tín hiệu nghe

Một lượt nói chủ động nên đi theo thứ tự:

```text
WS text:   {"type":"listen","state":"start","mode":"manual"}
WS binary: <Opus frame 1>
WS binary: <Opus frame 2>
...
WS text:   {"type":"listen","state":"stop"}
```

Quy tắc binary:

- Mỗi WebSocket binary message chứa raw bytes của một Opus packet.
- Không thêm header riêng, không base64, không JSON.
- Server đưa nguyên từng binary message vào ASR queue.
- Với ASR non-streaming, `listen/stop` buộc server xử lý phần audio đã gom. Ở chế độ auto, VAD cũng có thể xác định điểm kết thúc lời nói.

Các mode được server ghi nhận nhưng không kiểm enum: thường dùng `auto`, `manual`, `realtime` tùy firmware.

### 4.4 Gửi text thay cho microphone

Muốn gửi câu người dùng trực tiếp, không gửi `{"type":"text"}`. Contract thực tế là:

```json
{
  "type": "listen",
  "state": "detect",
  "text": "Thời tiết hôm nay thế nào?"
}
```

Server đưa `text` thẳng vào luồng chat/LLM. Plain text không phải JSON hiện chỉ bị server echo lại và không đi vào LLM.

### 4.5 Server trả STT, TTS text và audio

Thứ tự điển hình:

```text
server text  -> {"type":"stt","text":"...","session_id":"..."}
server text  -> {"type":"tts","state":"start","session_id":"..."}
server text  -> {"type":"tts","state":"sentence_start","text":"...","session_id":"..."}
server binary-> <Opus packet 1>
server binary-> <Opus packet 2>
...
server text  -> {"type":"tts","state":"stop","session_id":"..."}
```

Ý nghĩa:

| Message | Firmware nên làm gì |
|---|---|
| `stt` | Hiển thị câu server nhận dạng từ người dùng |
| `tts/start` | Chuyển UI sang trạng thái assistant chuẩn bị/nói |
| `tts/sentence_start` | Hiển thị đoạn text assistant sắp phát |
| binary Opus | Đưa vào Opus decoder/jitter buffer và phát loa |
| `tts/stop` | Đợi audio buffer phát hết, sau đó trở về idle/listening |

Không được hiểu `tts/stop` là audio frame. Đây là JSON control message được gửi sau khi server đã drain hàng đợi gửi audio.

### 4.6 Barge-in/abort

Khi người dùng đánh thức/nói chen lúc assistant đang phát:

```json
{"type":"abort","session_id":"<session-id>"}
```

Server hủy LLM/TTS queue và phản hồi:

```json
{"type":"tts","state":"stop","session_id":"<session-id>"}
```

Firmware phải dừng decoder/playback và xóa audio buffer cũ trước khi bắt đầu lượt mới.

### 4.7 Ping/pong

```json
{"type":"ping"}
```

Nếu `enable_websocket_ping=true`, server trả:

```json
{"type":"pong","timestamp":"YYYY-MM-DD HH:mm:ss"}
```

Nếu config tắt, application ping bị bỏ qua. WebSocket protocol-level ping/pong vẫn là cơ chế riêng của thư viện/network stack.

## 5. Phương thức B — Canonical hybrid 12-byte (legacy, không dùng cho HK production)

### 5.1 Điều kiện chạy

Server chỉ mở hybrid khi:

```text
TRANSPORT_MODE=mqtt_udp_hybrid
```

hoặc compatibility flag:

```text
ENABLE_HYBRID_GATEWAY=true
```

Khi đó server:

- Kết nối broker MQTT từ `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`.
- Subscribe `devices/+/signaling` và `devices/+/state`.
- Mở UDP multiplexer tại `0.0.0.0:5000`.
- Vẫn mở WebSocket tại port 8000.

### 5.2 Topic contract của hybrid mới

Giả sử `device_id = AA:BB:CC:DD:EE:FF`:

| Topic | Hướng | Nội dung |
|---|---|---|
| `devices/{device_id}/signaling` | device -> server | `call_invite` JSON |
| `devices/{device_id}/state` | device -> server | hello/listen/abort/iot/mcp/ping JSON |
| `devices/{device_id}/command` | server -> device | `call_accept` hoặc error |
| `{device_id}/MONITOR` | server -> device | hello/STT/TTS/IoT/MCP/pong JSON trong session |

Firmware hybrid hiện phải subscribe **cả** `devices/{device_id}/command` và `{device_id}/MONITOR`. Tên `MONITOR` không nằm dưới prefix `devices/` là hành vi đúng theo code hiện tại, dù không nhất quán.

MQTT payload ở các topic trên là UTF-8 JSON text, không phải audio.

### 5.3 Tạo voice session

Device publish:

```json
{
  "type": "call_invite",
  "device_id": "AA:BB:CC:DD:EE:FF",
  "client_id": "<client-id>",
  "token": "Bearer <token-if-auth-enabled>",
  "audio_format": "opus",
  "sample_rate": 24000
}
```

Server publish vào `devices/{device_id}/command`:

```json
{
  "type": "call_accept",
  "session_id": "A1B2C3D4",
  "server_ip": "10.0.0.15",
  "udp_port": 5000
}
```

`session_id` hybrid là 1–8 ký tự ASCII; server hiện sinh đúng 8 ký tự hex uppercase. Sau khi nhận `call_accept`, firmware publish hello vào topic state:

```json
{
  "type": "hello",
  "version": 1,
  "transport": "udp",
  "audio_params": {
    "format": "opus",
    "sample_rate": 24000,
    "channels": 1,
    "frame_duration": 60
  },
  "features": {"mcp": false}
}
```

Sau hello, tất cả JSON nghiệp vụ ở phần WebSocket (`listen`, `abort`, `iot`, `mcp`, `ping`) được publish vào `devices/{device_id}/state`. Server trả JSON session qua `{device_id}/MONITOR`.

Không nên gửi hello trước `call_accept`: server có lưu bản hello gần nhất để log nhưng không replay nó vào `ConnectionHandler` mới.

### 5.4 UDP packet format

Mỗi datagram UDP gồm header 12 byte, theo network byte order (big-endian), sau đó là raw Opus payload:

| Offset | Size | Kiểu | Ý nghĩa |
|---:|---:|---|---|
| 0 | 8 | ASCII, pad `0x00` | `session_id` |
| 8 | 2 | unsigned 16-bit BE | sequence number, wrap sau 65535 |
| 10 | 1 | unsigned 8-bit | flags/payload type |
| 11 | 1 | unsigned 8-bit | reserved, hiện đặt `0` |
| 12 | N | bytes | một Opus packet |

Pseudo-code đóng gói:

```c
packet[0..7]  = session_id padded with 0x00;
packet[8..9]  = seq uint16 big-endian;
packet[10]    = flags;
packet[11]    = 0;
packet[12..]  = opus_packet;
```

Quy ước flags theo code hiện tại:

| Flags | Hướng | Ý nghĩa |
|---:|---|---|
| `0x01` | server -> device | audio packet bình thường (default payload type) |
| khác `0xFF` | device -> server | được server coi là audio bình thường |
| `0xFF` | device -> server | End-of-Stream, không có audio payload |

Firmware nên dùng `0x01` cho audio thường và `0xFF` cho EOS để contract rõ ràng.

### 5.5 Luồng audio hybrid

```text
1. MQTT call_invite
2. MQTT call_accept (nhận session_id, server_ip, udp_port)
3. MQTT hello trên /state
4. MQTT listen/start trên /state
5. UDP header + Opus, tăng seq từng packet
6. MQTT listen/stop trên /state và/hoặc UDP EOS flags=0xFF
7. MQTT STT/TTS control từ topic /MONITOR
8. UDP header + Opus từ server, phát loa
9. MQTT tts/stop từ /MONITOR
```

Datagram đầu tiên từ device đồng thời giúp server học địa chỉ `(IP, port)` phía client để gửi audio ngược lại. Vì vậy firmware phải gửi UDP trước thì server mới có `client_addr`; NAT rebinding được server cập nhật khi packet mới tới.

Server bỏ packet được đánh giá là cũ/out-of-order và không có cơ chế retransmit. Firmware nên có jitter buffer nhỏ ở chiều nhận, chấp nhận mất packet, và không dùng UDP cho JSON control quan trọng.

### 5.6 Trạng thái production hybrid

Canonical hybrid 12-byte không được dùng cho HK production. Nó được giữ để tương thích nhánh nghiên cứu cũ.

### 5.7 Contract HK MQTT-only + UDP AES-CTR đang dùng

```text
Device -> MQTT {serial}: hello/listen/abort/goodbye/MCP
Server -> MQTT {serial}/MONITOR: hello/STT/TTS/LLM/MCP
Device <-> Server: UDP Opus + AES-CTR
```

Device hello dùng `version=3`, `transport=udp`, uplink Opus mono 16 kHz/60 ms. Server hello công bố downlink thực tế, mặc định 24 kHz/60 ms, cùng `udp.server`, `udp.port`, AES-128 `key` và nonce template theo session.

UDP packet HK có header 16 byte:

| Offset | Size | Nội dung |
|---:|---:|---|
| 0 | 1 | type cố định `0x01` |
| 1 | 1 | flags |
| 2 | 2 | encrypted payload length, uint16 BE |
| 4 | 4 | SSRC, uint32 BE |
| 8 | 4 | timestamp, uint32 BE |
| 12 | 4 | sequence, uint32 BE |
| 16 | N | Opus ciphertext |

Toàn bộ header truyền trên mạng đồng thời là counter AES-CTR. Key và client SSRC sinh theo session; SSRC route datagram tới đúng session. Server dùng SSRC khác chiều để tránh trùng CTR domain. Port mặc định production là `8883/udp`; nó có thể tồn tại song song với MQTT TLS `8883/tcp`.

Lưu ý bắt buộc: `HK_Embedded/main/application.cc` trong source đối chiếu vẫn chọn `WebsocketProtocol` cho `protocol_` voice. Server đã sẵn sàng contract này nhưng thiết bị chỉ mở UDP khi firmware thực sự gọi `MqttProtocol::OpenAudioChannel()`.

## 6. MQTT quản lý thiết bị — độc lập với voice

`main/device-monitor` định nghĩa một protocol MQTT thứ ba. Nó dùng Serial Number làm `{client}`, không dùng MAC/device-id làm khóa chính.

| Topic | Hướng | QoS/retain đề xuất | Payload |
|---|---|---|---|
| `devices/{serial}/status` | device -> server | QoS 1, retained + LWT | online/offline |
| `devices/{serial}/telemetry` | device -> server | QoS 1 | health metrics |
| `devices/{serial}/command` | server -> device | QoS 1 | lệnh quản trị |
| `devices/{serial}/command/ack` | device -> server | QoS 1 | kết quả lệnh |

Status:

```json
{"online":true,"ts":1780000000,"fw_ver":"1.2.3"}
```

LWT/offline retained:

```json
{"online":false,"ts":1780000000,"fw_ver":"1.2.3"}
```

Telemetry:

```json
{
  "ts": 1780000000,
  "uptime_s": 3600,
  "battery_pct": 82,
  "rssi_dbm": -55,
  "free_heap_kb": 104,
  "fw_ver": "1.2.3"
}
```

Command server gửi:

```json
{
  "id": "<command-id>",
  "action": "set_config",
  "params": {"volume": 70},
  "ts": 1780000000
}
```

Ack device trả:

```json
{
  "id": "<same-command-id>",
  "action": "set_config",
  "status": "done",
  "result": {"ok": true, "applied": {"volume": 70}},
  "ts": 1780000001
}
```

Protocol này có thể chạy song song với WebSocket voice hoặc hybrid voice, nhưng credential và ACL cần cho phép đúng topic. Không trộn `status/telemetry` với `state/signaling` dù cùng prefix `devices/`.

### 6.1 Compatibility bridge cho HK firmware hiện tại

Trong thời gian firmware chưa chuyển sang canonical topic, `device-monitor` bật bridge:

- Nhận state/response từ `HAKAT_AI_MONITOR_ALL`, xác định serial từ `serial_number` hoặc mapping MAC.
- Gửi command có target vào `{serial}/MONITOR`, không dùng broadcast `HAKAT_AI_REMOTE_ALL`.
- Chuyển `action/params` của API thành `cmd` mà firmware hiện hỗ trợ.
- Lệnh firmware chưa hỗ trợ trả `unsupported_by_current_firmware`, không trả success giả.

ACL mỗi device chỉ bổ sung publish `HAKAT_AI_MONITOR_ALL` và subscribe đúng `{serial}/MONITOR`; canonical `devices/{serial}/#` vẫn là contract dài hạn.

## 7. IoT và MCP qua kênh JSON

### 7.1 IoT descriptor/state từ device

Firmware có thể công bố capability:

```json
{
  "type": "iot",
  "descriptors": [
    {
      "name": "speaker",
      "description": "Loa trên thiết bị",
      "properties": {
        "volume": {"type": "number", "description": "Âm lượng"}
      },
      "methods": {
        "set_volume": {
          "description": "Đặt âm lượng",
          "parameters": {
            "volume": {"type": "number", "description": "0-100"}
          }
        }
      }
    }
  ]
}
```

Device cập nhật trạng thái:

```json
{
  "type": "iot",
  "states": [
    {"name": "speaker", "state": {"volume": 50}}
  ]
}
```

Server điều khiển:

```json
{
  "type": "iot",
  "commands": [
    {"name": "speaker", "method": "set_volume", "parameters": {"volume": 70}}
  ]
}
```

### 7.2 MCP

MCP được bọc trong envelope:

```json
{"type":"mcp","payload":{...JSON-RPC 2.0...}}
```

Khi client khai báo `features.mcp=true`, server gửi `initialize` với protocol version `2024-11-05`, sau đó `tools/list`; tool call dùng `tools/call`. Firmware phải giữ nguyên `id` khi trả `result` hoặc `error`.

Ví dụ response:

```json
{
  "type": "mcp",
  "payload": {
    "jsonrpc": "2.0",
    "id": 3,
    "result": {
      "content": [{"type": "text", "text": "OK"}],
      "isError": false
    }
  }
}
```

## 8. Ảnh/Vision và binary ngoài audio

Ảnh không được gửi trong WebSocket binary vì server sẽ coi mọi WS binary là audio. Luồng đúng:

1. Firmware bật MCP.
2. Server gửi trong MCP initialize capability `vision.url` và `vision.token`.
3. Firmware chụp ảnh và HTTP POST `multipart/form-data` tới URL đó.
4. Header gồm `Authorization: Bearer <token>`, `Device-Id`, `Client-Id`.
5. Multipart part đầu là câu hỏi dạng text; part sau là file ảnh binary.

Server chấp nhận JPEG, PNG, GIF, BMP, TIFF, WEBP, tối đa 5 MB và trả JSON kết quả vision.

Các file ảnh server đã resize cho màn hình firmware được phục vụ bằng HTTP GET `/images/{hash}.{ext}`; chúng cũng không đi qua voice binary channel.

## 9. State machine tối thiểu firmware nên triển khai

```text
BOOT
  -> HTTP OTA/discovery
  -> chọn transport
  -> CONNECTING
  -> HELLO
  -> IDLE
  -> LISTENING (listen/start + audio upload)
  -> THINKING  (listen/stop, chờ stt/tts)
  -> SPEAKING  (tts controls + audio download/playback)
  -> IDLE       (tts/stop)

SPEAKING + wake/button -> abort -> clear playback -> LISTENING
network lost           -> reconnect -> HELLO -> IDLE
```

Firmware nên tách hai queue:

- Control queue: JSON, phải xử lý theo thứ tự và không block bởi decoder.
- Audio queue: Opus packets, có jitter buffer, có khả năng clear ngay khi abort/session đổi.

Mọi audio/control nhận được phải gắn với session hiện hành. HK MQTT-only nhận session ID trong server hello; UDP được route bằng SSRC của nonce template. Khi reconnect hoặc nhận session mới, xóa toàn bộ buffer của session cũ.

## 10. Checklist tích hợp firmware ngoài repo

### Bắt buộc cho MQTT-only HK production

- [ ] OTA gửi `Serial-Number` đã được declare để nhận credential EMQX.
- [ ] Chọn `MqttProtocol` làm `protocol_` voice chính; không tạo hai MQTT client trùng vai trò.
- [ ] Publish hello/listen/abort/goodbye vào `{serial}` và subscribe `{serial}/MONITOR`.
- [ ] Parse server hello `transport=udp`, AES key/nonce và downlink audio params.
- [ ] UDP AES-CTR header đúng 16 byte, network byte order; sequence bắt đầu từ 1.
- [ ] Gửi UDP packet đầu tiên để server học địa chỉ NAT trả audio.
- [ ] Clear playback/session state khi abort, goodbye hoặc reconnect.

### WebSocket fallback/dev

- [ ] HTTP POST OTA với `Device-Id`, `Client-Id`, model và version.
- [ ] Hỗ trợ `ws://` và production nên dùng `wss://`.
- [ ] Gửi đúng header auth từ OTA.
- [ ] Gửi hello JSON ngay sau connect.
- [ ] Encode/decode Opus mono 24 kHz, frame 60 ms hoặc khớp cấu hình server đã thống nhất.
- [ ] Một WS binary frame tương ứng một Opus packet.
- [ ] Triển khai `listen start/stop/detect`, `stt`, `tts`, `abort`.
- [ ] Clear playback buffer khi abort, disconnect hoặc session đổi.

### Canonical hybrid 12-byte cũ (không dùng cho HK production)

- [ ] MQTT subscribe cả `/command` và `{device_id}/MONITOR` trước khi invite.
- [ ] Publish `call_invite`, đợi `call_accept`, rồi mới publish hello/state.
- [ ] UDP header đúng 12 byte và big-endian.
- [ ] Gửi UDP audio thường flags `0x01`, EOS `0xFF`.
- [ ] Sequence 16-bit có wrap-around.
- [ ] Gửi packet UDP đầu tiên để bind đường trả audio qua NAT.
- [ ] Server phải công bố public UDP host/port thật, firewall mở UDP.

### Thêm nếu dùng device monitoring

- [ ] Activate Serial Number để nhận MQTT credential/ACL.
- [ ] LWT offline retained + online retained khi connect.
- [ ] Telemetry định kỳ.
- [ ] Subscribe command và ack cùng `command-id`.

## 11. Các điểm không nên suy đoán từ source hiện tại

- Không dùng firmware trong thư mục `firmware/` làm chuẩn triển khai sản phẩm.
- Không coi `docs/mqtt-gateway-integration.md` là contract của hybrid mới; tài liệu đó mô tả gateway ngoài và các port/topic khác.
- Không coi mọi MQTT topic `devices/...` là cùng một protocol.
- Không gửi WAV/PCM/MP3 nếu hello khai báo Opus; binary channel không tự nhận biết container file.
- Không gửi image qua WebSocket binary.
- Không dùng message `type: text`; server không đăng ký handler đó.
- `conversation_id` của Oriagent/Dify là state nội bộ phía server, khác `session_id` transport. Firmware không cần tự tạo hoặc truyền `conversation_id` trong protocol hiện tại.

## 12. Nguồn đối chiếu trong repository

| Nội dung | Source chuẩn |
|---|---|
| Chọn transport và service được mở | `main/xiaozhi-server/app.py` |
| WebSocket handshake/auth | `main/xiaozhi-server/core/websocket_server.py` |
| Session và routing text/binary | `main/xiaozhi-server/core/connection.py` |
| Danh sách JSON message nhận | `main/xiaozhi-server/core/handle/textMessageHandlerRegistry.py` |
| Hello | `main/xiaozhi-server/core/handle/helloHandle.py` |
| Listen/text injection | `main/xiaozhi-server/core/handle/textHandler/listenMessageHandler.py` |
| STT/TTS và audio outbound | `main/xiaozhi-server/core/handle/sendAudioHandle.py` |
| MQTT hybrid topics/session | `main/xiaozhi-server/core/mqtt_server.py` |
| UDP header/flags/session | `main/xiaozhi-server/core/udp_server.py` |
| HTTP OTA/discovery/download | `main/xiaozhi-server/core/api/ota_handler.py` |
| HTTP Vision | `main/xiaozhi-server/core/api/vision_handler.py` |
| MQTT monitoring | `main/device-monitor/common.py`, `sim_device.py`, `README.md` |
