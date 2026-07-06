# UI Studio Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign 3 màn manager-web (Home, Model AI, Agent Config) theo mẫu Adobe XD "studio" với shell sidebar dùng chung, giữ 100% chức năng hiện có.

**Architecture:** Shell `StudioLayout.vue` (sidebar panel nổi) + token `studio.scss` dùng chung; từng màn chỉ đổi `<template>` khung + CSS, script giữ nguyên (ngoại lệ duy nhất đã duyệt: computed gộp provider ở ModelConfig). Mỗi đợt: prune → build → verify container → anh duyệt bằng mắt → commit riêng.

**Tech Stack:** Vue 2 + Element UI + SCSS (scoped, `::v-deep`), Docker Compose (deploy/docker-compose.prod.yml + docker-compose.test.yml), image `xiaozhi-web-custom:local`.

**Spec:** `docs/compose/specs/2026-07-06-ui-studio-redesign-design.md` · **Ảnh đối chiếu:** `docs/compose/specs/assets/ui-studio/*.png`

**QUY TẮC CHUNG CHO MỌI TASK (từ S2/S8):**
- Không sửa `<script>` trừ ngoại lệ Task 9 (chỉ THÊM computed/method mới).
- Không sửa `global.scss`. Mọi style mới trong `studio.scss` (class prefix `studio-`) hoặc scoped trong view.
- Prune trước MỖI lần build: `docker builder prune -af`.
- Lệnh build (chạy từ `/home/khanhnq/device_esp32_oriagent/deploy`):
  ```bash
  docker builder prune -af
  docker compose -f docker-compose.prod.yml -f docker-compose.test.yml build xiaozhi-web
  docker compose -f docker-compose.prod.yml -f docker-compose.test.yml up -d --no-deps xiaozhi-web
  docker restart xiaozhi-prod-xiaozhi-edge-router-1
  ```
- Sau build, verify CSS vào container:
  ```bash
  docker exec xiaozhi-prod-xiaozhi-web-1 sh -c 'grep -rl "studio-sidebar" /usr/share/nginx/html/css/ | head -1'
  ```
- KHÔNG commit khi anh Khanh chưa duyệt bằng mắt trên `localhost:8002`.

---

## Đợt 0 — Nền móng

### Task 1: Dọn nhánh — commit phần login dở, tạo nhánh mới

**Covers:** [S3] (chuẩn bị nhánh)

**Files:**
- Modify: không (chỉ git)

- [ ] **Step 1: Commit riêng phần login đang dở trên `fix/live-test-websocket`**

Chỉ add đúng file login, KHÔNG add file rác ở gốc repo (`BANNER.png`, `Login – 1.png`, `logo.svg`, `icon google.svg`, `measure*.py`, `test_dom.js`, `deploy/data/`):

```bash
cd /home/khanhnq/device_esp32_oriagent
git status --short   # xác nhận chỉ auth.scss bị modified
git add main/manager-web/src/views/auth.scss
git commit -m "fix(ui): can giua chu trong o nhap man login/register theo mau"
```

- [ ] **Step 2: Tạo nhánh làm việc**

```bash
git checkout -b feat/ui-studio-redesign
git branch --show-current   # kỳ vọng: feat/ui-studio-redesign
```

### Task 2: Token file `studio.scss`

**Covers:** [S3]

**Files:**
- Create: `main/manager-web/src/views/studio.scss`

- [ ] **Step 1: Tạo file token + class shell**

