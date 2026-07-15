<template>
  <div class="studio-shell">
    <aside class="studio-sidebar">
      <!-- Logo nằm NGOÀI .studio-sidebar-top: vùng đó cuộn, để trong thì logo trôi mất -->
      <div class="studio-sidebar-head">
        <div class="studio-logo-row">
          <img src="@/assets/auth/logo.svg" alt="Oriagent" class="studio-logo" />
          <!-- TODO: icon thu gọn hiển thị tĩnh, chức năng làm sau -->
          <i class="el-icon-copy-document studio-collapse-icon"></i>
        </div>
      </div>
      <div class="studio-sidebar-top">
        <div class="studio-context-pill">
          <span class="studio-ic studio-ic--agent-builder"></span>
          <span>{{ contextLabel }}</span>
        </div>

        <div class="studio-nav-group">
          <div class="studio-group-label">AgentOS</div>
          <div class="studio-nav-item" :class="{ active: active === 'agents' }" @click="go('/home')">
            <span class="studio-ic studio-ic--robot-agent"></span><span>Robot Agent</span>
          </div>
        </div>

        <div class="studio-nav-group">
          <div class="studio-group-label">AgentCore</div>
          <div class="studio-nav-item" :class="{ active: active === 'models' }" @click="go('/model-config')">
            <span class="studio-ic studio-ic--model-ai"></span><span>Model AI</span>
          </div>
          <div class="studio-nav-item disabled"><span class="studio-ic studio-ic--knowledge"></span><span>Knowledge</span></div>
          <div class="studio-nav-item disabled"><span class="studio-ic studio-ic--integration"></span><span>Integration</span></div>
        </div>

        <div class="studio-nav-group">
          <div class="studio-group-label">AgentSetting</div>
          <div class="studio-nav-item" :class="{ active: active === 'settings' }" @click="go('/params-management')">
            <span class="studio-ic studio-ic--settings"></span><span>Thiết lập</span>
          </div>
        </div>
      </div>

      <div class="studio-sidebar-bottom">
        <!-- TODO: gắn link Guide Document khi có URL chính thức -->
        <div class="studio-guide-btn">
          <span class="studio-ic studio-ic--guide"></span><span>Guide Document</span>
        </div>
        <el-popover
          placement="top-start"
          trigger="click"
          popper-class="account-popover"
          :width="252"
          :visible-arrow="false"
        >
          <div class="account-menu">
            <div class="account-header">
              <span class="account-avatar">{{ userInitial }}</span>
              <div class="account-id">
                <div class="account-name">{{ userName }}</div>
                <div class="account-email" v-if="userEmail">{{ userEmail }}</div>
              </div>
            </div>

            <div class="account-block">
              <div class="account-ws-label">{{ $t('account.workspace') }}</div>
              <div class="account-ws-pill">
                <span class="account-ws-dot">{{ userInitial }}</span>
                <span class="account-ws-name">{{ $t('account.workspaceName') }}</span>
                <i class="el-icon-arrow-right account-ws-caret"></i>
              </div>
            </div>

            <div class="account-block">
              <div class="account-item" @click="settingsVisible = true">{{ $t('account.settings') }}</div>
              <div class="account-item">{{ $t('account.feedback') }}</div>
              <div class="account-item">{{ $t('account.community') }}</div>
              <div class="account-item">{{ $t('account.helpCenter') }}</div>
              <div class="account-item account-item--about">
                <span>{{ $t('account.about') }}</span>
                <span class="account-ver">
                  <span class="account-ver-num">{{ appVersion }}</span>
                  <span class="account-ver-dot"></span>
                </span>
              </div>
            </div>

            <div class="account-logout-row" @click="onLogout">
              <span>{{ $t('header.logout') }}</span>
              <i class="el-icon-switch-button account-logout-ic"></i>
            </div>
          </div>

          <div slot="reference" class="studio-account-pill">
            <span class="studio-ic studio-ic--account"></span><span>My Account</span>
            <span class="studio-ic studio-ic--caret studio-account-caret"></span>
          </div>
        </el-popover>
      </div>
    </aside>

    <main class="studio-content">
      <slot />
    </main>

    <SettingsModal v-model="settingsVisible" />
  </div>
</template>

<script>
import { mapActions } from "vuex";
import { goToPage } from "@/utils";
import SettingsModal from "@/components/SettingsModal.vue";

