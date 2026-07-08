<template>
  <div class="studio-shell">
    <aside class="studio-sidebar">
      <div class="studio-sidebar-top">
        <div class="studio-logo-row">
          <img src="@/assets/auth/logo.svg" alt="Oriagent" class="studio-logo" />
          <!-- TODO: icon thu gọn hiển thị tĩnh, chức năng làm sau -->
          <i class="el-icon-copy-document studio-collapse-icon"></i>
        </div>
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
        <el-dropdown trigger="click" class="studio-account" @command="onAccount">
          <div class="studio-account-pill">
            <span class="studio-ic studio-ic--account"></span><span>My Account</span>
            <span class="studio-ic studio-ic--caret studio-account-caret"></span>
          </div>
          <el-dropdown-menu slot="dropdown">
            <el-dropdown-item command="logout">{{ $t('header.logout') }}</el-dropdown-item>
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
import { mapActions } from "vuex";
import { goToPage } from "@/utils";

export default {
  name: "StudioLayout",
  props: {
    active: {
      type: String,
      default: "agents", // agents | models | settings
      validator: (v) => ["agents", "models", "settings"].includes(v),
    },
    contextLabel: { type: String, default: "Agent Builder" },
  },
  methods: {
    ...mapActions(["logout"]),
    go(path) {
      if (this.$route.path !== path) goToPage(path);
    },
    async onAccount(cmd) {
      if (cmd === "logout") {
        try {
          await this.logout();
        } catch (error) {
          this.$message.error(this.$t("message.error"));
        }
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
  text-align: left; /* ghi đè #app{text-align:center} — chữ studio canh trái như Figma */
}

.studio-sidebar {
  @include studio-panel;
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  padding: 10px 14px 18px; /* top 10 = khớp padding nav bar -> logo thẳng hàng tab */
  position: sticky;
  top: $studio-gap;
  height: calc(100vh - #{$studio-gap * 2});
  overflow: hidden; /* phần cuộn nằm ở .studio-sidebar-top */
}

/* Nhóm nav cuộn khi màn thấp; đáy (Guide/My Account) luôn ghim, không bị che */
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

.studio-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: $studio-gap;
}
</style>