```scss
/* ============================================
   Studio design tokens & shared shell styles
   Reference: docs/compose/specs/assets/ui-studio/*.png
   Import bằng @import "./studio.scss" trong <style lang="scss" scoped>
   ============================================ */

/* ---------- Tokens ---------- */
$studio-accent: #08c45b;          /* xanh Oriagent */
$studio-accent-soft: #dff5e8;     /* nền xanh nhạt cho item active / pill chọn model */
$studio-text: #313133;            /* chữ chính */
$studio-text-sub: #707070;        /* chữ phụ */
$studio-black: #1a1a1c;           /* pill đen (nút chính) */
$studio-page-bg: #e9e9e9;         /* nền ngoài cùng (xám) */
$studio-panel-bg: #ffffff;        /* panel nổi */
$studio-soft-bg: #f7f7f7;         /* nền phụ trong panel */
$studio-border: #eeeeee;
$studio-radius-panel: 18px;       /* bo góc panel nổi */
$studio-radius-pill: 999px;
$studio-gap: 12px;                /* khe giữa các panel nổi */
$studio-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);

/* ---------- Panel nổi ---------- */
@mixin studio-panel {
  background: $studio-panel-bg;
  border-radius: $studio-radius-panel;
  box-shadow: $studio-shadow;
  box-sizing: border-box;
}

/* ---------- Pill đen (nút hành động chính) ---------- */
@mixin studio-black-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 36px;
  padding: 0 18px;
  border: none;
  border-radius: $studio-radius-pill;
  background: linear-gradient(180deg, #333335 0%, #1a1a1c 100%);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  user-select: none;
  &:hover { background: linear-gradient(180deg, #3a3a3c 0%, #202022 100%); }
  &:active { background: #111112; }
}

/* ---------- Pill xanh nhạt (giá trị được chọn) ---------- */
@mixin studio-soft-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  border-radius: $studio-radius-pill;
  background: $studio-accent-soft;
  color: $studio-text;
  padding: 0 14px;
  height: 40px;
}
```

- [ ] **Step 2: Build thử cục bộ nhanh (webpack chấp nhận file)**

File chưa được import ở đâu nên chỉ cần kiểm cú pháp khi build Task 4. Không commit riêng — commit chung ở Task 4.

### Task 3: Component `StudioLayout.vue`

**Covers:** [S3]

**Files:**
- Create: `main/manager-web/src/components/StudioLayout.vue`

- [ ] **Step 1: Viết component shell hoàn chỉnh**

Cấu trúc đúng ảnh mẫu: sidebar panel nổi (logo + icon thu gọn tĩnh → pill "Agent Builder" → nhóm AgentOS/AgentCore/AgentSetting → đáy: Guide Document + My Account), slot nội dung. Knowledge/Integration hiển thị nhưng disabled (S3 — quyết định để trống). My Account tái dùng dropdown tài khoản: dựng menu tối thiểu điều hướng tới route sẵn có (không gọi API mới).

