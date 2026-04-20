<template>
  <div class="provider-config-form">
    <div v-if="showHeader" class="section-title">
      {{ $t("modelConfigDialog.callInfoOriagent") }}
    </div>
    <div v-loading="loading">
      <div v-if="dynamicFields.length === 0" style="color: #999; font-size: 12px; margin-top: 5px;">
        (No fields detected: {{ dynamicFields.length }})
      </div>
      <template v-for="(row, rowIndex) in chunkedFields">
        <div :key="rowIndex" class="config-row">
          <el-form-item v-for="field in row" :key="field.prop" 
            :label="(getTranslatedLabel(field)) + '：'" 
            :prop="field.prop">
            
            <!-- JSON Textarea Field -->
            <template v-if="field.type === 'json-textarea'">
              <el-input v-model="fieldJsonMap[field.prop]" type="textarea" :rows="3"
                :placeholder="$t('mcpToolCall.inputPlaceholder', { label: getTranslatedLabel(field) })" 
                class="form-input"
                @change="(val) => handleJsonChange(field.prop, val)" 
                @focus="isSensitiveField(field.prop) ? handleJsonInputFocus(field.prop, fieldJsonMap[field.prop]) : undefined"
              ></el-input>
            </template>

            <!-- Standard Input Field (Text/Password) -->
            <el-input v-else v-model="configData[field.prop]" 
              :placeholder="$t('mcpToolCall.inputPlaceholder', { label: getTranslatedLabel(field) })"
              :type="field.type"
              class="form-input" 
              :show-password="field.type === 'password'" 
              @focus="isSensitiveField(field.prop) ? handleInputFocus(field.prop, configData[field.prop]) : undefined"
              @blur="isSensitiveField(field.prop) ? handleInputBlur(field.prop) : undefined"
            ></el-input>
          </el-form-item>
        </div>
      </template>
    </div>
  </div>
</template>

<script>
import Api from "@/apis/api";

