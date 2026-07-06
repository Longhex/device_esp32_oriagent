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

- `src/components/StudioLayout.vue` — shell dùng chung:
  - Sidebar trái ~280px: logo Oriagent trên cùng; nhóm **AgentOS** (Robot Agent, Knowledge,
    Thiết lập), nhóm **AgentCore** (AgentSetting, Model AI). Mục active màu accent.
    Mục trỏ tới trang chưa redesign điều hướng về route cũ (giao diện cũ) — chấp nhận được.
  - Mapping sidebar → route: Robot Agent → `/home`; Knowledge → `/knowledge-base-management`;
    Model AI → `/model-config`; Thiết lập → `/params-management`; AgentSetting →
    `/agent-template-management`. Mục không có route tương ứng rõ ràng → bỏ khỏi sidebar
    (cùng quy tắc với Integration).
  - Topbar: Guide Document + My Account (menu tài khoản hiện có).
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

Bố cục: bọc `StudioLayout` (Robot Agent active). Hàng tiêu đề: chữ "Robot Agent" +
ô "Tìm kiếm Robot Agent" (bo tròn, nền `#f7f7f7`) + nút "Create Robot Agent". Lưới card
trên nền `#fbfbfb`, card trắng bo góc lớn, bóng nhẹ. Banner hero cũ gọn lại thành hàng
tiêu đề; lời chào thành dòng phụ nhỏ.

Card agent (restyle `DeviceItem.vue`) theo mẫu: tên agent, mô tả từ `systemPrompt`,
chip LLM / TTS / STT, badge "N Thiết bị". **Giữ đủ ngoài mẫu:** nút xóa, tooltip info,
tên model + giọng TTS cụ thể, tag History (khi có memory), thời gian hội thoại gần nhất,
tags firmware, skeleton loading, search-history dropdown.

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
- Thanh tab restyle (pill/underline accent), giữ logic tab + nút Lưu + Back.
- Tab Setup: 2 cột như mẫu — trái form (`RoleConfigSection`), phải panel Testing;
  màn hẹp thì cột phải xuống dưới.
- Tab còn lại: giữ component, tút card/màu/bo góc theo token.
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