export default {
  name: "StudioLayout",
  components: { SettingsModal },
  props: {
    active: {
      type: String,
      default: "agents", // agents | models | settings
      validator: (v) => ["agents", "models", "settings"].includes(v),
    },
    contextLabel: { type: String, default: "Agent Builder" },
  },
  data() {
    return { appVersion: "0.1.0", settingsVisible: false };
  },
  computed: {
    userInfo() {
      return this.$store.getters.getUserInfo || {};
    },
    userName() {
      return this.userInfo.username || "User";
    },
    userEmail() {
      return this.userInfo.email || "";
    },
    userInitial() {
      return (this.userName || "U").charAt(0).toUpperCase();
    },
  },
  methods: {
    ...mapActions(["logout"]),
    go(path) {
      if (this.$route.path !== path) goToPage(path);
    },
    async onLogout() {
      try {
        await this.logout();
      } catch (error) {
        this.$message.error(this.$t("message.error"));
      }
    },
  },
};
</script>

<style lang="scss" scoped>
@import "@/views/studio.scss";

/* Shell khoá cứng theo viewport: height (KHÔNG phải min-height) + overflow:hidden.
   min-height cũ làm shell phình theo nội dung -> trang cuộn toàn cục và khu vực phải
   thò xuống dưới đáy sidebar. Nội dung dài phải cuộn nội bộ trong .studio-content. */
.studio-shell {
  display: flex;
  gap: $studio-gap;
  height: 100vh;
  overflow: hidden;
  padding: $studio-gap;
  background: $studio-page-bg;
  box-sizing: border-box;
  text-align: left; /* ghi đè #app{text-align:center} — chữ studio canh trái như Figma */
}

.studio-sidebar {
  @include studio-panel;
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  padding: 10px 14px 18px; /* top 10 = khớp padding nav bar -> logo thẳng hàng tab */
  /* Không set height/sticky: shell đã khoá 100vh nên flex stretch cho sidebar đúng
     chiều cao khả dụng. Trước đây sticky + calc(100vh) chạy độc lập với shell nên
     hai bên lệch nhau (màn cao thì hụt, màn thấp thì thò). */
  min-height: 0;
  overflow: hidden; /* phần cuộn nằm ở .studio-sidebar-top */
}

/* Nhóm nav cuộn khi màn thấp; đáy (Guide/My Account) luôn ghim, không bị che */
/* Đầu sidebar: giữ cố định, không cuộn theo menu */
.studio-sidebar-head {
  flex-shrink: 0;
}

.studio-sidebar-top {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden; /* chặn thanh cuộn ngang vắt qua đáy nav (che Guide Document) */

  &::-webkit-scrollbar {
    width: 4px;
  }
  &::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.05);
    border-radius: 2px;
  }
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
  height: 38px;
  font-size: 16px;
  font-weight: 500;
  color: #5b5c65;
  margin-bottom: 18px;
}

.studio-group-label {
  font-size: 16px;
  font-weight: 400;
  color: #5b5c65;
  margin: 14px 6px 6px;
}

