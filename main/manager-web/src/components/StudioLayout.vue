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
        <!-- TODO: gắn link Guide Document khi có URL chính thức -->
        <div class="studio-guide-btn">
          <i class="el-icon-reading"></i><span>Guide Document</span>
        </div>
        <el-dropdown trigger="click" class="studio-account" @command="onAccount">
          <div class="studio-account-pill">
            <i class="el-icon-user"></i><span>My Account</span>
            <i class="el-icon-sort studio-account-caret"></i>
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
}

.studio-sidebar {
  @include studio-panel;
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 18px 14px;
  position: sticky;
  top: $studio-gap;
  height: calc(100vh - #{$studio-gap * 2});
  overflow-y: auto;

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
    color: #069d49; /* darken(#08c45b, 8%) */
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
