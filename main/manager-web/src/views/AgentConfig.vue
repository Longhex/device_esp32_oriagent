<template>
  <StudioLayout active="agents" contextLabel="Agent Robot Builder">
  <div class="agent-config-view">

    <AgentConfigTabs
      v-model="activeTab" 
      :saving="saving" 
      :agent-name="agentForm.agentName"
      @input="handleTabChange"
      @save="handleSaveAll" 
      @back="goBack"
    />

    <div class="sections-container" ref="container">
      <!-- Setup Section -->
      <div v-if="activeTab === 'setup'" class="config-content-view">
        <RoleConfigSection 
          ref="roleSection"
          :agent-id="agentId"
          :form="agentForm"
          :model-options="modelOptions"
          :llm-mode-type-map="llmModeTypeMap"
          :voice-options="voiceOptions"
          :language-options="languageOptions"
          :selected-language.sync="selectedLanguage"
          @filter-voices="filterVoicesByLanguage"
          @model-change="handleModelChange"
          @open-plugins="showFunctionDialog = true"
          @open-context="showContextProviderDialog = true"
        />
      </div>

      <!-- Overview Section -->
      <div v-if="activeTab === 'overview'" class="config-content-view">
        <AgentOverviewSection :agent-name="agentForm.agentName" :devices="deviceList" />
      </div>

      <!-- History Section -->
      <div v-if="activeTab === 'history'" class="config-content-view">
        <ChatHistorySection :agent-id="agentId" :agent-name="agentForm.agentName" />
      </div>

      <!-- Device Section -->
      <div v-if="activeTab === 'device'" class="config-content-view">
        <DeviceManagementSection 
          :agent-id="agentId"
          :device-list="deviceList"
          :loading="loadingDevices"
          :mqtt-service-available="mqttServiceAvailable"
          :firmware-types="firmwareTypes"
          @refresh="fetchDevices"
          @add-device="showAddDeviceDialog = true"
          @manual-add="showManualAddDeviceDialog = true"
        />
      </div>
    </div>

    <!-- Dialogs -->
    <add-device-dialog :visible.sync="showAddDeviceDialog" :agent-id="agentId" @refresh="fetchDevices" />
    <manual-add-device-dialog :visible.sync="showManualAddDeviceDialog" :agent-id="agentId" @refresh="fetchDevices" />
    <function-dialog 
        v-model="showFunctionDialog" 
        :functions="currentFunctions" 
        :all-functions="allFunctions" 
        :agent-id="agentId" 
        @update-functions="handleUpdateFunctions" 
        @dialog-closed="handleDialogClosed" />
    
    <context-provider-dialog 
        :visible.sync="showContextProviderDialog" 
        :providers="currentContextProviders" 
        @confirm="handleUpdateContext" />
  </div>
  </StudioLayout>
</template>

<script>
import Api from "@/apis/api";
import StudioLayout from "@/components/StudioLayout.vue";
import RoleConfigSection from "@/components/RoleConfigSection.vue";
import DeviceManagementSection from "@/components/DeviceManagementSection.vue";
import ChatHistorySection from "@/components/ChatHistorySection.vue";
import FunctionDialog from "@/components/FunctionDialog.vue";
import ContextProviderDialog from "@/components/ContextProviderDialog.vue";
import AgentConfigTabs from "@/components/AgentConfigTabs.vue";
import AgentOverviewSection from "@/components/AgentOverviewSection.vue";
import AddDeviceDialog from "@/components/AddDeviceDialog.vue";
import ManualAddDeviceDialog from "@/components/ManualAddDeviceDialog.vue";