```vue
<template>
  <div class="studio-shell">
    <aside class="studio-sidebar">
      <div class="studio-sidebar-top">
        <div class="studio-logo-row">
          <img src="@/assets/auth/logo.svg" alt="Oriagent" class="studio-logo" />
          <i class="el-icon-copy-document studio-collapse-icon"></i>
        </div>
        <div class="studio-context-pill">
          <i class="el-icon-cpu"></i>
          <span>{{ contextLabel }}</span>
        </div>

        <div class="studio-nav-group">
          <div class="studio-group-label">AgentOS</div>
          <div class="studio-nav-item" :class="{ active: active === 'agents' }" @click="go('/home')">
            <i class="el-icon-user"></i><span>Robot Agent</span>
          </div>
        </div>

        <div class="studio-nav-group">
          <div class="studio-group-label">AgentCore</div>
          <div class="studio-nav-item" :class="{ active: active === 'models' }" @click="go('/model-config')">
            <i class="el-icon-refresh"></i><span>Model AI</span>
          </div>
          <div class="studio-nav-item disabled"><i class="el-icon-notebook-2"></i><span>Knowledge</span></div>
          <div class="studio-nav-item disabled"><i class="el-icon-connection"></i><span>Integration</span></div>
        </div>

        <div class="studio-nav-group">
          <div class="studio-group-label">AgentSetting</div>
          <div class="studio-nav-item" :class="{ active: active === 'settings' }" @click="go('/params-management')">
            <i class="el-icon-setting"></i><span>Thiết lập</span>
          </div>
        </div>
      </div>

      <div class="studio-sidebar-bottom">
        <div class="studio-guide-btn" @click="openGuide">
          <i class="el-icon-reading"></i><span>Guide Document</span>
        </div>
        <el-dropdown trigger="click" class="studio-account" @command="onAccount">
          <div class="studio-account-pill">
            <i class="el-icon-user"></i><span>My Account</span>
            <i class="el-icon-sort studio-account-caret"></i>
          </div>
          <el-dropdown-menu slot="dropdown">
            <el-dropdown-item command="logout">{{ $t('header.logout') || 'Đăng xuất' }}</el-dropdown-item>
          </el-dropdown-menu>
        </el-dropdown>
      </div>
    </aside>

    <main class="studio-content">
      <slot />
    </main>
  </div>
</template>

<script>
import { goToPage } from "@/utils";

export default {
  name: "StudioLayout",
  props: {
    active: { type: String, default: "agents" },        // agents | models | settings
    contextLabel: { type: String, default: "Agent Builder" },
  },
  methods: {
    go(path) {
      if (this.$route.path !== path) goToPage(path);
    },
    openGuide() {
      window.open("https://oriagent.com", "_blank");
    },
    onAccount(cmd) {
      if (cmd === "logout") {
        this.$store.commit("clearAuth");
        goToPage("/login");
      }
    },
  },
};
</script>

<style lang="scss" scoped>
@import "@/views/studio.scss";

.studio-shell {
  display: flex;
  gap: $studio-gap;
  min-height: 100vh;
  padding: $studio-gap;
  background: $studio-page-bg;
  box-sizing: border-box;
}

.studio-sidebar {
  @include studio-panel;
  width: 250px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 18px 14px;
  position: sticky;
  top: $studio-gap;
  height: calc(100vh - #{$studio-gap * 2});
  overflow-y: auto;
}

.studio-logo-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 6px 14px;
  .studio-logo { height: 30px; }
  .studio-collapse-icon { color: $studio-text-sub; font-size: 14px; }
}

.studio-context-pill {
  @include studio-soft-pill;
  background: $studio-soft-bg;
  height: 36px;
  font-size: 13px;
  font-weight: 600;
  color: $studio-text;
  margin-bottom: 18px;
}

.studio-group-label {
  font-size: 12px;
  color: $studio-text-sub;
  margin: 14px 6px 6px;
}

.studio-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 10px;
  font-size: 14px;
  color: $studio-text;
  cursor: pointer;

  &:hover:not(.disabled) { background: $studio-soft-bg; }
  &.active {
    background: $studio-accent-soft;
    color: darken($studio-accent, 8%);
    font-weight: 600;
  }
  &.disabled { color: #b5b5b5; cursor: default; }
}

.studio-sidebar-bottom {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.studio-guide-btn {
  @include studio-black-pill;
  width: 100%;
  height: 38px;
}

.studio-account { width: 100%; }
.studio-account-pill {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 38px;
  padding: 0 14px;
  border: 1px solid $studio-border;
  border-radius: $studio-radius-pill;
  font-size: 13px;
  color: $studio-text;
  cursor: pointer;
  box-sizing: border-box;
  .studio-account-caret { margin-left: auto; }
}

.studio-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: $studio-gap;
}
</style>
```

Lưu ý khi thi công: kiểm tra tên mutation logout thật trong `src/store` (`clearAuth` chỉ là dự kiến — tìm mutation mà `HeaderBar.vue` đang dùng để đăng xuất và dùng đúng tên đó; nếu HeaderBar dùng method khác thì copy nguyên cách gọi của HeaderBar).

### Task 4: Build xác nhận nền móng không phá gì

**Covers:** [S3], [S7]

- [ ] **Step 1: Prune + build + up (lệnh chuẩn ở đầu plan)**
- [ ] **Step 2: Verify**: mở `localhost:8002` — login OK, `/home` vẫn giao diện CŨ (chưa màn nào dùng shell), các màn admin vào bình thường.
- [ ] **Step 3: Commit**

```bash
git add main/manager-web/src/views/studio.scss main/manager-web/src/components/StudioLayout.vue
git commit -m "feat(ui): them StudioLayout shell + studio.scss tokens (chua man nao dung)"
```

---

