<template>
  <el-dialog :visible="dialogVisible" @update:visible="handleVisibleChange" width="57%" center
    custom-class="custom-dialog" :show-close="false" class="center-dialog">
    <div style="margin: 0 18px; text-align: left; padding: 10px; border-radius: 10px;">
      <div style="font-size: 30px; color: #3d4566; margin-top: -10px; margin-bottom: 10px; text-align: center;">
        {{ $t('modelConfigDialog.addModel') }}
      </div>

      <button class="custom-close-btn" @click="handleClose">
        ×
      </button>

      <!-- 模型信息部分 -->
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
        <div style="font-size: 20px; font-weight: bold; color: #3d4566;">{{ $t('modelConfigDialog.modelInfo') }}</div>
        <div style="display: flex; align-items: center; gap: 20px;">
          <div style="display: flex; align-items: center;">
            <span style="margin-right: 8px;">{{ $t('modelConfigDialog.enable') }}</span>
            <el-switch v-model="formData.isEnabled" class="custom-switch"></el-switch>
          </div>
          <div style="display: none; align-items: center;">
            <span style="margin-right: 8px;">{{ $t('modelConfigDialog.setDefault') }}</span>
            <el-switch v-model="formData.isDefault" class="custom-switch"></el-switch>
          </div>
        </div>
      </div>

      <div style="height: 2px; background: #e9e9e9; margin-bottom: 22px;"></div>
      <el-form :model="formData" label-width="100px" label-position="left" class="custom-form">
        <div style="display: flex; gap: 20px; margin-bottom: 0;">
          <el-form-item :label="$t('modelConfigDialog.modelId')" prop="id" style="flex: 1;">
            <el-input v-model="formData.id" :placeholder="$t('modelConfigDialog.enterModelId')" class="custom-input-bg"
              maxlength="32"></el-input>
          </el-form-item>
        </div>
        <div style="display: flex; gap: 20px; margin-bottom: 0;">
          <el-form-item :label="$t('modelConfigDialog.modelName')" prop="modelName" style="flex: 1;">
            <el-input v-model="formData.modelName" :placeholder="$t('modelConfigDialog.enterModelName')"
              class="custom-input-bg"></el-input>
          </el-form-item>
          <el-form-item :label="$t('modelConfigDialog.modelCode')" prop="modelCode" style="flex: 1;">
            <el-input v-model="formData.modelCode" :placeholder="$t('modelConfigDialog.enterModelCode')"
              class="custom-input-bg"></el-input>
          </el-form-item>
        </div>

        <div style="display: flex; gap: 20px; margin-bottom: 0;">
          <el-form-item :label="$t('modelConfigDialog.supplier')" prop="supplier" style="flex: 1;">
            <el-select v-model="formData.supplier" :placeholder="$t('modelConfigDialog.selectSupplier')"
              class="custom-select custom-input-bg" style="width: 100%;" @focus="loadProviders" filterable>
              <el-option v-for="item in providers" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('modelConfigDialog.sortOrder')" prop="sortOrder" style="flex: 1;">
            <el-input v-model="formData.sort" type="number" :placeholder="$t('modelConfigDialog.enterSortOrder')"
              class="custom-input-bg"></el-input>
          </el-form-item>
        </div>


        <el-form-item :label="$t('modelConfigDialog.docLink')" prop="docLink" style="margin-bottom: 27px;">
          <el-input v-model="formData.docLink" :placeholder="$t('modelConfigDialog.enterDocLink')"
            class="custom-input-bg"></el-input>
        </el-form-item>

        <el-form-item :label="$t('modelConfigDialog.remark')" prop="remark" class="prop-remark">
          <el-input v-model="formData.remark" type="textarea" :rows="3"
            :placeholder="$t('modelConfigDialog.enterRemark')" :autosize="{ minRows: 3, maxRows: 5 }"
            class="custom-input-bg"></el-input>
        </el-form-item>
      </el-form>

      <div style="font-size: 20px; font-weight: bold; color: #3d4566; margin-bottom: 15px;">{{
        $t('modelConfigDialog.callInfo') }}</div>
      <div style="height: 2px; background: #e9e9e9; margin-bottom: 22px;"></div>

      <!-- Provider thường: render phẳng theo fields -->
      <el-form v-if="!isOriagentVoice" :model="formData.configJson" label-width="auto" label-position="left"
        class="custom-form">
        <div v-for="(row, rowIndex) in chunkedCallInfoFields" :key="rowIndex"
          style="display: flex; gap: 20px; margin-bottom: 0;">
          <el-form-item v-for="field in row" :key="field.prop" :label="field.label" :prop="field.prop" style="flex: 1;">
            <el-input v-model="formData.configJson[field.prop]" :placeholder="field.placeholder"
              :type="field.type || 'text'" class="custom-input-bg" :show-password="field.type === 'password'">
            </el-input>
          </el-form-item>
        </div>
      </el-form>

      <!-- Voice Oriagent: form đa giọng (mỗi API key một giọng) -->
      <div v-else class="oriagent-voice-form">
        <el-form :model="oriagentConfig" label-width="auto" label-position="left" class="custom-form">
          <el-form-item label="URL" style="margin-bottom: 18px;">
            <el-input v-model="oriagentConfig.api_url" :placeholder="oriagentDefaultUrl" class="custom-input-bg" />
          </el-form-item>
        </el-form>

        <div v-for="(voice, vIndex) in oriagentVoices" :key="vIndex" class="voice-group">
          <div class="voice-group-header">
            <span class="voice-group-title">{{ $t('ttsModel.voice') || 'Giọng' }} {{ vIndex + 1 }}</span>
            <el-button v-if="oriagentVoices.length > 1" type="text" class="voice-remove-btn"
              @click="removeVoice(vIndex)">{{ $t('ttsModel.delete') || 'Xóa' }}</el-button>
          </div>
          <el-form label-width="auto" label-position="left" class="custom-form">
            <div style="display: flex; gap: 20px; margin-bottom: 0;">
              <el-form-item :label="$t('ttsModel.voiceName') || 'Tên giọng'" style="flex: 1;">
                <el-input v-model="voice.name" maxlength="20" show-word-limit placeholder="VD: Giọng Mai"
                  class="custom-input-bg" />
              </el-form-item>
              <el-form-item :label="$t('ttsModel.languageType') || 'Loại ngôn ngữ'" style="flex: 1;">
                <el-input v-model="voice.language" placeholder="auto" class="custom-input-bg" />
              </el-form-item>
            </div>
            <el-form-item label="API key" style="margin-bottom: 0;">
              <el-input v-model="voice.api_key" type="password" show-password placeholder="vc_sk_live_..."
                class="custom-input-bg" />
            </el-form-item>
          </el-form>
        </div>

        <el-button type="text" class="add-voice-btn" @click="addVoice">
          + {{ $t('ttsModel.addNewVoice') || 'Thêm giọng nói mới' }}
        </el-button>
      </div>
    </div>

    <div style="display: flex;justify-content: center;">
      <el-button type="primary" @click="confirm" class="save-btn" :loading="saving" :disabled="saving">
        {{ $t('modelConfigDialog.save') }}
      </el-button>
    </div>
  </el-dialog>
