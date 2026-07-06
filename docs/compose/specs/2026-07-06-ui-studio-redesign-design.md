# Design: Redesign giao diện manager-web theo mẫu Adobe XD "Device Oriagent"

Ngày: 2026-07-06 · Trạng thái: Đã duyệt (5/5 phần) · Người duyệt: anh Khanh

## [S1] Bối cảnh & phạm vi

Nguồn mẫu: file Adobe XD đã giải nén tại
`/home/khanhnq/Downloads/Device Oriagent — May 28, 10.03.04 AM (1)` — 6 artboard 1920×1080:

| Artboard | Nội dung | Màn ứng với | Trạng thái |
|---|---|---|---|
| Login – 1 | Đăng nhập | `login.vue`, `register.vue` | ✅ Đã làm xong (ngoài spec này) |
| Home - Studio – 28 | Danh sách Robot Agent | `home.vue` | Đợt 1 |
| Home - Studio – 31 | Quản lý Model AI | `ModelConfig.vue` | Đợt 2 |
| Home - Studio – 29, 30 | Thiết lập Robot (2 biến thể trạng thái) | `AgentConfig.vue` | Đợt 3 |

**Ngoài phạm vi:** màn Quên mật khẩu (`retrievePassword.vue`), ~17 màn admin không có mẫu
(UserManagement, OTA, Dict, VoiceClone, ...), mọi thay đổi backend/API, mục "Integration"
trong sidebar mẫu (app chưa có tính năng này).

## [S2] Nguyên tắc bất di bất dịch

1. **Chức năng là chuẩn, mẫu là skin.** Giữ 100% chức năng hiện có. Chức năng mẫu không vẽ
   → vẫn hiển thị, style theo tông mới. Mục mẫu vẽ mà app chưa có → bỏ qua.
2. **Không đổi `<script>`**, không đổi props/events của component. Chỉ đụng `<template>`
   (phần khung/bố cục) + CSS. Buộc phải đụng script → dừng, hỏi trước.
3. Đây là dự án thương mại: mỗi đợt build + verify + người duyệt bằng mắt xong mới commit,
   mỗi đợt 1 commit riêng để revert độc lập.
4. Prune builder cache **trước mỗi lần build** (tránh đầy `/`).

## [S3] Kiến trúc: shell dùng chung (Hướng A đã chọn)

Thành phần **mới** (không sửa cái cũ):

- `src/components/StudioLayout.vue` — shell dùng chung (cấu trúc theo ảnh mẫu):
  - Sidebar trái ~280px, từ trên xuống:
    1. Logo Oriagent — dùng lại `@/assets/auth/logo.svg` (logo màn login, không thêm asset).
    2. Pill "Agent Builder" (nhãn tiêu đề khu vực, nền xám nhạt).
    3. Nhóm **AgentOS**: Robot Agent (active nền xanh nhạt + chữ xanh khi ở Home/AgentConfig).
    4. Nhóm **AgentCore**: Model AI, Knowledge. (Integration trong mẫu — app chưa có → bỏ.)
    5. Nhãn nhóm **AgentSetting**: Thiết lập.
    6. Đáy sidebar: nút **Guide Document** (pill đen) + **My Account** (menu tài khoản
       hiện có — đổi chỗ từ header cũ xuống đây).
  - **Không có topbar** — Guide Document/My Account nằm đáy sidebar theo mẫu.
  - Mapping route: Robot Agent → `/home`; Model AI → `/model-config`;
    Knowledge → `/knowledge-base-management`; Thiết lập → `/params-management`.
    Mục trỏ tới trang chưa redesign điều hướng về route cũ (giao diện cũ) — chấp nhận được.
  - Slot nội dung cho từng màn.
- `src/views/studio.scss` — design tokens lấy từ XD, 3 màn cùng import (mô hình như `auth.scss`):
  - Accent xanh `#08c45b`; chữ chính `#313133`, phụ `#707070`, đen `#000`;
    nền panel `#fefefe`/`#ffffff`, nền trang `#fbfbfb`, nền phụ `#f7f7f7`, viền `#eeeeee`.
  - Font: Roboto — tiêu đề Bold 20px, nhãn Medium 20px, phụ Regular 15px
    (HelveticaNeue-Medium 15px trong mẫu thay bằng Roboto Medium 15px, đồng bộ với login).
  - Mọi class mới prefix `studio-` / scoped trong view, **không sửa `global.scss`**.

Nhánh git: commit phần login đang dở trên `fix/live-test-websocket` trước, rồi tạo
`feat/ui-studio-redesign` để làm toàn bộ việc này.

## [S4] Đợt 1 — Màn Home (artboard 28) → `home.vue`

Bố cục theo ảnh mẫu: bọc `StudioLayout` (Robot Agent active). Hàng trên cùng khu nội dung:
ô "Tìm kiếm Robot Agent" (bo tròn trắng, icon kính lúp) + nút **"Create Robot Agent"**
(pill đen, chữ trắng) sát mép phải. Lưới card trên nền xám nhạt, card trắng bo góc lớn,
bóng nhẹ. Banner hero cũ bỏ, thay bằng hàng search + Create như mẫu.

