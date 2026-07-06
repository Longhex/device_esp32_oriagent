<template>
  <div class="agent-config-header">
    <div class="top-nav-bar">
      <!-- Left: Back Button -->
      <div class="header-left">
        <div class="back-btn" @click="$emit('back')">
          <i class="el-icon-arrow-left"></i>
        </div>
      </div>

      <!-- Center: Segmented Control Navigation -->
      <div class="navigation-bar">
        <div class="segmented-control">
          <div 
            v-for="tab in tabs" 
            :key="tab.id"
            class="segmented-tab" 
            :class="{ active: value === tab.id }" 
            @click="$emit('input', tab.id)"
          >
            <img 
              :src="getIconPath(tab.iconName)" 
              class="tab-icon-img" 
              :class="{ 'active-icon': value === tab.id }"
            />
            <span class="tab-label">{{ $t(tab.labelKey) }}</span>
          </div>
        </div>
      </div>

      <!-- Right: Save Action -->
      <div class="header-actions">
        <slot name="extra-actions"></slot>
        <el-button type="primary" size="medium" class="main-save-btn" @click="$emit('save')" :loading="saving">
            {{ $t('roleConfig.saveConfig') }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: "AgentConfigTabs",
  props: {
    value: { type: String, required: true },
    saving: { type: Boolean, default: false },
    agentName: { type: String, default: 'Agent' }
  },
  data() {
    return {
      tabs: [
        { id: 'setup', labelKey: 'roleConfig.tabSetup', iconName: 'studio_agent.svg' },
        { id: 'history', labelKey: 'roleConfig.tabHistory', iconName: 'history.svg' },
        { id: 'overview', labelKey: 'roleConfig.tabOverview', iconName: 'overview.svg' },
        { id: 'device', labelKey: 'roleConfig.tabDevice', iconName: 'api_access.svg' }
      ]
    };
  },
  methods: {
    getIconPath(name) {
      try {
        return require(`@/assets/dashboard/${name}`);
      } catch (e) {
        return '';
      }
    }
  }
};
</script>

<style lang="scss" scoped>
@import "@/views/studio.scss";

.agent-config-header {
  @include studio-panel;
  position: sticky;
  top: 0;
  z-index: 1000;
  padding: 10px 20px;
  display: flex;
  flex-direction: column;
}

.top-nav-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.header-left {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid $studio-border;
  background: $studio-panel-bg;
  color: $studio-text;
  font-size: 16px;
  cursor: pointer;
  transition: background 0.2s;

  &:hover {
    background: $studio-soft-bg;
  }
}

.navigation-bar {
  display: flex;
  justify-content: flex-start;
  flex: 1;
  margin-left: 16px;
}

.segmented-control {
  display: inline-flex;
  align-items: center;
  background: $studio-soft-bg;
  padding: 4px;
  border-radius: $studio-radius-pill;
  gap: 4px;
}

.segmented-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 22px;
  border-radius: $studio-radius-pill;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  white-space: nowrap;

  .tab-icon-img {
    width: 16px;
    height: 16px;
    opacity: 0.6;
    transition: all 0.2s;

    &.active-icon {
      filter: brightness(0) invert(1);
      opacity: 1;
    }
  }

  .tab-label {
    font-size: 13px;
    font-weight: 700;
    color: $studio-text-sub;
    transition: all 0.2s;
  }

  &:hover:not(.active) {
    .tab-label { color: $studio-text; }
    .tab-icon-img { opacity: 0.9; }
  }

  &.active {
    background: linear-gradient(180deg, #333335 0%, $studio-black 100%);
    .tab-label { color: white; }
  }

  @media (max-width: 1024px) {
    padding: 8px 14px;
    .tab-label { display: none; }
  }
}

.header-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex: 0 0 auto;
}

.main-save-btn {
  @include studio-black-pill;
  height: 40px;
  padding: 0 22px;
  border: none;
  font-weight: 800;
  font-size: 13px;
  box-shadow: none;

  &:hover {
    background: linear-gradient(180deg, #3a3a3c 0%, #202022 100%);
  }
}
</style>