</template>

<script>
import Api from '@/apis/api';
export default {
  name: 'AddModelDialog',
  props: {
    visible: { type: Boolean, required: true },
    modelType: { type: String, required: true }
  },
  data() {
    return {
      saving: false,
      providers: [],
      dialogVisible: false,
      providersLoaded: false,
      providerFields: [],
      currentProvider: null,
      // ── Voice Oriagent (đa giọng — mỗi API key một giọng) ──
      oriagentDefaultUrl: 'https://voice.oriagent.com/api/v1',
      oriagentConfig: { api_url: 'https://voice.oriagent.com/api/v1' },
      oriagentVoices: [{ name: '', language: 'auto', api_key: '' }],
      formData: {
        id: '',
        modelName: '',
        modelCode: '',
        supplier: '',
        sort: 1,
        docLink: '',
        remark: '',
        isEnabled: true,
        isDefault: true,
        configJson: {}
      }
    }
  },
  watch: {
    visible(val) {
      this.dialogVisible = val;
      if (val) {
        this.initConfigJson();
      } else {
        this.resetForm();
      }
    },
    'formData.supplier'(newVal) {
      this.currentProvider = this.providers.find(p => p.value === newVal);
      this.providerFields = this.currentProvider?.fields || [];
      if (newVal === 'oriagent_voice') {
        this.initOriagentVoice();
      } else {
        this.initDynamicConfig();
      }
    }
  },
  computed: {
    isOriagentVoice() {
      return this.formData.supplier === 'oriagent_voice';
    },
    dynamicCallInfoFields() {
      return this.providerFields;
    },
    chunkedCallInfoFields() {
      const chunkSize = 2;
      const result = [];
      for (let i = 0; i < this.dynamicCallInfoFields.length; i += chunkSize) {
        result.push(this.dynamicCallInfoFields.slice(i, i + chunkSize));
      }
      return result;
    }
  },
  methods: {
    loadProviders() {
      if (this.providersLoaded)
        return

      Api.model.getModelProviders(this.modelType, (data) => {
        this.providers = data.map(item => ({
          label: item.name,
          value: item.providerCode,
          fields: JSON.parse(item.fields || '[]').map(f => ({
            label: f.label,
            prop: f.key,
            type: f.type === 'password' ? 'password' : 'text',
            placeholder: `请输入${f.key}`
          }))
        }))
        this.providersLoaded = true
      })
    },
    initConfigJson() {
      const defaultConfig = {};
      this.providerFields.forEach(field => {
        defaultConfig[field.prop] = '';
      });
      this.formData.configJson = { ...defaultConfig };
    },
    handleVisibleChange(val) {
      this.dialogVisible = val;
      this.$emit('update:visible', val);
      if (!val) {
        this.resetForm();
      }
    },

    handleClose() {
      this.saving = false;
      this.$emit('update:visible', false);
    },
    initDynamicConfig() {
      const newConfig = {};
      this.providerFields.forEach(field => {
        newConfig[field.prop] = this.formData.configJson[field.prop] || '';
      });
      this.formData.configJson = newConfig;
    },
    // ── Voice Oriagent: khởi tạo form đa giọng (n = 1) ──
    initOriagentVoice() {
      this.oriagentConfig = { api_url: this.oriagentDefaultUrl };
      this.oriagentVoices = [{ name: '', language: 'auto', api_key: '' }];
    },
    addVoice() {
      this.oriagentVoices.push({ name: '', language: 'auto', api_key: '' });
    },
    removeVoice(index) {
      if (this.oriagentVoices.length > 1) {
        this.oriagentVoices.splice(index, 1);
      }
    },
    // Gom URL + danh sách giọng thành configJson; trả null nếu validate fail.
    buildOriagentConfigJson() {
      const apiUrl = (this.oriagentConfig.api_url || '').trim() || this.oriagentDefaultUrl;
      const voices = [];
      const names = new Set();
      for (const v of this.oriagentVoices) {
        const name = (v.name || '').trim();
        const apiKey = (v.api_key || '').trim();
        const language = (v.language || '').trim() || 'auto';
        if (!name || !apiKey) {
          this.$message.error(this.$t('ttsModel.voiceNameKeyRequired') || 'Mỗi giọng cần Tên giọng và API key');
          return null;
        }
        if (name.length > 20) {
          this.$message.error(this.$t('ttsModel.voiceNameTooLong') || 'Tên giọng tối đa 20 ký tự');
          return null;
        }
        if (names.has(name)) {
          this.$message.error(this.$t('ttsModel.voiceNameDuplicate') || 'Tên giọng bị trùng');
          return null;
        }
        names.add(name);
        voices.push({ name, language, api_key: apiKey });
      }
      return { type: 'oriagent_voice', api_url: apiUrl, voices };
    },
    confirm() {
      this.saving = true;

      // 校验模型ID不能为纯文字或空格
      if (this.formData.id && !this.validateModelId(this.formData.id)) {
        this.$message.error(this.$t('modelConfigDialog.invalidModelId'));
        this.saving = false;
        return;
      }

      if (!this.formData.supplier) {
        this.$message.error(this.$t('addModelDialog.requiredSupplier'));
        this.saving = false;
        return;
      }

      let configJson;
      if (this.isOriagentVoice) {
        configJson = this.buildOriagentConfigJson();
        if (!configJson) {
          this.saving = false;
          return;
        }
      } else {
        configJson = { ...this.formData.configJson, type: this.formData.supplier };
      }

      const submitData = {
        id: this.formData.id || '',
        modelName: this.formData.modelName || '',
        modelCode: this.formData.modelCode || '',
        supplier: this.formData.supplier,
        sort: this.formData.sort || 1,
        docLink: this.formData.docLink || '',
        remark: this.formData.remark || '',
        isEnabled: this.formData.isEnabled ? 1 : 0,
        isDefault: this.formData.isDefault ? 1 : 0,
        provideCode: this.formData.supplier,
        configJson
      };

      try {
        this.$emit('confirm', submitData);
        this.$emit('update:visible', false);
        this.resetForm();
      } catch (e) {
        console.error(e);
      } finally {
        this.saving = false;
      }
    },
    resetForm() {
      this.saving = false;
      this.formData = {
        id: '',
        modelName: '',
        modelCode: '',
        supplier: '',
        sort: 1,
        docLink: '',
        remark: '',
        isEnabled: true,
        isDefault: true,
        configJson: {}
      };
      // 重置加载状态
      this.providers = [];
      this.providersLoaded = false;
      // 重置字段配置
      this.providerFields = [];
      this.currentProvider = null;
      // reset form đa giọng Oriagent
      this.oriagentConfig = { api_url: this.oriagentDefaultUrl };
      this.oriagentVoices = [{ name: '', language: 'auto', api_key: '' }];
    },
    
    // 校验模型ID：不能为纯文字或空格
    validateModelId(modelId) {
      if (!modelId || typeof modelId !== 'string') {
        return false;
      }
      
      // 去除首尾空格
      const trimmedId = modelId.trim();
      
      // 检查是否为空或纯空格
      if (trimmedId === '') {
        return false;
      }
      
      // 检查是否只包含字母（纯文字）
      if (/^[a-zA-Z]+$/.test(trimmedId)) {
        return false;
      }
      
      // 检查是否包含空格
      if (/\s/.test(trimmedId)) {
        return false;
      }
      
      // 允许字母、数字、下划线、连字符
      if (!/^[a-zA-Z0-9_-]+$/.test(trimmedId)) {
        return false;
      }
      
      return true;
    }
  }
}
</script>

