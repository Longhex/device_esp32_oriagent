<template>
  <div class="agent-config-header">
    <div class="top-nav-bar">
      <!-- Left: Back Button -->
      <div class="header-left">
        <div class="back-btn" @click="$emit('back')">
          <span class="studio-ic studio-ic--back"></span>
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
            <span
              class="studio-ic tab-icon-img"
              :class="['studio-ic--' + tab.studioIc, { 'active-icon': value === tab.id }]"
            ></span>
            <span class="tab-label">{{ $t(tab.labelKey) }}</span>
          </div>
        </div>
      </div>

      <!-- Right: Save Action -->
      <div class="header-actions">
        <slot name="extra-actions"></slot>
        <el-button type="primary" size="medium" class="main-save-btn" @click="$emit('save')" :loading="saving">
            <span class="studio-ic studio-ic--publish save-btn-ic"></span>{{ $t('roleConfig.saveConfig') }}
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
        { id: 'setup', labelKey: 'roleConfig.tabSetup', studioIc: 'tab-setup' },
        { id: 'history', labelKey: 'roleConfig.tabHistory', studioIc: 'tab-history' },
        { id: 'overview', labelKey: 'roleConfig.tabOverview', studioIc: 'tab-overview' },
        { id: 'device', labelKey: 'roleConfig.tabDevice', studioIc: 'tab-device' }
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

  .studio-ic { width: 17px; height: 17px; }

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
    color: $studio-text-sub;
    transition: all 0.2s;
  }

  .tab-label {
    font-size: 13px;
    font-weight: 700;
    color: $studio-text-sub;
    transition: all 0.2s;
  }

  &:hover:not(.active) {
    .tab-label { color: $studio-text; }
    .tab-icon-img { color: $studio-text; }
  }

  &.active {
    background: linear-gradient(180deg, #333335 0%, $studio-black 100%);
    .tab-label { color: white; }
    .tab-icon-img { color: white; }
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

  .save-btn-ic {
    width: 15px;
    height: 15px;
    margin-right: 7px;
    vertical-align: -3px;
  }

  &:hover {
    background: linear-gradient(180deg, #3a3a3c 0%, #202022 100%);
  }
}
</style>
