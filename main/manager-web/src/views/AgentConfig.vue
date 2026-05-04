<template>
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
          :voice-options="voiceOptions"
          :language-options="languageOptions"
          :selected-language.sync="selectedLanguage"
          :oriagent-api-key.sync="oriagentApiKey"
          @filter-voices="filterVoicesByLanguage"
          @model-change="handleModelChange"
          @open-plugins="showFunctionDialog = true"
          @open-context="showContextProviderDialog = true"
        />
      </div>

      <!-- Overview Section -->
      <div v-if="activeTab === 'overview'" class="config-content-view">
        <div class="overview-section card-style">
           <div class="overview-header">
              <img src="@/assets/dashboard/overview.svg" class="header-icon" />
              <h3>{{ $t('roleConfig.tabOverview') }}</h3>
           </div>
           <div class="overview-grid">
              <div class="stat-card">
                 <span class="label">{{ $t("roleConfig.statAgentName") }}</span>
                 <span class="value">{{ agentForm.agentName }}</span>
              </div>
              <div class="stat-card">
                 <span class="label">{{ $t("roleConfig.statLlmProvider") }}</span>
                 <span class="value">{{ llmModeTypeMap[agentForm.model.llmModelId] || 'Oriagent' }}</span>
              </div>
              <div class="stat-card">
                 <span class="label">{{ $t("roleConfig.statDevicesOnline") }}</span>
                 <span class="value">{{ onlineDeviceCount }}</span>
              </div>
           </div>
        </div>
      </div>

      <!-- History Section -->
      <div v-if="activeTab === 'history'" class="config-content-view">
        <ServerLogsSection />
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

    <VersionFooter />
  </div>
</template>

<script>
import Api from "@/apis/api";
import VersionFooter from "@/components/VersionFooter.vue";
import RoleConfigSection from "@/components/RoleConfigSection.vue";
import DeviceManagementSection from "@/components/DeviceManagementSection.vue";
import ServerLogsSection from "@/components/ServerLogsSection.vue";
import FunctionDialog from "@/components/FunctionDialog.vue";
import ContextProviderDialog from "@/components/ContextProviderDialog.vue";
import AgentConfigTabs from "@/components/AgentConfigTabs.vue";
import AddDeviceDialog from "@/components/AddDeviceDialog.vue";
import ManualAddDeviceDialog from "@/components/ManualAddDeviceDialog.vue";

export default {
  name: "AgentConfig",
  components: { 
    VersionFooter, RoleConfigSection, DeviceManagementSection, 
    ServerLogsSection, FunctionDialog, ContextProviderDialog,
    AgentConfigTabs, AddDeviceDialog, ManualAddDeviceDialog
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
      oriagentFields: [
        { key: "api_key", type: "string", label: "Oriagent API KEY" },
        { key: "model_name", type: "string", label: "Model Name" }
      ],
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
      
      // Oriagent API Key management
      oriagentApiKey: '',
      oriagentModelDetail: null,
    };
  },
  computed: {
    onlineDeviceCount() {
      return this.deviceList.filter(d => d.deviceStatus === 'online').length;
    }
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
          this.oriagentApiKey = data.data.oriagentApiKey || '';
          this.oriagentModelName = data.data.oriagentModelName || '';
          this.initialOriagentApiKey = this.oriagentApiKey;
          this.initialOriagentModelName = this.oriagentModelName;

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
              if (type === 'LLM') data.data.forEach(item => this.llmModeTypeMap[item.id] = item.type);
           }
        });
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
      const fields = ['agentName', 'systemPrompt'];
      fields.forEach(f => { if (this.agentForm[f] !== this.initialAgentForm[f]) diff[f] = this.agentForm[f]; });
      const modelFields = ['asrModelId', 'vadModelId', 'llmModelId', 'ttsModelId', 'intentModelId'];
      modelFields.forEach(f => { if (this.agentForm.model[f] !== this.initialAgentForm.model[f]) diff[f] = this.agentForm.model[f]; });
      if (this.agentForm.ttsVoiceId !== this.initialAgentForm.ttsVoiceId) diff.ttsVoiceId = this.agentForm.ttsVoiceId;
      if (this.selectedLanguage !== this.initialAgentForm.ttsLanguage) diff.ttsLanguage = this.selectedLanguage;
      diff.functions = this.currentFunctions.map(f => ({ pluginId: f.id, paramInfo: f.params }));
      diff.contextProviders = this.currentContextProviders;
      if (this.oriagentApiKey !== this.initialOriagentApiKey) diff.oriagentApiKey = this.oriagentApiKey;
      if (this.oriagentModelName !== this.initialOriagentModelName) diff.oriagentModelName = this.oriagentModelName;

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
         this.initialOriagentApiKey = this.oriagentApiKey;
         this.initialOriagentModelName = this.oriagentModelName;
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
.agent-config-view { 
   background: #f8fafc; // Oriagent Gray Background
   min-height: 100vh; 
   display: flex; 
   flex-direction: column;
   font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.sections-container { 
  max-width: 1800px; // Further increased for even larger screens
  width: 96%; 
  margin: 0 auto; 
  padding: 16px 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.config-content-view { 
  flex: 1;
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

.overview-section {
   .overview-header { display: flex; align-items: center; gap: 12px; margin-bottom: 30px; .header-icon { width: 24px; } h3 { margin: 0; font-size: 20px; color: #313133; font-weight: 700; } }
   .overview-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px; }
   .stat-card { background: white; padding: 28px; border-radius: 20px; display: flex; flex-direction: column; gap: 12px; border: 1px solid #f1f5f9; box-shadow: 0 2px 4px rgba(0,0,0,0.02);
      .label { color: #64748b; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; }
      .value { color: #313133; font-size: 24px; font-weight: 800; }
   }
}
</style>
