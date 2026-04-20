<template>
  <div class="role-config-section">
    <div class="dashboard-layout">
      <!-- Left Column: Pure Setup -->
      <div class="config-panel no-scrollbar card-style">
        
        <!-- Center Branding Section -->
        <div class="branding-header">
           <div class="branding-avatar-wrapper">
              <div class="avatar-circle">
                <img src="@/assets/dashboard/agent.svg" alt="Agent" />
              </div>
           </div>
           <h2 class="branding-title">{{ form.agentName }}</h2>
           <p class="branding-subtitle">
             {{ $t("roleConfig.brandingSubtitle") }}
           </p>
        </div>

        <div class="config-flow">
          <!-- Oriagent API KEY Field -->
          <div class="custom-field-group">
            <label class="field-label-premium">
              <img src="@/assets/dashboard/model_AI.svg" class="label-icon-svg" /> Oriagent API KEY
            </label>
            <div class="premium-field-pill">
              <el-input 
                :value="oriagentApiKey" 
                @input="$emit('update:oriagentApiKey', $event)"
                class="premium-input-field" 
                :placeholder="$t('roleConfig.placeholderApiKey')"
                show-password
              />
            </div>
          </div>

          <!-- Component Selectors -->
          <div class="selection-grid-vertical">
            <div class="custom-field-group">
              <label class="field-label-premium">
                <img src="@/assets/dashboard/model_AI.svg" class="label-icon-svg" /> {{ $t("roleConfig.voiceDetect") }}
              </label>
              <div class="premium-field-pill">
                <el-select 
                  v-model="form.model.vadModelId" 
                  class="premium-select-field" 
                  @change="handleModelChange('VAD', $event)"
                >
                  <el-option v-for="item in modelOptions['VAD']" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </div>
            </div>

            <div class="custom-field-group">
              <label class="field-label-premium">
                <img src="@/assets/dashboard/model_AI.svg" class="label-icon-svg" /> {{ $t("roleConfig.speechRecognition") }}
              </label>
              <div class="premium-field-pill">
                <el-select 
                  v-model="form.model.asrModelId" 
                  class="premium-select-field" 
                  @change="handleModelChange('ASR', $event)"
                >
                  <el-option v-for="item in modelOptions['ASR']" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </div>
            </div>
          </div>

          <!-- TTS Section Header -->
          <div class="custom-field-group">
            <label class="field-label-premium">
              <img src="@/assets/dashboard/model_AI.svg" class="label-icon-svg" /> Văn bản thành giọng nói
            </label>
          </div>

          <!-- Text-to-Speech Sub-Selection Card -->
          <div class="tts-premium-card">
            <div class="brand-pill-row">
              <el-select 
                v-model="form.model.ttsModelId" 
                class="brand-select-pill" 
                @change="handleModelChange('TTS', $event)"
              >
                <div slot="prefix" class="brand-logo-prefix" v-if="currentModelLabel">
                  <img :src="modelBrandIcon" class="brand-icon" v-if="modelBrandIcon" />
                </div>
                <el-option v-for="item in modelOptions['TTS']" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </div>

            <div class="sub-selectors-row">
              <div class="mini-selector-premium flex-1">
                <span class="selector-tag-premium">Language</span>
                <div class="white-pill-selector">
                  <el-select v-model="internalLanguage" class="ghost-select-premium" @change="filterVoicesByLanguage">
                    <el-option v-for="lang in languageOptions" :key="lang.value" :label="lang.label" :value="lang.value" />
                  </el-select>
                </div>
              </div>
              <div class="mini-selector-premium flex-1">
                <span class="selector-tag-premium">Voice Type</span>
                <div class="white-pill-selector">
                  <el-select v-model="form.ttsVoiceId" class="ghost-select-premium">
                    <el-option v-for="item in voiceOptions" :key="item.value" :label="item.label" :value="item.value" />
                  </el-select>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right Column: Live Preview / Test -->
      <div class="preview-panel card-style">
         <div class="mockup-screen">
            <!-- Live iframe -->
            <template v-if="isLiveTesting">
               <div class="live-test-wrapper">
                  <iframe 
                    :src="testLiveUrl" 
                    frameborder="0" 
                    class="live-iframe"
                    :title="$t('roleConfig.liveTestTitle')"
                  ></iframe>
               </div>
            </template>
            <!-- Show Blank/Empty when !isLiveTesting -->
         </div>
         
         <div class="test-live-bar">
            <div class="pill-bar">
               <div class="call-btn start" @click="isLiveTesting = !isLiveTesting" :class="{ active: isLiveTesting }">
                  <img src="@/assets/dashboard/phone_calling.svg" class="btn-icon-svg" v-if="!isLiveTesting" />
                  <i class="el-icon-close" v-else></i>
               </div>
               <div class="status-label">{{ $t("roleConfig.testLive") }}</div>
               <div class="call-btn end" @click="isLiveTesting = false">
                  <img src="@/assets/dashboard/phone_stop.svg" class="btn-icon-svg" />
               </div>
            </div>
         </div>
      </div>
    </div>
  </div>
