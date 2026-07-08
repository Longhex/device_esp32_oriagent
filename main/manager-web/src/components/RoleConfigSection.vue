<template>
  <div class="role-config-section">
    <div class="dashboard-layout">
      <!-- Column 1: Form cấu hình -->
      <div class="config-panel no-scrollbar card-style">

        <div class="form-panel-header">
          <h3 class="form-panel-title">{{ form.agentName }}</h3>
          <i class="el-icon-edit-outline form-panel-edit-icon"></i>
        </div>

        <div class="config-flow">
          <!-- Toggle: Tùy chỉnh System Prompt (ẩn với Oriagent vì prompt đã cấu hình sẵn trong Studio) -->
          <div class="custom-field-group" v-if="!isOriagentLLM">
            <div class="prompt-toggle-row">
              <label class="field-label-premium">
                <span class="studio-ic studio-ic--instructions label-icon"></span> Tùy chỉnh System Prompt
              </label>
              <el-switch v-model="showSystemPrompt" active-color="#08c45b" />
            </div>
          </div>

          <!-- LLM Model Selector -->
          <div class="custom-field-group">
            <label class="field-label-premium">
              <span class="studio-ic studio-ic--cat-llm label-icon"></span> {{ $t("roleConfig.llm") }}
            </label>
            <div class="model-row-white">
              <div class="model-row-icon"><i class="el-icon-cpu"></i></div>
              <el-select
                v-model="form.model.llmModelId"
                class="model-row-select"
                @change="handleModelChange('LLM', $event)"
              >
                <el-option v-for="item in modelOptions['LLM']" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <span class="model-row-tag">Chat</span>
              <i class="el-icon-view model-row-action"></i>
              <i class="el-icon-set-up model-row-action"></i>
            </div>
          </div>

          <!-- Oriagent API Key riêng từng agent — chỉ hiện khi chọn Oriagent; để trống = dùng key chung của model -->
          <div class="custom-field-group" v-if="isOriagentLLM">
            <label class="field-label-premium">
              <span class="studio-ic studio-ic--apikey label-icon"></span> Oriagent API Key (riêng agent này)
            </label>
            <div class="premium-field-pill soft-pill">
              <i class="el-icon-key pill-badge-icon-inline"></i>
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
                <span class="studio-ic studio-ic--cat-vad label-icon"></span> {{ $t("roleConfig.voiceDetect") }}
              </label>
              <div class="premium-field-pill soft-pill">
                <img src="@/assets/dashboard/agent.svg" class="pill-badge-icon" />
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
                <span class="studio-ic studio-ic--cat-asr label-icon"></span> {{ $t("roleConfig.speechRecognition") }}
              </label>
              <div class="premium-field-pill soft-pill">
                <img src="@/assets/dashboard/agent.svg" class="pill-badge-icon" />
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
              <span class="studio-ic studio-ic--cat-tts label-icon"></span> Văn bản thành giọng nói
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

          <!-- Câu đệm suy nghĩ (thinking-buffer) — TOÀN HỆ THỐNG, mọi TTS -->
          <div class="filler-premium-card">
            <div class="filler-header-row">
              <label class="field-label-premium">
                <span class="studio-ic studio-ic--voice label-icon"></span> Câu đệm suy nghĩ
              </label>
              <el-switch
                v-model="form.fillerEnabled"
                :active-value="1"
                :inactive-value="0"
                active-color="#08c45b"
                @change="onFillerToggle"
              />
            </div>

            <template v-if="form.fillerEnabled === 1">
              <div class="filler-field">
                <span class="filler-tag">Thời gian chờ (ms)</span>
                <div class="filler-input-pill">
                  <el-input-number
                    v-model="form.fillerDelayMs"
                    class="filler-number"
                    :min="100"
                    :max="5000"
                    :step="100"
                    controls-position="right"
                  />
                </div>
              </div>

              <div class="filler-field">
                <span class="filler-tag">Câu đệm (mỗi câu một dòng)</span>
                <el-input
                  type="textarea"
                  v-model="form.fillerPhrases"
                  class="filler-textarea"
                  :autosize="{ minRows: 4, maxRows: 10 }"
                  placeholder="Ừm, để mình nghĩ xíu nha&#10;Câu này hay nè, đợi mình một chút&#10;Để mình xem nào"
                />
              </div>

              <p class="filler-hint">
                Số dòng = số câu đệm (xoay vòng). Để trống = dùng câu mặc định toàn hệ thống.
                Khi LLM nghĩ lâu hơn "thời gian đợi", hệ thống phát một câu đệm để che độ trễ — áp dụng cho mọi TTS.
              </p>
            </template>
          </div>
        </div>
      </div>

      <!-- Column 2: Testing (Live Preview) -->
      <div class="preview-panel card-style">
        <div class="panel-header-row">
          <span class="panel-header-title"><span class="studio-ic studio-ic--filler panel-header-ic"></span> Testing</span>
        </div>

        <div class="mockup-screen">
          <!-- Trạng thái đang gọi: waveform tĩnh + trạng thái + nút ngắt, chat thật nằm trong iframe -->
          <template v-if="isLiveTesting">
            <div class="live-test-wrapper">
              <div class="live-status-bar">
                <div class="live-waveform-static">
                  <span class="wave-bar" v-for="n in 5" :key="n"></span>
                </div>
                <span class="live-status-text">Đang hoạt động</span>
                <div class="call-btn end" @click="isLiveTesting = false">
                  <img src="@/assets/dashboard/phone_stop.svg" class="btn-icon-svg" />
                </div>
              </div>
              <iframe
                :src="testLiveUrl"
                frameborder="0"
                class="live-iframe"
                :title="$t('roleConfig.liveTestTitle')"
              ></iframe>
            </div>
          </template>

          <!-- Trạng thái chưa gọi: vòng tròn trắng + waveform tĩnh + nút gọi -->
          <template v-else>
            <div class="idle-test-wrapper">
              <div class="idle-circle">
                <svg class="idle-waveform" viewBox="0 0 100 40" xmlns="http://www.w3.org/2000/svg">
                  <rect x="6" y="15" width="4" height="10" rx="2" />
                  <rect x="16" y="9" width="4" height="22" rx="2" />
                  <rect x="26" y="4" width="4" height="32" rx="2" />
                  <rect x="36" y="12" width="4" height="16" rx="2" />
                  <rect x="46" y="1" width="4" height="38" rx="2" />
                  <rect x="56" y="12" width="4" height="16" rx="2" />
                  <rect x="66" y="4" width="4" height="32" rx="2" />
                  <rect x="76" y="9" width="4" height="22" rx="2" />
                  <rect x="86" y="15" width="4" height="10" rx="2" />
                </svg>
              </div>
              <div class="call-btn start" @click="toggleLiveTest">
                <img src="@/assets/dashboard/phone_calling.svg" class="btn-icon-svg" />
              </div>
            </div>
          </template>
        </div>

        <!-- Ô nhập tin nhắn tĩnh: chỉ hiện khi chưa gọi (khi đang gọi, ô nhập thật nằm trong live-iframe) -->
        <div class="idle-input-bar" v-if="!isLiveTesting">
          <i class="el-icon-chat-dot-round"></i>
          <span class="idle-input-placeholder">Nhập tin nhắn...</span>
          <div class="idle-send-btn"><i class="el-icon-top"></i></div>
        </div>
      </div>

      <!-- Column 3: Instructions (System Prompt) — chỉ hiện khi bật toggle & model không phải Oriagent -->
      <div class="system-prompt-panel card-style" v-if="showSystemPrompt && !isOriagentLLM">
        <div class="panel-header-row">
          <span class="panel-header-title"><span class="studio-ic studio-ic--instructions panel-header-ic"></span> Instructions</span>
          <div class="panel-header-actions">
            <span class="studio-ic studio-ic--settings sp-gear-icon"></span>
            <span class="sp-auto-btn"><span class="studio-ic studio-ic--autogen sp-auto-ic"></span> Tạo tự động</span>
          </div>
        </div>
        <el-input
          type="textarea"
          v-model="form.systemPrompt"
          class="sp-textarea"
          :rows="16"
          maxlength="4000"
          resize="none"
          placeholder="Ví dụ: Bạn là trợ lý thân thiện, trả lời ngắn gọn, dễ hiểu..."
        />
        <div class="sp-footer">
          <span class="sp-footer-item"><span class="studio-ic studio-ic--char sp-footer-ic"></span>Character: {{ (form.systemPrompt || '').length }}</span>
          <span class="sp-footer-item"><span class="studio-ic studio-ic--token sp-footer-ic"></span>Token prompt: --</span>
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
      return t === 'oriagent_http' || t === 'oriagent_websocket' || t === 'oriagent_ws';
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
    // Bật câu đệm: nếu chưa có thời gian đợi thì đặt mặc định 700ms cho dễ dùng.
    onFillerToggle(val) {
      if (val === 1 && (this.form.fillerDelayMs == null || this.form.fillerDelayMs === '')) {
        this.$set(this.form, 'fillerDelayMs', 700);
      }
    },
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
      Api.device.getAgentBindDevices(this.agentId, (res) => {
        const devices = (res.data && res.data.data) || [];
        const exists = devices.some(d => (d.macAddress || '').toUpperCase() === mac.toUpperCase());
        if (exists) { finish(); return; }
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
@import "@/views/studio.scss";

$ori-dark: #313133;
$ori-slate: #64748b;
$ori-green: #08c45b;
$ori-border: #f1f5f9;

.role-config-section {
  padding: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.card-style {
  @include studio-panel;
}

.dashboard-layout {
  display: flex;
  align-items: stretch;
  flex: 1;
  min-height: 700px;
  gap: 24px; /* tách 3 box rõ ràng (design step 16->24), đồng đều */

  /* flex thay grid: 2 panel -> 50/50, 3 panel -> chia đều 3, không để cột trống */

  @media (max-width: 1400px) {
    flex-direction: column;
    min-height: auto;
    gap: 20px;
  }
}

.config-panel {
  order: 1;
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 32px;
  padding: 24px;
  overflow-y: auto;

  @media (max-width: 1400px) { flex: 1 1 auto; }
}

.preview-panel {
  order: 2;
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 24px;
  overflow: hidden;

  @media (max-width: 1400px) {
    flex: 1 1 auto;
    min-height: 560px;
  }
}

.system-prompt-panel {
  order: 3;
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;

  @media (max-width: 1400px) { flex: 1 1 auto; }
}

/* Header dùng chung cho panel Testing / Instructions */
.panel-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 700;
  color: $studio-text;

  i { color: $studio-text-sub; font-size: 15px; }
  .panel-header-ic { width: 18px; height: 18px; }
}

.panel-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sp-gear-icon {
  width: 18px;
  height: 18px;
  color: $studio-text-sub;
  cursor: default;
}

.sp-auto-btn {
  @include studio-black-pill;
  height: 30px;
  padding: 0 14px;
  font-size: 12px;
  cursor: default; // Chưa có tính năng thật — hiển thị tĩnh

  .sp-auto-ic { width: 14px; height: 14px; }
}

.sp-textarea {
  flex: 1;
  display: flex;
}
::v-deep .sp-textarea .el-textarea__inner {
  height: 100%;
  min-height: 340px;
  border-radius: 16px;
  border: 1px solid $studio-border;
  background: $studio-soft-bg;
  font-size: 14px;
  line-height: 1.6;
  padding: 16px;
}

.sp-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 600;
  color: $studio-text-sub;

  .sp-footer-item { display: inline-flex; align-items: center; gap: 5px; }
  .sp-footer-ic { width: 13px; height: 13px; }
}

/* Hide Scrollbar */
.no-scrollbar {
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none; /* IE and Edge */

  &::-webkit-scrollbar {
    display: none; /* Chrome, Safari, Opera */
  }
}

/* Header panel Form: tên agent + icon edit tĩnh */
.form-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.form-panel-title {
  margin: 0;
  font-size: 17px;
  font-weight: 800;
  color: $studio-text;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.form-panel-edit-icon {
  font-size: 16px;
  color: $studio-text-sub;
  cursor: default;
  flex-shrink: 0;
}

.config-flow {
  display: flex; flex-direction: column; gap: 20px;
}

.selection-grid-vertical {
  display: flex; flex-direction: column; gap: 20px;
}

/* Câu đệm suy nghĩ — card xanh nhạt theo token */
.filler-premium-card {
  background: $studio-accent-soft;
  border-radius: 20px;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;

  .filler-header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .filler-field {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .filler-tag {
    font-size: 12px;
    font-weight: 700;
    color: $ori-dark;
    padding-left: 4px;
  }

  .filler-input-pill {
    background: white;
    border-radius: 999px;
    padding: 4px 6px;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
  }

  .filler-hint {
    margin: 0;
    font-size: 12px;
    color: #6b7280;
    line-height: 1.5;
  }

  ::v-deep .filler-number {
    width: 100%;
    line-height: normal;

    .el-input__inner {
      height: 44px;
      border: none;
      border-radius: 999px;
      background: transparent;
      text-align: left;
      padding-left: 16px;
      font-size: 14px;
      font-weight: 700;
      color: #111827;
    }
    .el-input-number__decrease,
    .el-input-number__increase {
      border: none;
      background: transparent;
      color: $ori-green;
    }
    .el-input-number__decrease:hover,
    .el-input-number__increase:hover {
      color: #067a3a;
    }
  }

  ::v-deep .filler-textarea .el-textarea__inner {
    border: none;
    border-radius: 16px;
    background: white;
    padding: 14px 16px;
    font-size: 13px;
    font-weight: 500;
    color: #111827;
    line-height: 1.6;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
    resize: none;
  }
}

/* Hàng toggle "Tùy chỉnh System Prompt": icon+label trái, công tắc phải (tách rõ) */
.prompt-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* Custom Fields */
.custom-field-group {
  display: flex; flex-direction: column; gap: 8px;

  .field-label-premium {
    font-size: 13px; font-weight: 700; color: $ori-dark; display: flex; align-items: center; gap: 8px;
    .label-icon { font-size: 14px; color: $studio-text-sub; }
    span.label-icon { width: 16px; height: 16px; }
    i { color: $ori-slate; opacity: 0.8; }
  }
}

/* Hàng model AI (LLM): pill trắng viền, icon + tên + tag Chat + icon mắt/chỉnh */
.model-row-white {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fff;
  border: 1px solid $studio-border;
  border-radius: $studio-radius-pill;
  padding: 6px 14px;

  .model-row-icon {
    width: 26px; height: 26px; border-radius: 50%;
    background: $studio-soft-bg;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    i { font-size: 13px; color: $studio-text-sub; }
  }

  .model-row-tag {
    font-size: 11px; font-weight: 700; color: $studio-text-sub;
    background: $studio-soft-bg; border-radius: $studio-radius-pill;
    padding: 3px 10px; flex-shrink: 0; white-space: nowrap;
  }

  .model-row-action { font-size: 14px; color: $studio-text-sub; cursor: default; flex-shrink: 0; }

  ::v-deep .el-input__inner {
    border: none; background: transparent; padding: 0; height: 32px;
    font-size: 13px; font-weight: 700; color: $studio-text;
  }
  ::v-deep .el-input__suffix { display: none; }
}
.model-row-select { flex: 1; min-width: 0; }

/* Pill xanh nhạt: API key / VAD / STT */
.premium-field-pill {
  background: $studio-soft-bg;
  border-radius: 999px;
  padding: 3px;
  transition: all 0.3s ease;
  border: 1px solid transparent;
  display: flex;
  align-items: center;
  gap: 8px;

  &.soft-pill {
    background: $studio-accent-soft;
    padding: 6px 14px;
  }

  &:focus-within {
    border-color: $studio-accent;
  }
  &.soft-pill:focus-within {
    background: $studio-accent-soft;
    box-shadow: 0 0 0 3px rgba(8, 196, 91, 0.15);
  }
}

.pill-badge-icon {
  width: 22px; height: 22px; border-radius: 50%;
  background: #fff; padding: 4px; flex-shrink: 0;
}
.pill-badge-icon-inline {
  font-size: 14px; color: $studio-text-sub; flex-shrink: 0;
}

::v-deep {
  .premium-input-field .el-input__inner,
  .premium-select-field .el-input__inner {
    height: 36px; border: none; background: transparent; padding: 0 4px;
    font-size: 12px; font-weight: 600; color: $ori-dark;
    &:focus { outline: none; }
  }

  .premium-select-field { width: 100%; flex: 1; }
  .premium-input-field { flex: 1; }
}

/* TTS Card: viền xanh, nền trắng */
.tts-premium-card {
  background: #fff;
  border: 1.5px solid $studio-accent;
  border-radius: 20px;
  padding: 24px;
  display: flex; flex-direction: column; gap: 16px;

  .brand-pill-row {
    .brand-select-pill {
      width: 100%;
      ::v-deep .el-input__inner {
         height: 52px; border: none; border-radius: 999px; background: $studio-soft-bg;
         padding: 0 48px 0 64px; font-size: 14px; font-weight: 700; color: #111827;
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
        background: $studio-soft-bg; border-radius: 999px; padding: 4px;
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

/* Mockup / test area */
.mockup-screen {
  flex: 1;
  background: transparent;
  border-radius: 24px;
  border: none;
  overflow: hidden;
  position: relative;
  box-shadow: none;
  display: flex;
  flex-direction: column;
}

.live-test-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.live-iframe { width: 100%; height: 100%; border: none; flex: 1; border-radius: 16px; }

/* Thanh trạng thái khi đang gọi: waveform tĩnh + "Đang hoạt động" + nút ngắt */
.live-status-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  border: 1px solid $studio-border;
  border-radius: 999px;
  padding: 8px 10px 8px 16px;
  flex-shrink: 0;
}

.live-waveform-static {
  display: flex;
  align-items: center;
  gap: 3px;

  .wave-bar {
    width: 3px;
    background: $studio-accent;
    border-radius: 2px;
    height: 14px;
    &:nth-child(2) { height: 20px; }
    &:nth-child(3) { height: 10px; }
    &:nth-child(4) { height: 22px; }
    &:nth-child(5) { height: 14px; }
  }
}

.live-status-text {
  flex: 1;
  font-size: 13px;
  font-weight: 700;
  color: $studio-text;
}

/* Trạng thái chưa gọi: vòng tròn trắng lớn + waveform tĩnh + nút gọi */
.idle-test-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0;
}

.idle-circle {
  width: min(440px, 90%); /* gần đầy cột -> dải trắng cột config↔Testing co lại, 2 bên vẫn cân đều */
  aspect-ratio: 1 / 1;     /* giữ hình tròn khi width đổi */
  max-width: 100%;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
}

.idle-waveform {
  width: 55%;
  height: auto;
  fill: #c7c9cf;
}

.call-btn {
  width: 56px; height: 56px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.3s; flex-shrink: 0;

  &.start { background: $studio-accent; margin-top: -22px; position: relative; z-index: 1; } /* tuck sát mép dưới vòng tròn như mẫu */
  &.end { background: #ef4444; width: 40px; height: 40px; }

  &:hover { transform: scale(1.05); }

  .btn-icon-svg {
     width: 22px; height: 22px;
     filter: brightness(0) invert(1); // Make SVG white
  }
  &.end .btn-icon-svg { width: 16px; height: 16px; }
}

/* Ô nhập tin nhắn tĩnh — chỉ hiển thị khi chưa gọi (trang trí, không có logic gửi) */
.idle-input-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  background: $studio-soft-bg;
  border-radius: 999px;
  padding: 8px 8px 8px 16px;
  flex-shrink: 0;

  i { color: $studio-text-sub; font-size: 15px; }

  .idle-input-placeholder {
    flex: 1;
    font-size: 13px;
    color: $studio-text-sub;
    text-align: left;
  }

  .idle-send-btn {
    width: 32px; height: 32px; border-radius: 50%;
    background: $studio-black;
    color: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px;
    flex-shrink: 0;
  }
}
</style>