export default {
  name: "ProviderConfigForm",
  props: {
    modelId: { type: String, default: "" },
    providerCode: { type: String, required: true },
    modelType: { type: String, default: "LLM" },
    staticFields: { type: Array, default: null },
    showHeader: { type: Boolean, default: true },
    i18nPrefix: { type: String, default: "roleConfig" },
    hiddenFields: { type: Array, default: () => [] },
    forcedValues: { type: Object, default: () => ({}) }
  },
  data() {
    return {
      loading: false,
      dynamicFields: [],
      configData: {},
      fieldJsonMap: {},
      originalValues: {},
      sensitiveKeys: [
        "api_key",
        "personal_access_token",
        "access_token",
        "token",
        "secret",
        "access_key_secret",
        "secret_key",
      ],
      modelDetail: null
    };
  },
  computed: {
    visibleFields() {
      return this.dynamicFields.filter(f => !this.hiddenFields.includes(f.prop));
    },
    chunkedFields() {
      const chunkSize = 1; // Standardize to one per row for vertical layout in roleConfig
      const result = [];
      const fields = this.visibleFields;
      for (let i = 0; i < fields.length; i += chunkSize) {
        result.push(fields.slice(i, i + chunkSize));
      }
      return result;
    }
  },
  watch: {
    modelId: {
      handler(newVal) {
        if (newVal) {
          this.loadModelConfig();
        }
      },
      immediate: true
    },
    providerCode: {
      handler(newVal) {
        if (newVal) {
          this.loadProviderFields();
        }
      },
      immediate: true
    },
    dynamicFields: {
      handler(newVal) {
        if (newVal && newVal.length > 0) {
          if (this.modelDetail && this.modelDetail.configJson) {
            this.processModelData(this.modelDetail.configJson);
          } else {
            this.initializeConfig();
          }
        }
      }
    }
  },
  methods: {
    async loadProviderFields() {
      if (this.staticFields && this.staticFields.length > 0) {
        this.dynamicFields = this.staticFields.map(f => ({
          label: f.label,
          prop: f.key || f.prop,
          type: f.type === "dict" ? "json-textarea" : f.type === "password" ? "password" : "text",
        }));
        this.initializeConfig();
        this.loading = false;
        return;
      }
      
      this.loading = true;
      Api.model.getModelProviders(this.modelType, (data) => {
        const provider = data.find(p => p.providerCode === this.providerCode);
        if (provider) {
          this.dynamicFields = JSON.parse(provider.fields || "[]").map(f => ({
            label: f.label,
            prop: f.key,
            type: f.type === "dict" ? "json-textarea" : f.type === "password" ? "password" : "text",
          }));
          this.initializeConfig();
        }
        this.loading = false;
      });
    },
    loadModelConfig() {
      if (!this.modelId) return;
      
      // Chỉ hiện loading nếu chưa có sẵn dynamicFields (trường hợp không dùng staticFields)
      if (this.dynamicFields.length === 0) {
        this.loading = true;
      }
      
      this.fetchingConfig = true;
      Api.model.getModelConfig(this.modelId, ({ data }) => {
        if (data.code === 0 && data.data) {
          this.modelDetail = data.data;
          this.processModelData(data.data.configJson || {});
        }
        this.loading = false;
        this.fetchingConfig = false;
      });
    },
    initializeConfig() {
      this.dynamicFields.forEach(field => {
        if (!this.configData.hasOwnProperty(field.prop)) {
          const forcedVal = this.forcedValues[field.prop];
          this.$set(this.configData, field.prop, forcedVal !== undefined ? forcedVal : "");
        }
      });
    },
    processModelData(configJson) {
      this.dynamicFields.forEach(field => {
        // Apply forced value if exists, otherwise use configJson or empty string
        const forcedVal = this.forcedValues[field.prop];
        const value = forcedVal !== undefined ? forcedVal : (configJson[field.prop] || "");
        
        if (field.type === "json-textarea") {
          this.$set(this.fieldJsonMap, field.prop, JSON.stringify(value, null, 2));
          this.$set(this.configData, field.prop, value);
        } else {
          this.$set(this.configData, field.prop, String(value));
        }
      });
    },
    getTranslatedLabel(field) {
      const camelKey = this.toCamelCase(field.prop);
      const i18nKey = `${this.i18nPrefix}.${camelKey}`;
      return this.$te(i18nKey) ? this.$t(i18nKey) : field.label;
    },
    toCamelCase(str) {
      return str.replace(/([-_][a-z])/g, (group) =>
        group.toUpperCase().replace("-", "").replace("_", "")
      );
    },
    isSensitiveField(fieldName) {
      return this.sensitiveKeys.includes(fieldName.toLowerCase());
    },
    handleJsonChange(field, value) {
      try {
        const parsed = JSON.parse(value);
        this.configData[field] = parsed;
      } catch (e) {
        // Keep original if invalid during typing
      }
    },
    handleInputFocus(field, value) {
      if (value && value.includes("*")) {
        this.$set(this.originalValues, field, value);
        this.$set(this.configData, field, "");
      }
    },
    handleInputBlur(field) {
      if (!this.configData[field] || this.configData[field].trim() === "") {
        if (this.originalValues[field]) {
          this.$set(this.configData, field, this.originalValues[field]);
        }
        this.$delete(this.originalValues, field);
      }
    },
    handleJsonInputFocus(field, value) {
      if (value && value.includes("*")) {
        this.$set(this.fieldJsonMap, field, "");
      }
    },
    save() {
      return new Promise((resolve, reject) => {
        if (!this.modelId || !this.modelDetail) {
          resolve();
          return;
        }

        const formData = {
          ...this.modelDetail,
          configJson: { ...this.configData }
        };

        const params = {
          modelType: this.modelType,
          provideCode: this.providerCode,
          id: this.modelId,
          formData
        };

        Api.model.updateModel(params, ({ data }) => {
          if (data.code === 0) {
            resolve(data);
          } else {
            reject(data.msg);
          }
        });
      });
    }
  }
};
</script>

<style scoped>
.provider-config-form {
  margin-top: 10px;
}
.section-title {
  margin-bottom: 20px;
  font-weight: bold;
  color: #3d4566;
}
.config-row {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.form-input {
  width: 100%;
}
</style>
