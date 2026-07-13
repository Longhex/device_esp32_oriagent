<template>
  <StudioLayout active="settings" contextLabel="Agent Builder">
    <div class="studio-settings-wrap">
      <!-- Box 2: panel danh mục các trang quản lý (giống cat-panel của Model AI) -->
      <div class="studio-cat-panel">
        <div
          v-for="item in menu"
          :key="item.key"
          class="studio-cat-item"
          :class="{ active: activeKey === item.key }"
          @click="go(item.route)"
        >
          <i :class="item.icon"></i>
          <span>{{ $t(item.labelKey) }}</span>
          <span v-if="activeKey === item.key" class="studio-ic studio-ic--arrow studio-cat-arrow"></span>
        </div>
      </div>

      <!-- Box 3: nội dung trang tương ứng -->
      <slot />
    </div>
  </StudioLayout>
</template>

<script>
import StudioLayout from "@/components/StudioLayout.vue";
import { goToPage } from "@/utils";

export default {
  name: "SettingsLayout",
  components: { StudioLayout },
  props: {
    // key mục đang mở (highlight ở Box 2)
    activeKey: { type: String, default: "" },
  },
  data() {
    return {
      menu: [
        { key: "user", route: "/user-management", labelKey: "header.userManagement", icon: "el-icon-user" },
        { key: "ota", route: "/ota-management", labelKey: "header.otaManagement", icon: "el-icon-upload" },
        { key: "deviceMonitor", route: "/device-monitor", labelKey: "header.deviceMonitor", icon: "el-icon-monitor" },
        { key: "serial", route: "/serial-management", labelKey: "header.serialManagement", icon: "el-icon-document" },
        { key: "emoji", route: "/emoji-management", labelKey: "header.emojiManagement", icon: "el-icon-picture-outline" },
        { key: "provider", route: "/provider-management", labelKey: "header.providerManagement", icon: "el-icon-connection" },
        { key: "agentTemplate", route: "/agent-template-management", labelKey: "header.agentTemplate", icon: "el-icon-collection" },
        { key: "params", route: "/params-management", labelKey: "header.paramManagement", icon: "el-icon-setting" },
        { key: "dict", route: "/dict-management", labelKey: "header.dictManagement", icon: "el-icon-notebook-2" },
        { key: "server", route: "/server-side-management", labelKey: "header.serverSideManagement", icon: "el-icon-cpu" },
        { key: "feature", route: "/feature-management", labelKey: "header.featureManagement", icon: "el-icon-magic-stick" },
      ],
    };
  },
  methods: {
    go(route) {
      if (this.$route.path !== route) goToPage(route);
    },
  },
};
</script>

<style lang="scss" scoped>
@import "@/views/studio.scss";

.studio-settings-wrap {
  display: flex;
  gap: $studio-gap;
  align-items: stretch;
  flex: 1;
  min-height: 0;
}

.studio-cat-panel {
  @include studio-panel;
  width: 260px;
  flex-shrink: 0;
  padding: 14px 10px;
  box-sizing: border-box;
  overflow-y: auto;
}

.studio-cat-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 14px;
  color: $studio-text;
  cursor: pointer;
  transition: background 0.2s ease;

  i { font-size: 15px; }
  span:not(.studio-ic) { flex: 1; text-align: left; }
  .studio-cat-arrow { flex: none; font-size: 14px; }

  &:hover:not(.active) { background: $studio-soft-bg; }
  &.active { background: $studio-accent-soft; color: #069d49; font-weight: 600; }
  & + .studio-cat-item { margin-top: 4px; }
}
</style>
