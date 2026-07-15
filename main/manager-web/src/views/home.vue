<template>
  <StudioLayout active="agents" contextLabel="Agent Builder">
    <div class="studio-content-panel">
      <div class="studio-topbar-row">
      <div class="studio-search-wrap">
        <el-input
          v-model="search"
          placeholder="Tìm kiếm Robot Agent"
          class="studio-search-input"
          @keyup.enter.native="handleSearch"
          @focus="showHistory = true"
          @blur="hideSearchHistory"
          clearable
          ref="searchInput">
          <span slot="prefix" class="studio-ic studio-ic--search search-icon"></span>
        </el-input>

        <!-- Search History Dropdown -->
        <div v-if="showHistory && searchHistory.length > 0" class="search-history-dropdown">
           <div class="history-header">
              <span>{{ $t("header.searchHistory") }}</span>
              <el-button type="text" size="mini" @click="clearSearchHistory">{{ $t("header.clearHistory") }}</el-button>
           </div>
           <div class="history-list">
              <div v-for="(item, idx) in searchHistory" :key="idx" class="history-item" @mousedown="selectSearchHistory(item)">
                 <span>{{ item }}</span>
                 <i class="el-icon-close" @mousedown.stop="removeSearchHistory(idx)"></i>
              </div>
           </div>
        </div>
      </div>

      <div class="studio-create-btn" @click="showAddDialog"><span class="studio-ic studio-ic--create"></span>Create Robot Agent</div>
      </div>

      <div class="studio-board-grid">
      <div v-if="isSearching" class="search-status">
         <span class="status-badge">Searching: "{{ search }}"</span>
         <el-button type="text" icon="el-icon-close" @click="handleSearchReset">Clear Results</el-button>
      </div>

      <template v-if="isLoading">
        <div v-for="i in skeletonCount" :key="'skeleton-' + i" class="skeleton-item">
          <div class="skeleton-image"></div>
          <div class="skeleton-content">
            <div class="skeleton-line"></div>
            <div class="skeleton-line-short"></div>
          </div>
        </div>
      </template>

      <template v-else>
        <DeviceItem v-for="(item, index) in devices" :key="index" :device="item" :feature-status="featureStatus"
          @configure="goToRoleConfig" @deviceManage="handleDeviceManage" @delete="handleDeleteAgent"
          @chat-history="handleShowChatHistory" @edit-info="handleEditInfo" @duplicate="handleDuplicateAgent" />
      </template>
      </div>
    </div>

    <AddWisdomBodyDialog :visible.sync="addDeviceDialogVisible" @confirm="handleWisdomBodyAdded" />
    <EditAgentInfoDialog :visible.sync="editInfoVisible" :agent="editingAgent" @saved="fetchAgentList" />
    <chat-history-dialog :visible.sync="showChatHistory" :agent-id="currentAgentId" :agent-name="currentAgentName" />
  </StudioLayout>
</template>

<script>
import Api from '@/apis/api';
import AddWisdomBodyDialog from '@/components/AddWisdomBodyDialog.vue';
import ChatHistoryDialog from '@/components/ChatHistoryDialog.vue';
import DeviceItem from '@/components/DeviceItem.vue';
import EditAgentInfoDialog from '@/components/EditAgentInfoDialog.vue';
import StudioLayout from '@/components/StudioLayout.vue';
import featureManager from '@/utils/featureManager';