<style>
.custom-dialog {
  position: relative;
  border-radius: 20px;
  overflow: hidden;
  background: white;
  padding-bottom: 17px;
}

.custom-dialog .el-dialog__header {
  padding: 0;
  border-bottom: none;
}

.center-dialog {
  display: flex;
  align-items: center;
  justify-content: center;
}

.center-dialog .el-dialog {
  margin: 0 0 auto !important;
  display: flex;
  flex-direction: column;
}

.custom-close-btn {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 35px;
  height: 35px;
  border-radius: 50%;
  border: 2px solid #cfcfcf;
  background: none;
  font-size: 30px;
  font-weight: lighter;
  color: #cfcfcf;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
  padding: 0;
  outline: none;
}

.custom-close-btn:hover {
  color: #000000;
  border-color: #000000;
}

.custom-select .el-input__suffix {
  background: #e6e8ea;
  right: 6px;
  width: 20px;
  height: 20px;
  display: flex;
  justify-content: center;
  align-items: center;
  top: 9px;
}

.custom-select .el-input__suffix-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
}

.custom-select .el-icon-arrow-up:before {
  content: "";
  display: inline-block;
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-top: 7px solid #c0c4cc;
  position: relative;
  top: -2px;
  transform: rotate(180deg);
}

.custom-form .el-form-item {
  margin-bottom: 20px;
}