## Đợt 1 — Màn Home (artboard 28)

### Task 5: `home.vue` — bọc shell + hàng search/Create

**Covers:** [S4]

**Files:**
- Modify: `main/manager-web/src/views/home.vue` (template + style; script GIỮ NGUYÊN)

- [ ] **Step 1: Template — bọc `StudioLayout`, thay hero banner bằng hàng topbar**

Khung mới (giữ nguyên toàn bộ logic binding sẵn có — `search`, `showHistory`, `searchHistory`, `isSearching`, `isLoading`, `devices`, `featureStatus`, các handler):

```vue
<template>
  <StudioLayout active="agents" contextLabel="Agent Builder">
    <div class="studio-topbar">
      <div class="studio-search-wrap">
        <!-- GIỮ NGUYÊN el-input search + history dropdown hiện có, chỉ đổi class bao ngoài -->
        <el-input v-model="search" :placeholder="'Tìm kiếm Robot Agent'" class="studio-search-input"
          @focus="showHistory = true" @blur="hideHistoryDelayed" @keyup.enter.native="handleSearch" clearable>
          <i slot="prefix" class="el-icon-search"></i>
        </el-input>
        <!-- search-history-dropdown: bê nguyên khối cũ vào đây -->
      </div>
      <div class="studio-create-btn" @click="showAddDialog">
        <i class="el-icon-plus"></i><span>Create Robot Agent</span>
      </div>
    </div>

    <div class="studio-board">
      <!-- GIỮ NGUYÊN: search-status, skeleton loop, DeviceItem loop, empty state, dialogs, footer -->
    </div>
  </StudioLayout>
</template>
```

Quy tắc chuyển đổi (làm bằng Edit từng khối, không viết lại cả file):
1. Import + đăng ký `StudioLayout` trong script (chỉ THÊM import/`components:` — được phép vì không đổi logic).
2. Bê nguyên các khối `search-history-dropdown`, `search-status`, skeleton, `DeviceItem` loop, dialog, footer vào vị trí mới — **không đổi binding nào**.
3. Xóa khối hero `add-device`/`add-device-bg` (nút add chuyển thành `.studio-create-btn` gọi đúng `showAddDialog`).
4. Chú ý: hàm blur của search cũ tên gì dùng đúng tên đó (đọc script trước khi edit — KHÔNG bịa tên `hideHistoryDelayed` nếu code thật khác).

- [ ] **Step 2: Style trong `home.vue`**

```scss
@import "./studio.scss";

.studio-topbar {
  @include studio-panel;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 14px;
  padding: 12px 16px;
}
.studio-search-wrap { position: relative; width: 320px; }
.studio-search-input ::v-deep .el-input__inner {
  border-radius: 999px;
  background: $studio-soft-bg;
  border: 1px solid $studio-border;
  height: 38px;
}
.studio-create-btn { @include studio-black-pill; }
.studio-board {
  @include studio-panel;
  flex: 1;
  padding: 20px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  align-content: start;
}
```

Xóa các style cũ chỉ phục vụ hero banner; style nào skeleton/search-status còn dùng thì giữ.

### Task 6: `DeviceItem.vue` — card theo mẫu

**Covers:** [S4]

**Files:**
- Modify: `main/manager-web/src/components/DeviceItem.vue` (template + style; script GIỮ NGUYÊN)

- [ ] **Step 1: Template card mới** (giữ đủ: click card, delete, tooltip info, LLM/TTS model + voice, device count, History tag, last time, tags firmware)