export default {
  name: 'HomePage',
  components: { DeviceItem, AddWisdomBodyDialog, ChatHistoryDialog, EditAgentInfoDialog, StudioLayout },
  data() {
    return {
      addDeviceDialogVisible: false,
      devices: [],
      originalDevices: [],
      search: "",
      isSearching: false,
      isLoading: true,
      skeletonCount: localStorage.getItem('skeletonCount') || 8,
      showChatHistory: false,
      showHistory: false,
      editInfoVisible: false,
      editingAgent: null,
      duplicating: false,
      currentAgentId: '',
      currentAgentName: '',
      searchHistory: [],
      SEARCH_HISTORY_KEY: "xiaozhi_search_history",
      MAX_HISTORY_COUNT: 5,
      // 功能状态
      featureStatus: {
        voiceprintRecognition: false,
        voiceClone: false,
        knowledgeBase: false
      }
    }
  },

  async mounted() {
    this.fetchAgentList();
    this.loadSearchHistory();
    await this.loadFeatureStatus();
  },

  methods: {
    // 加载历史记录
    loadSearchHistory() {
      const history = localStorage.getItem(this.SEARCH_HISTORY_KEY);
      this.searchHistory = history ? JSON.parse(history) : [];
    },
    saveSearchHistory(keyword) {
      if (!keyword || this.searchHistory.includes(keyword)) return;
      this.searchHistory.unshift(keyword);
      if (this.searchHistory.length > this.MAX_HISTORY_COUNT) this.searchHistory = this.searchHistory.slice(0, this.MAX_HISTORY_COUNT);
      localStorage.setItem(this.SEARCH_HISTORY_KEY, JSON.stringify(this.searchHistory));
    },
    hideSearchHistory() { setTimeout(() => { this.showHistory = false; }, 200); },
    selectSearchHistory(item) { this.search = item; this.handleSearch(); },
    removeSearchHistory(index) {
      this.searchHistory.splice(index, 1);
      localStorage.setItem(this.SEARCH_HISTORY_KEY, JSON.stringify(this.searchHistory));
    },
    clearSearchHistory() { this.searchHistory = []; localStorage.removeItem(this.SEARCH_HISTORY_KEY); },
    // 加载功能状态
    async loadFeatureStatus() {
      await featureManager.waitForInitialization();
      const config = featureManager.getConfig();
      this.featureStatus = {
        voiceprintRecognition: config.voiceprintRecognition,
        voiceClone: config.voiceClone,
        knowledgeBase: config.knowledgeBase
      };
    },

    showAddDialog() {
      this.addDeviceDialogVisible = true
    },
    goToRoleConfig(agentId) {
      this.$router.push({ path: '/agent-config', query: { agentId } })
    },
    handleWisdomBodyAdded(res) {
      this.fetchAgentList();
      this.addDeviceDialogVisible = false;
    },
    handleSearch(keyword) {
      const searchValue = (typeof keyword === 'string' ? keyword : this.search).trim();
      if (!searchValue) { this.handleSearchReset(); return; }

      this.isSearching = true;
      this.isLoading = true;
      this.saveSearchHistory(searchValue);

      const isMac = /^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$/.test(searchValue);
      const searchType = isMac ? 'mac' : 'name';
      Api.agent.searchAgent(searchValue, searchType, ({ data }) => {
        if (data?.data) { this.devices = data.data.map(item => ({ ...item, agentId: item.id })); }
        this.isLoading = false;
      }, (error) => {
        this.isLoading = false;
        this.$message.error(this.$t('message.searchFailed'));
      });
      if (this.$refs.searchInput) this.$refs.searchInput.blur();
    },
    handleSearchReset() {
      this.isSearching = false;
      this.search = "";
      this.devices = [...this.originalDevices];
    },
    fetchAgentList() {
      this.isLoading = true;
      Api.agent.getAgentList(({ data }) => {
        if (data.code === 0) {
          this.devices = data.data.map(item => ({ ...item, agentId: item.id }));
          this.originalDevices = [...this.devices];
          localStorage.setItem('skeletonCount', this.devices.length || 8);
        }
        this.isLoading = false;
      }, () => { this.isLoading = false; });
    },
    handleDeleteAgent(agentId) {
      // HTML tĩnh từ i18n, không nội suy dữ liệu người dùng -> không có đường XSS.
      const body = `<div class="ac-confirm-title">${this.$t('agentCard.deleteTitle')}</div>`
        + `<div class="ac-confirm-desc">${this.$t('agentCard.deleteDesc')}</div>`;
      this.$confirm(body, {
        dangerouslyUseHTMLString: true,
        showClose: false,
        type: 'warning',
        confirmButtonText: this.$t('agentCard.confirm'),
        cancelButtonText: this.$t('agentCard.cancel'),
        customClass: 'agent-delete-confirm'
      }).then(() => {
        Api.agent.deleteAgent(agentId, ({ data }) => {
          if (data.code === 0) {
            this.$message.success(this.$t('message.success'));
            this.fetchAgentList();
          }
        });
      }).catch(() => { });
    },
    handleEditInfo(device) {
      this.editingAgent = device;
      this.editInfoVisible = true;
    },
    parseParamInfo(value) {
      if (typeof value === 'string') {
        try { return JSON.parse(value || '{}'); } catch (e) { return {}; }
      }
      return value || {};
    },
    // Chép cấu hình sang agent mới. KHÔNG chép summaryMemory (ký ức tích luỹ của agent gốc)
    // và agentCode (định danh) — bản sao bắt đầu sạch.
    buildDuplicatePayload(cfg) {
      return {
        asrModelId: cfg.asrModelId,
        vadModelId: cfg.vadModelId,
        llmModelId: cfg.llmModelId,
        vllmModelId: cfg.vllmModelId,
        ttsModelId: cfg.ttsModelId,
        ttsVoiceId: cfg.ttsVoiceId,
        ttsLanguage: cfg.ttsLanguage,
        ttsVolume: cfg.ttsVolume,
        ttsRate: cfg.ttsRate,
        ttsPitch: cfg.ttsPitch,
        memModelId: cfg.memModelId,
        intentModelId: cfg.intentModelId,
        systemPrompt: cfg.systemPrompt,
        chatHistoryConf: cfg.chatHistoryConf,
        langCode: cfg.langCode,
        language: cfg.language,
        oriagentApiKey: cfg.oriagentApiKey,
        oriagentModelName: cfg.oriagentModelName,
        fillerEnabled: cfg.fillerEnabled,
        fillerDelayMs: cfg.fillerDelayMs,
        fillerPhrases: cfg.fillerPhrases,
        contextProviders: cfg.contextProviders || [],
        // PUT nhận paramInfo dạng object (xem AgentConfig.vue:266) — parse phòng khi GET trả chuỗi.
        functions: (cfg.functions || []).map(f => ({
          pluginId: f.pluginId,
          paramInfo: this.parseParamInfo(f.paramInfo)
        }))
      };
    },
    handleDuplicateAgent(device) {
      if (this.duplicating) return;
      this.duplicating = true;
      const fail = (msg) => {
        this.duplicating = false;
        this.$message.error(msg || this.$t('agentCard.duplicateFailed'));
      };

      Api.agent.getDeviceConfig(device.agentId, ({ data }) => {
        if (data?.code !== 0 || !data.data) return fail(data?.msg);
        const cfg = data.data;
        const newName = `${cfg.agentName || device.agentName} ${this.$t('agentCard.duplicateSuffix')}`.slice(0, 64);

        Api.agent.addAgent(newName, ({ data: created }) => {
          if (created?.code !== 0 || !created.data) return fail(created?.msg);

          Api.agent.updateAgentConfig(created.data, this.buildDuplicatePayload(cfg), ({ data: updated }) => {
            this.duplicating = false;
            // Agent đã tạo xong; nếu đắp cấu hình lỗi thì nó vẫn tồn tại (rỗng) -> báo rõ, vẫn refresh.
            if (updated?.code === 0) this.$message.success(this.$t('agentCard.duplicateSuccess'));
            else this.$message.warning(this.$t('agentCard.duplicatePartial'));
            this.fetchAgentList();
          });
        });
      });
    },
    handleDeviceManage(id) {
       this.$router.push({ path: '/agent-config', query: { agentId: id }, hash: '#device' });
    },
    handleShowChatHistory(agent) {
       this.currentAgentId = agent.id;
       this.currentAgentName = agent.agentName;
       this.showChatHistory = true;
    }
  }
}
</script>