.custom-form .el-form-item__label {
  color: #3d4566;
  font-weight: normal;
  text-align: right;
  padding-right: 20px;

}

.custom-form .el-form-item.prop-remark .el-form-item__label {
  margin-top: -4px;
}

.custom-input-bg .el-input__inner::-webkit-input-placeholder,
.custom-input-bg .el-textarea__inner::-webkit-input-placeholder {
  color: #9c9f9e;
}


.custom-input-bg .el-input__inner,
.custom-input-bg .el-textarea__inner {
  background-color: #ffffff;
}


.save-btn {
  background: #e6f0fd;
  color: #237ff4;
  border: 1px solid #b3d1ff;
  width: 150px;
  height: 40px;
  font-size: 16px;
  transition: all 0.3s ease;
}

.save-btn:hover {
  background: linear-gradient(to right, #237ff4, #9c40d5);
  color: white;
  border: none;
}


.custom-switch .el-switch__core {
  border-radius: 20px;
  height: 23px;
  background-color: #c0ccda;
  width: 35px;
  padding: 0 20px;
}

.custom-switch .el-switch__core:after {
  width: 15px;
  height: 15px;
  background-color: white;
  top: 3px;
  left: 4px;
  transition: all .3s;
}

.custom-switch.is-checked .el-switch__core {
  border-color: #b5bcf0;
  background-color: #cfd7fa;
  padding: 0 20px;
}

.custom-switch.is-checked .el-switch__core:after {
  left: 100%;
  margin-left: -18px;
  background-color: #1b47ee;
}


[style*="display: flex"] {
  gap: 20px;
}

.custom-input-bg .el-input__inner {
  height: 32px;
}

/* ── Voice Oriagent: nhóm cấu hình giọng ── */
.oriagent-voice-form .voice-group {
  border: 1px solid #e6e8f0;
  border-radius: 10px;
  padding: 14px 16px 4px;
  margin-bottom: 14px;
  background: #fafbff;
}

.oriagent-voice-form .voice-group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.oriagent-voice-form .voice-group-title {
  font-weight: bold;
  color: #3d4566;
}

.oriagent-voice-form .voice-remove-btn {
  color: #f56c6c;
  padding: 0;
}

.oriagent-voice-form .add-voice-btn {
  color: #237ff4;
  font-size: 15px;
  padding: 4px 0;
}
</style>