Card agent (restyle `DeviceItem.vue`) theo ảnh mẫu: avatar robot tròn (nền xanh) góc trái,
tên agent đậm + dòng phụ "Agent", hàng chip **TTS / LLM / STT** (mỗi chip: nhãn loại +
tên provider kèm icon), badge **"N Thiết bị"** ở chân card. **Giữ đủ ngoài mẫu:** nút xóa,
tooltip info systemPrompt, giọng TTS cụ thể, tag History (khi có memory), thời gian hội
thoại gần nhất, tags firmware, skeleton loading, search-history dropdown.

Chip STT: chỉ hiển thị nếu payload agent sẵn có trường model STT; thiếu thì ẩn chip —
không sửa backend.

Script giữ nguyên: `showAddDialog`, search/history, delete, click card → AgentConfig.

## [S5] Đợt 2 — Màn Model AI (artboard 31) → `ModelConfig.vue`

Quyết định đã duyệt: **giữ bảng, không chuyển card** (bảng đang gánh switch enable,
đặt mặc định, sửa/nhân bản/xóa, batch delete, phân trang — chuyển card sẽ rủi ro sót).

- Bọc `StudioLayout` (Model AI active).
- Bảng restyle: panel trắng bo góc lớn, header bảng `#f7f7f7`, chữ Roboto 15px `#313133`,
  switch/nút accent `#08c45b`, hàng cao thoáng.
- Thanh chọn nhóm model style pill/menu như mẫu — giữ đủ **6 nhóm thật**
  (LLM/VAD/STT/TTS/Memory/Intent; mẫu chỉ vẽ 4).
- Nút "Thêm mới model" đúng vị trí/kiểu mẫu.
- Dialog thêm/sửa model + dialog giọng TTS: giữ cấu trúc, tút màu/bo góc.
- Route + query `?tab=` giữ nguyên (nơi khác đang link tới).

## [S6] Đợt 3 — Màn Thiết lập Robot (artboard 29+30) → `AgentConfig.vue`

Cấu trúc thật đã gần mẫu: `AgentConfigTabs` có đúng tab (Setup/Tổng quan/Thiết bị/Lịch sử),
`RoleConfigSection` là form, tính năng test chat live WebSocket = panel "Testing" trong mẫu.
Chủ yếu restyle + sắp bố cục:

- Bọc `StudioLayout` (Robot Agent active — màn con).
- Header khu nội dung theo ảnh mẫu: nút **back** (mũi tên tròn) + dãy **tab pill**
  (Thiết lập Robot / Lịch sử & Nhật ký / Tổng quan / Thiết bị — tab active pill đen) +
  nút **"Xuất bản"** (pill đen) sát phải — map vào nút Lưu hiện có (giữ logic
  `handleSaveAll`, chỉ đổi nhãn/kiểu theo mẫu).
- Tab "Thiết lập Robot": **3 cột như ảnh mẫu** — (1) form cấu hình (`RoleConfigSection`:
  tên agent, Model AI (LLM), API Key, VAD, STT, TTS + Language/Voice Type, Câu đệm suy
  nghĩ với thời gian chờ ms); (2) panel **Testing** (test chat live WebSocket: vòng
  waveform + nút gọi xanh + ô "Nhập tin nhắn…"); (3) panel **Instructions** (system
  prompt, nút "Tạo tự động", đếm Character/Token). Màn hẹp thì các cột xếp dọc.
- Tab còn lại (Lịch sử/Tổng quan/Thiết bị): giữ component, tút card/màu/bo góc theo token.
- Giữ đủ ngoài mẫu: FunctionDialog (plugins), ContextProviderDialog, 2 dialog Add Device,
  Memory/Intent, voiceprint...
- Trước khi code: diff kỹ artboard 29 vs 30 để lấy đủ trạng thái.

## [S7] Quy trình mỗi đợt & nghiệm thu

Mỗi đợt: sửa code → prune → build web image → recreate container + restart edge-router →
tự kiểm (grep CSS/HTML mới trong container) → anh duyệt bằng mắt trên `localhost:8002` →
commit riêng đợt đó → sang đợt sau.

Checklist tự kiểm trước khi gọi duyệt:
- Build OK, CSS mới có trong container.
- Đăng nhập được; điều hướng màn mới ↔ màn cũ đủ; màn cũ không bị lệch style.
- Chức năng màn đó bấm thử đủ: Home (tạo/xóa agent, tìm kiếm, click card),
  Model AI (thêm/sửa/xóa/switch/batch/phân trang/giọng TTS),
  Agent Config (lưu, chuyển tab, test chat, các dialog).
- So màn hình thật với artboard cạnh nhau.

Thứ tự: Đợt 0 (commit login dở + nhánh mới + StudioLayout/studio.scss, chưa màn nào dùng,
build xác nhận không vỡ) → Đợt 1 Home → Đợt 2 Model AI → Đợt 3 Agent Config.

## [S8] Rủi ro & phòng bị

| Rủi ro | Phòng bị |
|---|---|
| SCSS mới đè màn cũ | Token trong `studio.scss`, prefix `studio-`, style scoped từng view, không sửa `global.scss` |
| Element UI khó ép kiểu | `::v-deep` override phạm vi trong view (như `auth.scss` đã làm) |
| Vỡ chức năng ngầm | Không đổi script/props/events; vướng thì dừng hỏi |
| Đầy disk khi build | Prune trước mỗi build |
| Hỏng giữa chừng | Mỗi đợt 1 commit, revert độc lập; image tag cũ còn nguyên |