</template>

<script>
import Api from '@/apis/api';

export default {
  name: "RoleConfigSection",
  props: {
    agentId: String,
    form: Object,
    modelOptions: Object,
    voiceOptions: Array,
    languageOptions: Array,
    selectedLanguage: String,
    oriagentApiKey: String
  },
  data() {
    return {
      isLiveTesting: false,
      internalLanguage: this.selectedLanguage
    };
  },
  computed: {
    testLiveUrl() {
      const baseUrl = "/test_live/test_page.html";
      const otaUrl = Api.getServiceUrl() + '/ota/';
      const lang = this.$i18n.locale;
      return `${baseUrl}?agentId=${this.agentId}&otaUrl=${encodeURIComponent(otaUrl)}&lang=${lang}`;
    },
    currentModelLabel() {
      if (!this.form.model.ttsModelId || !this.modelOptions['TTS']) return '';
      const model = this.modelOptions['TTS'].find(m => m.value === this.form.model.ttsModelId);
      return model ? model.label : '';
    },
    modelBrandIcon() {
      const label = (this.currentModelLabel || '').toLowerCase();
      if (label.includes('openai')) return require('@/assets/dashboard/openai.svg');
      return require('@/assets/dashboard/agent.svg'); // Fallback
    }
  },
  watch: {
    selectedLanguage(newVal) {
      this.internalLanguage = newVal;
    }
  },
  methods: {
    handleModelChange(type, value) {
      this.$emit('model-change', { type, value });
    },
    filterVoicesByLanguage(val) {
      this.$emit('update:selectedLanguage', val);
      this.$emit('filter-voices');
    }
  }
};
</script>

<style lang="scss" scoped>
$ori-dark: #313133;
$ori-slate: #64748b;
$ori-green: #08c45b;
$ori-light-green: #ecfccb;
$ori-border: #f1f5f9;

.role-config-section { padding: 0; }

.card-style {
  background: white !important;
  border: 1px solid $ori-border !important;
  border-radius: 24px !important;
  box-shadow: none !important;
}

.dashboard-layout { 
  display: flex; 
  align-items: stretch;
  height: 720px;
  gap: 20px;
  
  @media (max-width: 1200px) { 
    flex-direction: column; 
    height: auto;
  }
}

.config-panel {
  flex: 0 0 520px; 
  display: flex; 
  flex-direction: column; 
  gap: 40px;
  padding: 40px;
  overflow-y: auto;
  
  @media (max-width: 1200px) { 
    flex: none;
    max-height: 500px;
  }
}

/* Hide Scrollbar */
.no-scrollbar {
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none; /* IE and Edge */
  
  &::-webkit-scrollbar {
    display: none; /* Chrome, Safari, Opera */
  }
}

/* Branding Header */
.branding-header {
  text-align: center;
  margin-bottom: 10px;
  
  .avatar-circle {
    width: 80px; height: 80px; 
    background: #e2f9eb;
    border-radius: 50%; 
    display: inline-flex; align-items: center; justify-content: center;
    margin-bottom: 16px;
    border: 4px solid white;
    box-shadow: 0 8px 16px rgba(0,0,0,0.05);
    img { width: 48px; height: 48px; }
  }
  
  .branding-title {
    font-size: 20px; font-weight: 800; color: #111827; margin: 0 0 8px;
  }
  
  .branding-subtitle {
    font-size: 13px; color: $ori-slate; line-height: 1.5; max-width: 320px; margin: 0 auto;
  }
}

.config-flow {
  display: flex; flex-direction: column; gap: 20px;
}

.selection-grid-vertical {
  display: flex; flex-direction: column; gap: 20px;
}