export default {
  name: "AgentConfig",
  components: {
    StudioLayout, RoleConfigSection, DeviceManagementSection,
    ChatHistorySection, FunctionDialog, ContextProviderDialog,
    AgentConfigTabs, AddDeviceDialog, ManualAddDeviceDialog, AgentOverviewSection
  },
  data() {
    return {
      agentId: this.$route.query.agentId,
      activeTab: 'setup',
      saving: false,
      loadingDevices: false,
      agentForm: { model: {} },
      initialAgentForm: null,
      deviceList: [],
      initialDeviceList: null,
      modelOptions: {},
      voiceOptions: [],
      languageOptions: [],
      selectedLanguage: '',
      llmModeTypeMap: {},
      firmwareTypes: [],
      mqttServiceAvailable: false,
      voiceDetails: {},
      
      // Dialog states
      showFunctionDialog: false,
      showContextProviderDialog: false,
      showAddDeviceDialog: false,
      showManualAddDeviceDialog: false,
      currentFunctions: [],
      allFunctions: [],
      currentContextProviders: [],
    };
  },
  methods: {
    handleTabChange(id) {
       this.activeTab = id;
       // Update URL hash
       if (this.$route.hash !== '#' + id) {
          this.$router.replace({ 
            query: this.$route.query,
            hash: '#' + id 
          }).catch(() => {});
       }
       // Reset scroll to top for "new page" feel
       window.scrollTo(0, 0);
    },
    goBack() {
      this.$router.push('/home');
    },
    fetchAgentConfig() {
      Api.agent.getDeviceConfig(this.agentId, ({ data }) => {
        if (data.code === 0) {
          this.agentForm = { ...data.data, model: {
             ttsModelId: data.data.ttsModelId,
             vadModelId: data.data.vadModelId,
             asrModelId: data.data.asrModelId,
             llmModelId: data.data.llmModelId,
             intentModelId: data.data.intentModelId,
          }};
          this.initialAgentForm = JSON.parse(JSON.stringify(this.agentForm));
          if (this.agentForm.model.ttsModelId) this.fetchVoiceOptions(this.agentForm.model.ttsModelId);
          this.currentContextProviders = data.data.contextProviders || [];

          this.fetchAllFunctions().then(() => {
             const savedMappings = data.data.functions || [];
             this.currentFunctions = savedMappings.map(m => {
                const meta = this.allFunctions.find(f => f.id === m.pluginId);
                return meta ? { ...meta, params: { ...meta.params, ...(m.paramInfo || {}) } } : null;
             }).filter(f => f);
          });
        }
      });
    },
    fetchDevices() {
      this.loadingDevices = true;
      Api.device.getAgentBindDevices(this.agentId, ({ data }) => {
        this.loadingDevices = false;
        if (data.code === 0) {
          this.deviceList = data.data.map(d => ({
            device_id: d.id, model: d.board, macAddress: d.macAddress,
            remark: d.alias, otaSwitch: d.autoUpdate === 1,
            // lastConnectedAt/appVersion: tab Tổng quan cần để tính robots online
            lastConnectedAt: d.lastConnectedAt, appVersion: d.appVersion,
            selected: false, deviceStatus: 'offline'
          }));
          this.initialDeviceList = JSON.parse(JSON.stringify(this.deviceList));
          this.fetchDeviceStatus();
        }
      });
    },
    fetchDeviceStatus() {
       Api.device.getDeviceStatus(this.agentId, ({ data }) => {
          if (data.code === 0) this.mqttServiceAvailable = true;
       });
    },
    fetchModelOptions() {
      ["VAD", "ASR", "LLM", "Intent", "TTS"].forEach(type => {
        Api.model.getModelNames(type, "", ({ data }) => {
           if (data.code === 0) {
              this.$set(this.modelOptions, type, data.data.map(item => ({ value: item.id, label: item.modelName })));
           }
        });
      });
      // getModelNames không trả 'type' → dùng getLlmModelCodeList để biết type (openai/oriagent_ws/...) từng model LLM
      Api.model.getLlmModelCodeList("", ({ data }) => {
        if (data.code === 0 && Array.isArray(data.data)) {
          data.data.forEach(item => this.$set(this.llmModeTypeMap, item.id, item.type));
        }
      });
    },
    fetchAllFunctions() {
       return new Promise((resolve) => {
          Api.model.getPluginFunctionList(null, ({ data }) => {
             if (data.code === 0) {
                this.allFunctions = data.data.map(item => ({ ...item, params: JSON.parse(item.fields || '[]').reduce((m, f) => ({ ...m, [f.key]: f.default }), {}) }));
                resolve();
             }
          });
       });
    },
    fetchVoiceOptions(modelId) {
      Api.model.getModelVoices(modelId, "", ({ data }) => {
        if (data.code === 0 && data.data) {
          this.voiceDetails = data.data.reduce((acc, voice) => { acc[voice.id] = voice; return acc; }, {});
          const allLanguages = new Set();
          data.data.forEach(voice => { if (voice.languages) voice.languages.split(/[、]/).forEach(l => allLanguages.add(l.trim())); });
          this.languageOptions = Array.from(allLanguages).map(l => ({ value: l, label: l }));
          this.selectedLanguage = this.agentForm.ttsLanguage || (this.languageOptions[0]?.value || '');
          this.filterVoicesByLanguage();
        }
      });
    },
    filterVoicesByLanguage() {
      const allVoices = Object.values(this.voiceDetails);
      const filtered = allVoices.filter(v => v.languages?.includes(this.selectedLanguage) || Boolean(v.isClone));
      this.voiceOptions = filtered.map(v => ({ value: v.id, label: v.name }));
    },
    handleModelChange({ type, value }) { if (type === 'TTS') this.fetchVoiceOptions(value); },
    handleUpdateFunctions(selected) { this.currentFunctions = selected; },
    handleDialogClosed() { this.showFunctionDialog = false; },
    handleUpdateContext(providers) { this.currentContextProviders = providers; },
    
    handleSaveAll() {
      this.saving = true;
      const promises = [];
      const diff = {};
      const fields = ['agentName', 'systemPrompt', 'oriagentApiKey', 'fillerEnabled', 'fillerDelayMs', 'fillerPhrases'];
      fields.forEach(f => { if (this.agentForm[f] !== this.initialAgentForm[f]) diff[f] = this.agentForm[f]; });
      const modelFields = ['asrModelId', 'vadModelId', 'llmModelId', 'ttsModelId', 'intentModelId'];
      modelFields.forEach(f => { if (this.agentForm.model[f] !== this.initialAgentForm.model[f]) diff[f] = this.agentForm.model[f]; });
      if (this.agentForm.ttsVoiceId !== this.initialAgentForm.ttsVoiceId) diff.ttsVoiceId = this.agentForm.ttsVoiceId;
      if (this.selectedLanguage !== this.initialAgentForm.ttsLanguage) diff.ttsLanguage = this.selectedLanguage;
      diff.functions = this.currentFunctions.map(f => ({ pluginId: f.id, paramInfo: f.params }));
      diff.contextProviders = this.currentContextProviders;

      promises.push(new Promise((resolve) => {
         Api.agent.updateAgentConfig(this.agentId, diff, () => resolve());
      }));
      
      // Removed global Oriagent model config update

      this.deviceList.forEach((d, i) => {
         const init = this.initialDeviceList[i];
         if (d.remark !== init.remark || d.otaSwitch !== init.otaSwitch) {
            promises.push(new Promise(r => Api.device.updateDeviceInfo(d.device_id, { alias: d.remark, autoUpdate: d.otaSwitch ? 1 : 0 }, () => r())));
         }
      });
      Promise.all(promises).then(() => {
         this.$message.success(this.$t('roleConfig.saveSuccess'));
         this.initialAgentForm = JSON.parse(JSON.stringify(this.agentForm));
         this.initialDeviceList = JSON.parse(JSON.stringify(this.deviceList));
      }).finally(() => { this.saving = false; });
    }
  },
  mounted() {
    this.fetchAgentConfig();
    this.fetchDevices();
    this.fetchModelOptions();
    Api.dict.getDictDataByType('FIRMWARE_TYPE').then(res => this.firmwareTypes = res.data);
    
    // Hash support on load
    if (this.$route.hash) {
       this.activeTab = this.$route.hash.replace('#', '');
    }
  }
};
</script>

<style lang="scss" scoped>
/* min-height:0 xuyên suốt chuỗi flex (giống .studio-model-wrap của trang Model AI):
   thiếu nó thì flex item không co được dưới kích thước nội dung -> chuỗi chiều cao
   đứt, panel con không lấp đủ chiều cao và overflow không ăn. */
.agent-config-view {
   background: transparent; // nen xam do StudioLayout lo, tranh 2 lop nen
   flex: 1;
   min-height: 0;
   display: flex;
   flex-direction: column;
   font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.sections-container {
  width: 100%; /* full-width khớp khung canh lề của top bar (nav header cùng nằm trong agent-config-view) */
  /* padding-bottom PHẢI = 0: đáy khung nội dung phải trùng tuyệt đối đáy card
     ORIAGENT. Trước để 16px nên panel trắng hụt đúng 16px so với đáy sidebar. */
  padding: 24px 0 0; /* khe thở dọc top bar -> cụm 3 box (24 = đồng bộ gap ngang giữa box) */
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.config-content-view {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  animation: fadeIn 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.card-style { 
  background: white; 
  border-radius: 20px; 
  padding: 32px; 
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03); 
  border: 1px solid #f1f5f9;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

</style>