<style lang="scss" scoped>
@import "./studio.scss";

/* 1 panel nội dung lớn: chứa hàng search+Create + lưới card (như Figma) */
/* min-height:0 -> panel đứng yên đúng chiều cao khả dụng (đáy trùng card ORIAGENT),
   phần cuộn đẩy xuống .studio-board-grid để ô tìm kiếm + nút Create không trôi. */
.studio-content-panel {
  @include studio-panel;
  background: $studio-soft-bg;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 22px;
}

.studio-topbar-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  flex-shrink: 0;
}

.studio-search-wrap {
  position: relative;
  width: 360px;
}

.studio-search-input ::v-deep .el-input__inner {
  height: 42px;
  line-height: 42px;
  border-radius: 999px;
  background: $studio-soft-bg;
  border: 1px solid $studio-border;
  padding-left: 38px;   /* chừa chỗ icon */
}

.studio-search-input ::v-deep .el-input__prefix {
  display: flex;
  align-items: center;
  left: 12px;
}

.studio-search-input ::v-deep .el-input__icon {
  line-height: 42px;
}

.search-icon {
  width: 18px;
  height: 18px;
  color: #9a9a9a;
}

.studio-create-btn {
  @include studio-black-pill;
}

.studio-board-grid {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  /* Cận trên PHẢI là 1fr, không được để số cố định (vd 380px): auto-fill đếm số cột
     theo cận trên nếu nó cố định -> cột kịch trần rồi chừa chỗ thừa thành khoảng trống. */
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
  align-content: start;
}