.studio-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid transparent; /* giữ box model đồng nhất khi active có viền */
  border-radius: 10px;
  font-size: 16px;
  font-weight: 500;
  color: #5b5c65;
  cursor: pointer;

  &:hover:not(.disabled) { background: $studio-soft-bg; }
  &.active {
    /* Figma: gradient #DFF9C0->#D0EFD7 + viền #707070 + radius 14 */
    background: linear-gradient(90deg, #dff9c0 0%, #d0efd7 100%);
    border-color: #707070;
    border-radius: 14px;
    color: #069d49; /* darken(#08c45b, 8%) */
    font-weight: 600;
  }
  &.disabled { color: #b5b5b5; cursor: default; }
}

/* Icon studio (SVG mẫu qua CSS mask -> to mau theo currentColor) */
.studio-ic {
  display: inline-block;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  background-color: currentColor;
  -webkit-mask-repeat: no-repeat;
  mask-repeat: no-repeat;
  -webkit-mask-position: center;
  mask-position: center;
  -webkit-mask-size: contain;
  mask-size: contain;
}
.studio-ic--agent-builder { -webkit-mask-image: url("~@/assets/studio/icons/ic-agent-builder.svg"); mask-image: url("~@/assets/studio/icons/ic-agent-builder.svg"); }
.studio-ic--robot-agent   { -webkit-mask-image: url("~@/assets/studio/icons/ic-robot-agent.svg");   mask-image: url("~@/assets/studio/icons/ic-robot-agent.svg"); }
.studio-ic--model-ai      { -webkit-mask-image: url("~@/assets/studio/icons/ic-model-ai.svg");      mask-image: url("~@/assets/studio/icons/ic-model-ai.svg"); }
.studio-ic--knowledge     { -webkit-mask-image: url("~@/assets/studio/icons/ic-knowledge.svg");     mask-image: url("~@/assets/studio/icons/ic-knowledge.svg"); }
.studio-ic--integration   { -webkit-mask-image: url("~@/assets/studio/icons/ic-integration.svg");   mask-image: url("~@/assets/studio/icons/ic-integration.svg"); }
.studio-ic--settings      { -webkit-mask-image: url("~@/assets/studio/icons/ic-settings.svg");      mask-image: url("~@/assets/studio/icons/ic-settings.svg"); }
.studio-ic--guide         { -webkit-mask-image: url("~@/assets/studio/icons/ic-guide.svg");         mask-image: url("~@/assets/studio/icons/ic-guide.svg"); }
.studio-ic--account       { -webkit-mask-image: url("~@/assets/studio/icons/ic-account.svg");       mask-image: url("~@/assets/studio/icons/ic-account.svg"); }
.studio-ic--caret         { width: 14px; -webkit-mask-image: url("~@/assets/studio/icons/ic-caret.svg"); mask-image: url("~@/assets/studio/icons/ic-caret.svg"); }

.studio-sidebar-bottom {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 12px;
}

.studio-guide-btn {
  @include studio-black-pill;
  width: 100%;
  height: 40px;
  font-size: 13px;
  justify-content: flex-start; /* icon + chữ canh trái như Figma (không canh giữa) */
  padding-left: 16px;
  /* Nút tĩnh cho tới khi có URL Guide Document chính thức */
  cursor: default;
  &:hover { background: linear-gradient(180deg, #333335 0%, $studio-black 100%); }
  &:active { background: linear-gradient(180deg, #333335 0%, $studio-black 100%); }
}

.studio-account { width: 100%; }
.studio-account-pill {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 40px;
  padding: 0 14px;
  border: 1px solid $studio-border;
  border-radius: $studio-radius-pill;
  font-size: 13px;
  font-weight: 700;
  color: #5b5c65;
  cursor: pointer;
  box-sizing: border-box;
  .studio-account-caret { margin-left: auto; }
}

/* min-height:0 để flex item co được dưới kích thước nội dung -> overflow-y mới ăn.
   Nội dung dài cuộn TRONG đây, không kéo dài shell (xem .studio-shell). */
.studio-content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: $studio-gap;
}

/* el-popover reference: kéo full-width như pill cũ */
.studio-sidebar-bottom ::v-deep .el-popover__reference-wrapper {
  display: block;
  width: 100%;
}
</style>

<style lang="scss">
/* Menu tài khoản: el-popover render ra body nên style KHÔNG dùng scoped */
.account-popover.el-popover {
  padding: 0;
  border-radius: 12px;
  border: 1px solid #eeeeee;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  overflow: hidden;
}
.account-popover .account-menu { font-size: 14px; color: #313133; }
.account-popover .account-header {
  display: flex; align-items: center; gap: 12px;
  padding: 13px 16px; border-bottom: 1px solid #f2f2f2;
}
.account-popover .account-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  background: #dff5e8; color: #069d49;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; flex-shrink: 0;
}
.account-popover .account-id { min-width: 0; }
.account-popover .account-name { font-size: 14px; color: #1d2939; font-weight: 500; word-break: break-all; }
.account-popover .account-email { font-size: 12px; color: #667085; word-break: break-all; }
.account-popover .account-block { padding: 6px 8px; border-bottom: 1px solid #f2f2f2; }
.account-popover .account-ws-label { font-size: 12px; font-weight: 500; color: #667085; padding: 4px 8px 6px; }
.account-popover .account-ws-pill {
  display: flex; align-items: center; gap: 8px;
  padding: 8px; border-radius: 8px; cursor: pointer;
}
.account-popover .account-ws-pill:hover { background: #f7f7f7; }
.account-popover .account-ws-dot {
  width: 24px; height: 24px; border-radius: 6px;
  background: #1a1a1c; color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; flex-shrink: 0;
}
.account-popover .account-ws-name { flex: 1; font-size: 13px; }
.account-popover .account-ws-caret { color: #98a2b3; font-size: 14px; }
.account-popover .account-item {
  display: flex; align-items: center; justify-content: space-between;
  height: 36px; padding: 0 12px; border-radius: 8px;
  color: #475467; cursor: pointer;
}
.account-popover .account-item:hover { background: #f7f7f7; }
.account-popover .account-ver { display: flex; align-items: center; gap: 6px; }
.account-popover .account-ver-num { font-size: 12px; color: #667085; }
.account-popover .account-ver-dot { width: 8px; height: 8px; border-radius: 50%; background: #12b76a; }
.account-popover .account-logout-row {
  display: flex; align-items: center; justify-content: space-between;
  height: 40px; padding: 0 16px; cursor: pointer; color: #475467;
}
.account-popover .account-logout-row:hover { background: #f7f7f7; }
.account-popover .account-logout-ic { color: #98a2b3; font-size: 14px; }
</style>