```vue
<template>
  <div class="studio-agent-card" @click="handleCardClick">
    <div class="card-head">
      <div class="card-avatar"><i class="el-icon-service"></i></div>
      <div class="card-title-block">
        <el-tooltip :content="device.agentName" placement="top" effect="light">
          <div class="card-name">{{ device.agentName }}</div>
        </el-tooltip>
        <div class="card-sub">Agent</div>
      </div>
      <div class="card-actions">
        <img src="@/assets/home/delete.png" class="card-icon" @click.stop="handleDelete" />
        <el-tooltip effect="light" :content="device.systemPrompt" placement="top" popper-class="custom-tooltip">
          <img src="@/assets/home/info.png" class="card-icon" />
        </el-tooltip>
      </div>
    </div>

    <div class="card-chips">
      <div class="chip"><span class="chip-label">TTS</span><span class="chip-value">{{ device.ttsModelName }}</span></div>
      <div class="chip"><span class="chip-label">LLM</span><span class="chip-value">{{ device.llmModelName }}</span></div>
      <div class="chip"><span class="chip-label">Voice</span><span class="chip-value">{{ device.ttsVoiceName }}</span></div>
    </div>

    <div class="card-foot">
      <span class="foot-badge"><i class="el-icon-monitor"></i> {{ device.deviceCount || 0 }} {{ $t('roleConfig.tabDevice') }}</span>
      <span v-if="device.memModelId !== 'Memory_nomem'" class="foot-badge"><i class="el-icon-chat-dot-round"></i> History</span>
      <span class="foot-time">{{ formattedLastConnectedTime }}</span>
    </div>
    <el-tooltip v-if="tags.length" :content="tags.join()" placement="top" effect="light">
      <div class="card-tags">{{ tags.join() }}</div>
    </el-tooltip>
  </div>
</template>
```

(Mẫu vẽ chip STT nhưng payload card hiện chỉ có `llmModelName`/`ttsModelName`/`ttsVoiceName` — theo S4: không có dữ liệu STT thì không chế thêm; dùng chip Voice hiển thị giọng, đúng dữ liệu thật. Ghi chú này báo lại anh khi nghiệm thu.)

- [ ] **Step 2: Style card** (thay style cũ tương ứng)

```scss
@import "@/views/studio.scss";

.studio-agent-card {
  @include studio-panel;
  border: 1px solid $studio-border;
  padding: 14px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 12px;
  &:hover { box-shadow: 0 4px 14px rgba(0,0,0,0.08); }
}
.card-head { display: flex; align-items: center; gap: 10px; }
.card-avatar {
  width: 42px; height: 42px; border-radius: 50%;
  background: $studio-accent-soft; color: darken($studio-accent, 8%);
  display: flex; align-items: center; justify-content: center; font-size: 20px;
  flex-shrink: 0;
}
.card-title-block { min-width: 0; flex: 1; }
.card-name { font-weight: 700; font-size: 15px; color: $studio-text; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card-sub { font-size: 12px; color: $studio-text-sub; }
.card-actions { display: flex; gap: 8px; .card-icon { width: 18px; height: 18px; } }
.card-chips {
  display: flex; gap: 8px;
  .chip {
    flex: 1; background: $studio-soft-bg; border-radius: 10px; padding: 6px 8px;
    display: flex; flex-direction: column; gap: 2px; min-width: 0;
    .chip-label { font-size: 11px; color: $studio-text-sub; }
    .chip-value { font-size: 12px; font-weight: 600; color: $studio-text; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  }
}
.card-foot { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  .foot-badge { background: $studio-soft-bg; border-radius: 999px; padding: 3px 10px; font-size: 12px; color: $studio-text-sub; }
  .foot-time { margin-left: auto; font-size: 11px; color: $studio-text-sub; }
}
.card-tags { font-size: 11px; color: $studio-text-sub; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
```

### Task 7: Build + nghiệm thu Đợt 1

**Covers:** [S4], [S7]

- [ ] **Step 1: Prune + build + up + restart edge-router (lệnh chuẩn)**
- [ ] **Step 2: Tự kiểm:** grep `studio-sidebar` trong CSS container; mở `/home`: sidebar hiện, card mới, search hoạt động, tạo/xóa agent OK, click card → AgentConfig; màn cũ (`/user-management`) không lệch.
- [ ] **Step 3: BÁO ANH DUYỆT bằng mắt, so với `home-28.png`. Chưa duyệt = chưa commit.**
- [ ] **Step 4: Commit sau duyệt**

```bash
git add main/manager-web/src/views/home.vue main/manager-web/src/components/DeviceItem.vue
git commit -m "feat(ui): man Home theo mau studio 28 (sidebar + card agent)"
```

