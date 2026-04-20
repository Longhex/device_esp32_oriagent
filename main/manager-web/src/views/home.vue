<template>
  <div class="welcome">
    <!-- 公共头部 -->
    <el-main class="home-main">
      <div class="home-content">
        <!-- Hero Section -->
        <div class="add-device">
          <div class="add-device-bg">
            <div class="hero-text-area">
               <div class="greeting">{{ $t('home.greeting') }}</div>
               <div class="wish">{{ $t('home.wish') }}</div>
               <div class="hi-hint">Ready to manage your intelligent agents?</div>
               
               <div class="add-device-btn" @click="showAddDialog">
                 <div class="left-add">{{ $t('home.addAgent') }}</div>
               </div>
            </div>
          </div>
        </div>

        <!-- Search & Filter Section -->
        <div class="search-section">
          <div class="search-wrapper">
            <el-input 
              v-model="search" 
              :placeholder="$t('header.searchPlaceholder')" 
              class="modern-search-input"
              @keyup.enter.native="handleSearch"
              @focus="showHistory = true"
              @blur="hideSearchHistory"
              clearable
              ref="searchInput">
              <i slot="prefix" class="el-icon-search search-icon"></i>
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
          
          <div v-if="isSearching" class="search-status">
             <span class="status-badge">Searching: "{{ search }}"</span>
             <el-button type="text" icon="el-icon-close" @click="handleSearchReset">Clear Results</el-button>
          </div>
        </div>

        <!-- Agent Grid -->
        <div class="device-list-container">
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
              @chat-history="handleShowChatHistory" />
          </template>
        </div>
      </div>
      <AddWisdomBodyDialog :visible.sync="addDeviceDialogVisible" @confirm="handleWisdomBodyAdded" />
    </el-main>
    <el-footer>
      <version-footer />
    </el-footer>
    <chat-history-dialog :visible.sync="showChatHistory" :agent-id="currentAgentId" :agent-name="currentAgentName" />
  </div>

</template>

<script>
import Api from '@/apis/api';
import AddWisdomBodyDialog from '@/components/AddWisdomBodyDialog.vue';
import ChatHistoryDialog from '@/components/ChatHistoryDialog.vue';
import DeviceItem from '@/components/DeviceItem.vue';
import VersionFooter from '@/components/VersionFooter.vue';
import featureManager from '@/utils/featureManager';

export default {
  name: 'HomePage',
  components: { DeviceItem, AddWisdomBodyDialog, VersionFooter, ChatHistoryDialog },
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
      this.$confirm(this.$t('message.deleteConfirm'), this.$t('message.tips'), { type: 'warning' }).then(() => {
        Api.agent.deleteAgent(agentId, ({ data }) => {
          if (data.code === 0) {
            this.$message.success(this.$t('message.success'));
            this.fetchAgentList();
          }
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
.welcome {
  display: flex;
  flex-direction: column;
  flex: 1;
  width: 100%;
  background: #f8fafc;
}

.home-main {
  padding: 0;
  display: flex;
  flex-direction: column;
}

.home-content {
  max-width: 1440px;
  width: 96%;
  margin: 0 auto;
  padding: 40px 0;
}

.add-device {
  height: 240px;
  border-radius: 24px;
  overflow: hidden;
  margin-bottom: 40px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.05);
}

.add-device-bg {
  width: 100%;
  height: 100%;
  background-image: url("@/assets/home/banner.jpeg");
  background-size: cover;
  background-position: center;
  display: flex;
  align-items: center;
  padding: 0 60px;
  
  .hero-text-area {
     text-align: left;
     .greeting { font-size: 36px; font-weight: 800; color: #313133; }
     .wish { font-size: 18px; font-weight: 500; color: #64748b; margin-bottom: 8px; }
     .hi-hint { font-size: 14px; color: #94a3b8; margin-bottom: 24px; font-style: italic; }
  }
}

.add-device-btn {
  display: inline-flex;
  cursor: pointer;
  transition: all 0.2s ease;
  
  &:hover { 
    transform: translateY(-1px);
    .left-add {
      background: #22c55e; // Modern green highlight on hover
      box-shadow: 0 4px 12px rgba(34, 197, 94, 0.2);
    }
  }
  
  &:active { transform: translateY(0); }

  .left-add {
    padding: 6px 20px;
    height: 34px;
    border-radius: 17px;
    background: #000;
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
  }
}

.search-section {
  margin-bottom: 32px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  
  .search-wrapper {
    position: relative;
    max-width: 600px;
  }
  
  .search-status {
     display: flex;
     align-items: center;
     gap: 12px;
     .status-badge {
        background: #f1f5f9;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 600;
        color: #475569;
     }
  }
}

::v-deep .modern-search-input {
  .el-input__inner {
    height: 48px;
    border-radius: 16px;
    background: white;
    border: 1px solid #f1f5f9;
    padding-left: 45px;
    font-size: 15px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    transition: all 0.2s;
    
    &:focus { border-color: #08c45b; box-shadow: 0 10px 15px -3px rgba(8, 196, 91, 0.1); }
  }
  
  .search-icon { position: absolute; left: 15px; top: 14px; font-size: 18px; color: #94a3b8; }
}

.search-history-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  background: white;
  border: 1px solid #f1f5f9;
  border-radius: 16px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  overflow: hidden;
  
  .history-header {
    padding: 12px 16px;
    background: #f8fafc;
    display: flex;
    justify-content: space-between;
    align-items: center;
    span { font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
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
    
    &:hover { background: #f1f5f9; }
    span { font-size: 14px; color: #334155; }
    i { color: #94a3b8; font-size: 14px; padding: 4px; &:hover { color: #ef4444; } }
  }
}

.device-list-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 24px;
}

.skeleton-item {
  background: #fff;
  border-radius: 20px;
  padding: 24px;
  height: 140px;
  border: 1px solid #f1f5f9;
  position: relative;
  overflow: hidden;
}

.skeleton-line-short {
  height: 12px;
  background: #f0f2f5;
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
      rgba(255, 255, 255, 0.3),
      rgba(255, 255, 255, 0));
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(200%); }
}
</style>