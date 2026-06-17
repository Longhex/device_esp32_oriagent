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
          <!-- Toggle: Tùy chỉnh System Prompt (ẩn với Oriagent vì prompt đã cấu hình sẵn trong Studio) -->
          <div class="custom-field-group" v-if="!isOriagentLLM">
            <div class="prompt-toggle-row">
              <label class="field-label-premium">
                <img src="@/assets/dashboard/model_AI.svg" class="label-icon-svg" /> Tùy chỉnh System Prompt
              </label>
              <el-switch v-model="showSystemPrompt" active-color="#08c45b" />
            </div>
          </div>

          <!-- LLM Model Selector -->
          <div class="custom-field-group">
            <label class="field-label-premium">
              <img src="@/assets/dashboard/model_AI.svg" class="label-icon-svg" /> {{ $t("roleConfig.llm") }}
            </label>
            <div class="premium-field-pill">
              <el-select
                v-model="form.model.llmModelId"
                class="premium-select-field"
                @change="handleModelChange('LLM', $event)"
              >
                <el-option v-for="item in modelOptions['LLM']" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </div>
          </div>

          <!-- Oriagent API Key riêng từng agent — chỉ hiện khi chọn Oriagent; để trống = dùng key chung của model -->
          <div class="custom-field-group" v-if="isOriagentLLM">
            <label class="field-label-premium">
              <img src="@/assets/dashboard/model_AI.svg" class="label-icon-svg" /> Oriagent API Key (riêng agent này)
            </label>
            <div class="premium-field-pill">
              <el-input
                v-model="form.oriagentApiKey"
                class="premium-input-field"
                placeholder="Nhập key riêng (app-...); để trống = dùng key chung của model"
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

      <!-- Middle Column: System Prompt (chỉ hiện khi bật toggle & model không phải Oriagent) -->
      <div class="system-prompt-panel card-style" v-if="showSystemPrompt && !isOriagentLLM">
        <div class="sp-header">
          <label class="field-label-premium">
            <img src="@/assets/dashboard/model_AI.svg" class="label-icon-svg" /> System Prompt
          </label>
          <p class="sp-hint">Hướng dẫn tác nhân cách giao tiếp và xử lý yêu cầu.</p>
        </div>
        <el-input
          type="textarea"
          v-model="form.systemPrompt"
          class="sp-textarea"
          :rows="16"
          maxlength="4000"
          show-word-limit
          resize="none"
          placeholder="Ví dụ: Bạn là trợ lý thân thiện, trả lời ngắn gọn, dễ hiểu..."
        />
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
               <div class="call-btn start" @click="toggleLiveTest" :class="{ active: isLiveTesting }">
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
    llmModeTypeMap: Object,
    voiceOptions: Array,
    languageOptions: Array,
    selectedLanguage: String
  },
  data() {
    return {
      isLiveTesting: false,
      testLoading: false,
      internalLanguage: this.selectedLanguage,
      showSystemPrompt: false
    };
  },
  computed: {
    isOriagentLLM() {
      const map = this.llmModeTypeMap || {};
      const t = map[this.form.model.llmModelId];
      return t === 'oriagent_http' || t === 'oriagent_websocket';
    },
    // MAC test cố định RIÊNG theo từng agent (per-agent), KHÔNG bao giờ trùng MAC thiết bị thật:
    // tiền tố 02 (locally-administered) + 5 octet suy ra từ agentId. Ổn định -> không bao giờ phải move binding.
    testDeviceMac() {
      const hex = (this.agentId || '').replace(/[^0-9a-fA-F]/g, '').toUpperCase().padEnd(10, '0').slice(0, 10);
      const octets = hex.match(/.{2}/g) || ['00', '00', '00', '00', '00'];
      return ['02', ...octets].join(':');
    },
    testLiveUrl() {
      const baseUrl = "/test_live/test_page.html";
      const otaUrl = Api.getServiceUrl() + '/ota/';
      const lang = this.$i18n.locale;
      return `${baseUrl}?agentId=${this.agentId}&otaUrl=${encodeURIComponent(otaUrl)}&lang=${lang}&deviceMac=${this.testDeviceMac}`;
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
    },
    // Tự bật toggle nếu agent đã có sẵn system prompt
    'form.systemPrompt': {
      immediate: true,
      handler(val) {
        if (val && val.trim()) this.showSystemPrompt = true;
      }
    }
  },
  methods: {
    // Bật/tắt test trực tiếp. Khi bật: đảm bảo MAC test riêng của agent đã được bind, RỒI mới mở iframe.
    toggleLiveTest() {
      if (this.isLiveTesting) {
        this.isLiveTesting = false;
        return;
      }
      if (this.testLoading) return;
      this.testLoading = true;
      let opened = false;
      const open = () => {
        if (!opened) {
          opened = true;
          this.isLiveTesting = true;
        }
        this.testLoading = false;
      };
      this.ensureTestDevice(open);
      setTimeout(open, 2500);
    },
    // Đăng ký MAC test riêng cho agent hiện tại.
    // AN TOÀN: chỉ THÊM khi MAC chưa tồn tại; không bao giờ move/sửa binding sẵn có (của agent khác / thiết bị thật).
    ensureTestDevice(done) {
      const finish = () => { if (done) done(); };
      if (!this.agentId) { finish(); return; }
      const mac = this.testDeviceMac;
      Api.device.getAgentBindDevices(this.agentId, ({ data }) => {
        const exists = (data || []).some(d => (d.macAddress || '').toUpperCase() === mac.toUpperCase());
        if (exists) { finish(); return; } // đã bind đúng agent này -> không làm gì
        Api.device.manualAddDevice(
          { agentId: this.agentId, board: 'web-test', appVersion: '1.0.0', macAddress: mac },
          () => finish()
        );
      });
    },
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

.role-config-section { 
  padding: 0; 
  flex: 1;
  display: flex;
  flex-direction: column;
}

.card-style {
  background: white !important;
  border: 1px solid $ori-border !important;
  border-radius: 24px !important;
  box-shadow: none !important;
}

.dashboard-layout { 
  display: flex; 
  align-items: stretch;
  flex: 1;
  min-height: 700px;
  gap: 24px;
  
  @media (max-width: 1200px) { 
    flex-direction: column; 
    min-height: auto;
    gap: 32px;
  }
}

.config-panel {
  flex: 0 0 35%; 
  min-width: 400px;
  display: flex; 
  flex-direction: column; 
  gap: 40px;
  padding: 40px;
  overflow-y: auto;
  
  @media (max-width: 1200px) { 
    flex: none;
    width: 100%;
    min-width: 0;
    max-height: none; // Allow it to grow on mobile
  }
}

/* Toggle row: Tùy chỉnh System Prompt */
.prompt-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

/* Middle Column: System Prompt */
.system-prompt-panel {
  flex: 1;
  min-width: 320px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 40px;

  @media (max-width: 1200px) {
    flex: none;
    width: 100%;
    min-width: 0;
  }

  .sp-header { display: flex; flex-direction: column; gap: 6px; }
  .sp-hint { margin: 0; font-size: 13px; color: $ori-slate; }
  .sp-textarea { flex: 1; display: flex; }
  ::v-deep .sp-textarea .el-textarea__inner {
    height: 100%;
    min-height: 360px;
    border-radius: 16px;
    border: 1px solid $ori-border;
    background: #f8fafc;
    font-size: 14px;
    line-height: 1.6;
    padding: 16px;
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
  flex: 1; // Takes the remaining 65%
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
