<template>
  <div class="agent-config-header">
    <div class="top-nav-bar">
      <!-- Left: Back Button -->
      <div class="header-left">
        <div class="back-section" @click="$emit('back')">
          <i class="el-icon-arrow-left back-icon"></i>
          <span class="back-text">Agents</span>
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
        { id: 'overview', labelKey: 'roleConfig.tabOverview', iconName: 'overview.svg' },
        { id: 'history', labelKey: 'roleConfig.tabHistory', iconName: 'history.svg' },
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
.agent-config-header {
  position: sticky;
  top: 0;
  z-index: 1000;
  background: transparent; // Clean, seamless background
  padding: 16px 24px;
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

  .back-section {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    padding: 8px 12px;
    border-radius: 12px;
    background: white;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    transition: all 0.2s;
    
    &:hover {
      background: #f1f5f9;
      transform: translateX(-2px);
    }

    .back-icon { font-size: 16px; color: #64748b; }
    .back-text { font-size: 13px; font-weight: 700; color: #171717; }
  }
}

.navigation-bar {
  display: flex;
  justify-content: flex-start;
  flex: 1;
  margin-left: 8px;
}

.segmented-control {
  display: inline-flex;
  align-items: center;
  background: #EEEEEE;
  padding: 4px;
  border-radius: 999px;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.05);
  gap: 4px;
}

.segmented-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 24px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  white-space: nowrap;
  
  .tab-icon-img {
    width: 16px;
    height: 16px;
    opacity: 0.7;
    transition: all 0.2s;
    
    &.active-icon {
      filter: brightness(0) invert(1);
      opacity: 1;
    }
  }
  
  .tab-label {
    font-size: 13px;
    font-weight: 700;
    color: #5B5C65;
    transition: all 0.2s;
  }

  &:hover:not(.active) {
    .tab-label { color: #111827; }
    .tab-icon-img { opacity: 1; }
  }

  &.active {
    background: linear-gradient(to right, #000000, #545454);
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);
    .tab-label { color: white; }
  }
  
  @media (max-width: 1024px) {
    padding: 8px 14px;
    .tab-label { display: none; }
  }
}

.header-actions {
  display: flex;
  justify-content: flex-end;
  flex: 0 0 150px;
}

.main-save-btn { 
  background: linear-gradient(to right, #000000, #545454); // Match active segmented tab
  border: none; 
  padding: 10px 24px; 
  border-radius: 999px; // Unified rounded style
  font-weight: 800; 
  font-size: 13px;
  transition: all 0.2s;
  color: white;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  
  &:hover { 
    background: #171717; 
    transform: translateY(-1px);
    box-shadow: 0 6px 12px rgba(0, 0, 0, 0.2);
  }
  
  &:active {
    transform: translateY(0);
  }
}
</style>