/* Custom Fields */
.custom-field-group {
  display: flex; flex-direction: column; gap: 8px;
  
  .field-label-premium {
    font-size: 13px; font-weight: 700; color: $ori-dark; display: flex; align-items: center; gap: 10px;
    .label-icon-svg { width: 14px; height: 14px; opacity: 0.7; }
    i { color: $ori-slate; opacity: 0.8; }
  }
}

.premium-field-pill {
  background: #EEEEEE;
  border-radius: 999px;
  padding: 3px;
  transition: all 0.3s ease;
  border: 1px solid transparent;

  &:focus-within {
    background: white;
    border-color: $ori-green;
    box-shadow: 0 0 0 4px rgba(8, 196, 91, 0.1);
  }
}

::v-deep {
  .premium-input-field .el-input__inner,
  .premium-select-field .el-input__inner {
    height: 36px; border: none; background: transparent; padding: 0 16px;
    font-size: 12px; font-weight: 600; color: $ori-dark;
    &:focus { outline: none; }
  }
  
  .premium-select-field { width: 100%; }
}

/* TTS Card Premium */
.tts-premium-card {
  background: #DFF9C0; 
  border-radius: 20px; 
  padding: 24px;
  display: flex; flex-direction: column; gap: 16px;
  
  .brand-pill-row {
    .brand-select-pill {
      width: 100%;
      ::v-deep .el-input__inner {
         height: 52px; border: none; border-radius: 999px; background: white;
         padding: 0 48px 0 64px; font-size: 14px; font-weight: 700; color: #111827;
         box-shadow: 0 4px 10px rgba(0,0,0,0.05);
      }
      ::v-deep .el-input__prefix { left: 16px; display: flex; align-items: center; }
      ::v-deep .el-input__suffix { display: none !important; }
      
      .brand-logo-prefix {
         .brand-icon { width: 32px; height: 32px; }
      }
    }
  }

  .sub-selectors-row {
     display: flex; justify-content: space-between; gap: 20px;
  }
  
  .mini-selector-premium {
     display: flex; flex-direction: column; gap: 8px; width: 48%; // Ensure split
     
     .selector-tag-premium { font-size: 12px; font-weight: 700; color: #3d4566; padding-left: 4px; text-align: left; }
     
     .white-pill-selector {
        background: white; border-radius: 999px; padding: 4px; 
        .ghost-select-premium {
           width: 100%;
           ::v-deep .el-input__inner { 
              background: transparent; border: none; text-align: left; 
              padding: 0 20px; font-weight: 600; color: #111827; height: 36px; font-size: 13px; 
           }
           ::v-deep .el-input__suffix { display: none; }
        }
     }
  }
}

/* Preview Panel */
.preview-panel {
  flex: 1; 
  display: flex; 
  flex-direction: column; 
  gap: 24px;
  padding: 40px;
  overflow: hidden;
  
  @media (max-width: 1200px) { 
    width: 100%; 
    height: 600px; 
  }
}

.mockup-screen {
  flex: 1; 
  background: transparent; 
  border-radius: 24px; 
  border: none; 
  overflow: hidden;
  position: relative; 
  box-shadow: none;
}

.chat-preview-mock {
   padding: 24px; 
   .mock-header { font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: $ori-slate; margin-bottom: 20px; }
   .mock-msg .msg-bubble { background: #f1f5f9; padding: 12px 18px; border-radius: 18px; border-bottom-left-radius: 4px; font-size: 14px; color: $ori-dark; line-height: 1.5; }
}

.live-test-wrapper { width: 100%; height: 100%; }
.live-iframe { width: 100%; height: 100%; border: none; }

.test-live-bar {
  display: flex;
  justify-content: center;

  .pill-bar {
    background: #EEEEEE; 
    border-radius: 50px; 
    padding: 8px 12px;
    display: flex; 
    align-items: center; 
    justify-content: space-between;
    width: fit-content;
    min-width: 320px;
    border: 1px solid transparent;
    transition: all 0.3s ease;
  }
  
  .status-label { font-size: 14px; font-weight: 700; color: #111827; }
  
  .call-btn {
    width: 48px; height: 48px; border-radius: 50%; 
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; transition: all 0.3s; font-size: 18px;
    
    &.start { 
      background: $ori-green; color: white; 
      &.active { background: #ef4444; transform: rotate(180deg); }
    }
    &.end { background: #ef4444; color: white; }
    
    &:hover { transform: scale(1.05); }

    .btn-icon-svg {
       width: 20px; height: 20px;
       filter: brightness(0) invert(1); // Make SVG white
    }
  }
}
</style>