.search-status {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 12px;

  .status-badge {
    background: $studio-soft-bg;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 600;
    color: $studio-text-sub;
  }
}

.search-history-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  background: $studio-panel-bg;
  border: 1px solid $studio-border;
  border-radius: 16px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  overflow: hidden;

  .history-header {
    padding: 12px 16px;
    background: $studio-soft-bg;
    display: flex;
    justify-content: space-between;
    align-items: center;
    span { font-size: 11px; font-weight: 700; color: $studio-text-sub; text-transform: uppercase; letter-spacing: 0.05em; }
  }

  .history-list {
    max-height: 240px;
    overflow-y: auto;
  }

  .history-item {
    padding: 12px 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    cursor: pointer;
    transition: background 0.2s;

    &:hover { background: $studio-soft-bg; }
    span { font-size: 14px; color: $studio-text; }
    i { color: $studio-text-sub; font-size: 14px; padding: 4px; &:hover { color: #ef4444; } }
  }
}

.skeleton-item {
  background: $studio-soft-bg;
  border-radius: 14px;
  padding: 24px;
  height: 140px;
  border: 1px solid $studio-border;
  position: relative;
  overflow: hidden;
}

.skeleton-line-short {
  height: 12px;
  background: #eaeaea;
  border-radius: 4px;
  width: 50%;
}

.skeleton-item::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 50%;
  height: 100%;
  background: linear-gradient(90deg,
      rgba(255, 255, 255, 0),
      rgba(255, 255, 255, 0.5),
      rgba(255, 255, 255, 0));
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(200%); }
}
</style>

<style>
/* el-message-box render ra body nên style KHÔNG dùng scoped */
.agent-delete-confirm {
  width: 420px;
  border-radius: 14px;
  padding: 22px;
}
.agent-delete-confirm .el-message-box__header { display: none; }
.agent-delete-confirm .el-message-box__content { padding: 0; }
/* Icon cảnh báo: Element định vị absolute khi có title -> ép về luồng thường, nằm trên tiêu đề */
.agent-delete-confirm .el-message-box__status {
  position: static;
  display: block;
  font-size: 22px !important;
  margin-bottom: 12px;
  transform: none;
}
.agent-delete-confirm .el-message-box__message { padding-left: 0; }
.agent-delete-confirm .ac-confirm-title {
  font-size: 16px;
  font-weight: 600;
  color: #1d2939;
  margin-bottom: 8px;
}
.agent-delete-confirm .ac-confirm-desc {
  font-size: 13px;
  line-height: 1.6;
  color: #667085;
}
/* row-reverse: DOM là [Hủy, Xác nhận] -> hiện thành [Xác nhận][Hủy], giống Dify */
.agent-delete-confirm .el-message-box__btns {
  display: flex;
  flex-direction: row-reverse;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 22px;
}
.agent-delete-confirm .el-message-box__btns .el-button {
  margin: 0;
  height: 36px;
  padding: 0 18px;
  border-radius: 8px;
  font-weight: 500;
}
.agent-delete-confirm .el-message-box__btns .el-button--primary {
  background: #1a1a1c;
  border-color: #1a1a1c;
}
.agent-delete-confirm .el-message-box__btns .el-button--primary:hover {
  opacity: 0.88;
}
</style>