---

## Đợt 2 — Màn Model AI (artboard 31)

### Task 8: `ModelConfig.vue` — bọc shell + menu nhóm trái

**Covers:** [S5]

**Files:**
- Modify: `main/manager-web/src/views/ModelConfig.vue`

- [ ] **Step 1: Đọc script trước** — xác định cơ chế đổi `activeTab` hiện tại (route query `?tab=` + watcher). Menu mới phải dùng ĐÚNG cơ chế đó (vd `this.$router.push({ query: { tab } })` nếu code thật đang vậy).
- [ ] **Step 2: Template**: bọc `StudioLayout active="models"`; nội dung = 2 panel:

```vue
<StudioLayout active="models" contextLabel="Agent Builder">
  <div class="studio-model-wrap">
    <aside class="studio-cat-panel">
      <div v-for="cat in catList" :key="cat.tab"
           class="studio-cat-item" :class="{ active: activeTab === cat.tab }"
           @click="switchTab(cat.tab)">
        <i :class="cat.icon"></i><span>{{ cat.label }}</span>
        <i v-if="activeTab === cat.tab" class="el-icon-right cat-arrow"></i>
      </div>
    </aside>
    <section class="studio-model-panel">
      <!-- bảng + phân trang + nút batch hiện có, restyle ở Task 9 -->
    </section>
  </div>
</StudioLayout>
```

`catList` là mảng tĩnh khai báo trong `data()` (THÊM data tĩnh — không phải logic): 6 mục `llm/vad/asr/tts/memory/intent` với nhãn tiếng Việt như mẫu (*Mô hình ngôn ngữ (LLM)*, *Phát hiện giọng nói (VAD)*, *Giọng nói thành văn bản (STT)*, *Văn bản thành giọng nói (TTS)*, *Trí nhớ (Memory)*, *Ý định (Intent)*) — đối chiếu key tab thật trong script (`asr` hay `stt`) trước khi viết. `switchTab` = method sẵn có nếu có, không có thì dùng đúng câu lệnh router mà watcher đang nghe.

- [ ] **Step 3: Style 2 panel** (panel trái ~260px `@include studio-panel`, item active nền `$studio-accent-soft` + mũi tên; panel phải `@include studio-panel` flex:1).

### Task 9: Gộp provider trong 1 bảng (ngoại lệ S2 đã duyệt)

**Covers:** [S5]

**Files:**
- Modify: `main/manager-web/src/views/ModelConfig.vue`

Kỹ thuật: giữ NGUYÊN 1 `el-table` (không vỡ selection/batch/pagination). Chèn "hàng nhóm provider" bằng computed + span-method — toàn bộ là THÊM MỚI:

- [ ] **Step 1: Thêm computed `providerGroupedRows`** — từ danh sách trang hiện tại (biến data mà `:data` của bảng đang dùng, ví dụ `modelList` — đọc tên thật trước), chèn phần tử đánh dấu nhóm:

```js
// THÊM vào computed: (không sửa gì khác)
providerGroupedRows() {
  const rows = [];
  let lastProvider = null;
  for (const m of this.modelList) {           // dùng đúng tên biến thật
    const p = m.providerName || m.provideCode || "Khác";  // dùng đúng field thật
    if (p !== lastProvider) {
      rows.push({ __groupHeader: true, __provider: p });
      lastProvider = p;
    }
    rows.push(m);
  }
  return rows;
},
```

- [ ] **Step 2: Thêm 2 method mới** (span full width cho hàng nhóm + chặn selection hàng nhóm):

```js
// THÊM methods mới:
modelSpanMethod({ row, columnIndex }) {
  if (row.__groupHeader) {
    return columnIndex === 1 ? [1, 7] : [0, 0];   // 7 = tổng số cột thật, đếm lại khi làm
  }
  return [1, 1];
},
groupRowSelectable(row) {
  return !row.__groupHeader;
},
```

- [ ] **Step 3: Template bảng**: `:data="providerGroupedRows"`, `:span-method="modelSpanMethod"`, cột selection thêm `:selectable="groupRowSelectable"`; trong cột tên, render header nhóm:

```vue
<template slot-scope="scope">
  <div v-if="scope.row.__groupHeader" class="studio-provider-head">
    <span class="provider-name">{{ scope.row.__provider }}</span>
  </div>
  <span v-else class="model-name">{{ scope.row.modelName }}</span>
</template>
```

Các cột khác thêm `v-if="!scope.row.__groupHeader"` trong slot để hàng nhóm không render switch/nút. Nút API-KEY/Setup trong header nhóm của mẫu KHÔNG làm (không có tính năng per-provider thật).

- [ ] **Step 4: Restyle bảng** — `::v-deep`: bỏ border cell, hàng cao 52px, hàng nhóm nền `$studio-soft-bg` bo góc, switch `active-color="#08c45b"`, cụm sửa/nhân bản/xóa đổi thành icon-button tròn. Nút "Thêm mới model" (nút add sẵn có) restyle thành link/pill cuối panel như mẫu.
- [ ] **Step 5: Test lại đủ theo S5**: đổi 6 nhóm, thêm/sửa/nhân bản/xóa model, switch enable, đặt default, chọn hàng loạt + xóa hàng loạt (xác nhận hàng nhóm không chọn được), phân trang, tìm kiếm, dialog giọng TTS.

### Task 10: Build + nghiệm thu Đợt 2

**Covers:** [S5], [S7]

- [ ] **Step 1: Prune + build + up + restart edge-router**
- [ ] **Step 2: Tự kiểm checklist Step 5 Task 9 trên `localhost:8002/#/model-config`; so `model-ai-31.png`; kiểm màn cũ không lệch.**
- [ ] **Step 3: BÁO ANH DUYỆT. Chưa duyệt = chưa commit.**
- [ ] **Step 4: Commit sau duyệt**

```bash
git add main/manager-web/src/views/ModelConfig.vue
git commit -m "feat(ui): man Model AI theo mau studio 31 (menu nhom + gop provider)"
```

---

## Đợt 3 — Màn Thiết lập Robot (artboard 29/30)

### Task 11: `AgentConfig.vue` + `AgentConfigTabs.vue` — shell + header tab pill

**Covers:** [S6]

**Files:**
- Modify: `main/manager-web/src/views/AgentConfig.vue` (bọc StudioLayout)
- Modify: `main/manager-web/src/components/AgentConfigTabs.vue` (restyle template/style)

- [ ] **Step 1: `AgentConfig.vue`**: bọc toàn bộ template hiện tại trong `<StudioLayout active="agents" contextLabel="Agent Robot Builder">…</StudioLayout>`; thêm import + `components`. KHÔNG đổi gì khác.
- [ ] **Step 2: `AgentConfigTabs.vue`**: giữ nguyên props/emits (`input`/`save`/`back`, `saving`); restyle:
  - Header bọc trong bar `@include studio-panel` (bo góc, nền trắng).
  - Nút back: tròn trắng viền, chỉ icon mũi tên (bỏ chữ "Agents").
  - Tab: pill — active nền đen chữ trắng (như mẫu), inactive trong suốt chữ `$studio-text`; giữ icon.
  - Nút save: đổi thành pill đen, nhãn qua i18n key hiện có; sửa bản dịch `roleConfig.saveConfig` trong `src/i18n/locales/vi.js` thành "Xuất bản" (chỉ file vi; các ngôn ngữ khác giữ).
- [ ] **Step 3: Thứ tự tab giữ nguyên logic, chỉ đổi thứ tự HIỂN THỊ trong mảng `tabs` (data tĩnh) cho khớp mẫu: setup → history → overview → device.**

### Task 12: `RoleConfigSection.vue` — restyle 3 panel theo mẫu

**Covers:** [S6]

**Files:**
- Modify: `main/manager-web/src/components/RoleConfigSection.vue` (template class + style; script GIỮ NGUYÊN — trừ 0 thay đổi logic)

Cấu trúc 3 panel ĐÃ CÓ SẴN: `.config-panel` (form) / `.system-prompt-panel` (Instructions) / `.preview-panel` (Testing). Việc là restyle:

- [ ] **Step 1: `.dashboard-layout`** → grid 3 cột `minmax(0,1fr)` gap `$studio-gap`; dưới 1400px xếp dọc.
- [ ] **Step 2: Form panel** (đối chiếu `agent-config-30-idle.png`):
  - `field-label-premium`: icon + chữ đậm 14px `$studio-text`.
  - Pill chọn model LLM: hàng trắng viền `$studio-border` (icon + tên + tag "Chat" nhỏ).
  - API Key input: nền `$studio-accent-soft`, bo pill.
  - VAD/STT select: `@include studio-soft-pill`.
  - Khối TTS (`tts-premium-card`): viền 1.5px `$studio-accent`, nền `$studio-accent-soft` nhạt, bên trong pill model trắng + 2 select Language/Voice Type trắng có nhãn nhỏ phía trên.
  - Khối câu đệm (`filler-premium-card`): nền `$studio-accent-soft`, pill "Thời gian chờ (ms)" trắng, textarea trắng bo 12px.
- [ ] **Step 3: Testing panel** (`preview-panel`) — 2 trạng thái từ state `isLiveTesting` SẴN CÓ:
  - Idle (`!isLiveTesting`): giữa panel vòng tròn trắng đường kính ~240px đổ bóng, bên trong icon waveform tĩnh (SVG inline vài vạch), dưới là nút tròn xanh `$studio-accent` icon phone (gọi `toggleLiveTest` sẵn có).
  - Đang gọi (`isLiveTesting`): thanh trên = pill trắng chứa waveform tĩnh + chữ "Đang hoạt động" + nút tròn đỏ `#e74c3c` icon ngắt (gọi handler tắt sẵn có); giữ nguyên `live-iframe` bên dưới (iframe chính là khung chat thật).
  - Header panel: "Testing" + icon; đáy: giữ bar hiện có restyle thành pill "Nhập tin nhắn…" nếu iframe không tự chứa input — nếu iframe đã có input riêng thì KHÔNG chế thêm (S6: không chế logic).
- [ ] **Step 4: Instructions panel** (`system-prompt-panel`): header "Instructions" + textarea lớn; chân panel trái `Character: {{ (form.prompt || '').length }}` (template-only — dùng đúng tên field thật của textarea); "Token prompt" và nút "Tạo tự động" KHÔNG làm (không có tính năng thật). Panel này có `v-if` điều kiện sẵn — giữ nguyên điều kiện, khi ẩn thì grid tự còn 2 cột.

### Task 13: Build + nghiệm thu Đợt 3 + tổng kết

**Covers:** [S6], [S7], [S8]

- [ ] **Step 1: Prune + build + up + restart edge-router**
- [ ] **Step 2: Tự kiểm:** vào agent bất kỳ: lưu cấu hình OK, 4 tab chuyển OK, test chat live bật/tắt OK (2 trạng thái đúng ảnh), dialogs (plugins/context/add device) mở OK, so `agent-config-30-idle.png` + `agent-config-29-incall.png`.
- [ ] **Step 3: Hồi quy nhanh toàn app:** login → home → click card → config → back → model-config → màn cũ (`/user-management`, `/ota-management`) không lệch.
- [ ] **Step 4: BÁO ANH DUYỆT. Chưa duyệt = chưa commit.**
- [ ] **Step 5: Commit sau duyệt**

```bash
git add main/manager-web/src/views/AgentConfig.vue main/manager-web/src/components/AgentConfigTabs.vue main/manager-web/src/components/RoleConfigSection.vue main/manager-web/src/i18n/locales/vi.js
git commit -m "feat(ui): man Thiet lap Robot theo mau studio 29/30 (3 cot + tab pill)"
```

- [ ] **Step 6: Báo cáo tổng kết cho anh: 4 commit của 4 đợt, các điểm lệch mẫu có chủ đích (chip Voice thay STT, không có API-KEY/Setup per-provider, không có Tạo tự động/Token prompt, Knowledge/Integration để trống).**
