<template>
  <div class="server-logs-section">
    <div class="logs-layout-card">
      <!-- Left Column: Container List -->
      <div class="container-sidebar">
        <div class="sidebar-header">
          <i class="el-icon-monitor"></i>
          <span>Containers</span>
        </div>
        <div class="sidebar-scroll">
          <div 
            v-for="item in containerList" 
            :key="item"
            class="container-item"
            :class="{ active: currentContainer === item }"
            @click="selectContainer(item)"
            :title="item"
          >
            <i class="el-icon-cpu"></i>
            <span class="container-name">{{ item }}</span>
          </div>
          <div v-if="containerList.length === 0 && !loadingContainers" class="empty-list">
            No running containers
          </div>
          <div v-if="loadingContainers" class="loading-sidebar">
             <i class="el-icon-loading"></i>
          </div>
        </div>
      </div>

      <!-- Right Column: Logs Display -->
      <div class="logs-main">
        <div class="logs-header">
          <div class="header-left">
            <span class="status-dot" :class="{ 'is-loading': loading }"></span>
            <span class="current-label">{{ currentContainer || 'Select a container' }}</span>
          </div>
          <div class="header-right">
            <el-button type="primary" size="mini" icon="el-icon-refresh" @click="fetchLogs" :loading="loading">
              Refresh
            </el-button>
            <el-button size="mini" icon="el-icon-bottom" @click="scrollToBottom">
              Scroll
            </el-button>
          </div>
        </div>
        
        <div class="logs-container" ref="logsContainer">
          <pre v-if="logs" class="logs-content">{{ logs }}</pre>
          <div v-else-if="loading" class="loading-state">
            <i class="el-icon-loading"></i>
            <p>Fetching logs...</p>
          </div>
          <div v-else class="empty-state">
            <i class="el-icon-document-remove"></i>
            <p>Select a container to view logs</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import Api from '@/apis/api';

export default {
  name: "ServerLogsSection",
  data() {
    return {
      containerList: [],
      currentContainer: "",
      logs: "",
      loading: false,
      loadingContainers: false,
      timer: null
    };
  },
  mounted() {
    this.fetchContainers();
    // Auto refresh logs if a container is selected
    this.timer = setInterval(() => {
      if (this.currentContainer) {
        this.fetchLogs();
      }
    }, 15000);
  },
  beforeDestroy() {
    if (this.timer) clearInterval(this.timer);
  },
  methods: {
    fetchContainers() {
      this.loadingContainers = true;
      Api.admin.getContainers((res) => {
        this.loadingContainers = false;
        if (res.data && res.data.code === 0) {
          this.containerList = res.data.data;
          // Auto select the first container if none selected
          if (this.containerList.length > 0 && !this.currentContainer) {
            this.selectContainer(this.containerList[0]);
          }
        }
      });
    },
    selectContainer(name) {
      this.currentContainer = name;
      this.logs = ""; // Clear old logs
      this.fetchLogs();
    },
    fetchLogs() {
      if (!this.currentContainer) return;
      this.loading = true;
      Api.admin.getServerLogs(this.currentContainer, (res) => {
        this.loading = false;
        if (res.data && res.data.code === 0) {
          // Clean ANSI codes for better readability
          this.logs = this.filterAnsi(res.data.data);
          this.$nextTick(() => {
            this.scrollToBottom();
          });
        }
      });
    },
    filterAnsi(text) {
      if (!text) return "";
      // Regex to strip ANSI escape codes (color codes)
      return text.replace(/\u001b\[[0-9;]*m/g, "");
    },
    scrollToBottom() {
      const container = this.$refs.logsContainer;
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    }
  }
};
</script>

<style scoped lang="scss">
.server-logs-section {
  height: calc(100vh - 220px);
  min-height: 500px;
  animation: fadeIn 0.4s ease;
}

.logs-layout-card {
  display: flex;
  height: 100%;
  background: #ffffff;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  border: 1px solid #e2e8f0;
}

/* Sidebar Styling */
.container-sidebar {
  width: 260px;
  background: #f8fafc;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;

  .sidebar-header {
    padding: 16px 20px;
    background: #f1f5f9;
    font-size: 13px;
    font-weight: 700;
    color: #08c45b;
    display: flex;
    align-items: center;
    justify-content: flex-start; /* Ensure left alignment */
    gap: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid #e2e8f0;
    text-align: left;
  }

  .sidebar-scroll {
    flex: 1;
    overflow-y: auto;
    padding: 8px;

    &::-webkit-scrollbar { width: 4px; }
    &::-webkit-scrollbar-track { background: transparent; }
    &::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 2px; }
  }
}

.container-item {
  padding: 12px 16px;
  margin-bottom: 4px;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: flex-start; /* Ensure left alignment */
  gap: 12px;
  transition: all 0.2s;
  color: #64748b;
  text-align: left; /* Ensure text starts from left */

  i { font-size: 16px; flex-shrink: 0; }

  .container-name {
    font-size: 12px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
    text-align: left;
  }

  &:hover {
    background: #f1f5f9;
    color: #1e293b;
  }

  &.active {
    background: #ecfdf5;
    color: #059669;
    i { color: #059669; }
  }
}

/* Main Content Styling */
.logs-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  overflow: hidden;
}

.logs-header {
  padding: 12px 20px;
  background: #ffffff;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  justify-content: space-between;
  align-items: center;

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;
    .status-dot {
      width: 8px;
      height: 8px;
      background: #10b981;
      border-radius: 50%;
      &.is-loading {
        animation: pulse 1s infinite;
      }
    }
    .current-label {
      font-size: 13px;
      font-weight: 700;
      color: #334155;
      font-family: 'Inter', sans-serif;
    }
  }
}

.logs-container {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  background: #ffffff;
  text-align: left; /* Explicitly align left */
  
  &::-webkit-scrollbar { width: 8px; }
  &::-webkit-scrollbar-track { background: #f8fafc; }
  &::-webkit-scrollbar-thumb { background: #e2e8f0; border-radius: 4px; }
  &::-webkit-scrollbar-thumb:hover { background: #cbd5e1; }
}

.logs-content {
  margin: 0;
  padding: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #1a1a1a; /* Black text */
  text-align: left; /* Strict left alignment */
}

.loading-state, .empty-state, .loading-sidebar, .empty-list {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #94a3b8;
  gap: 12px;
  font-size: 13px;
}

.loading-sidebar { padding: 40px 0; }
.empty-list { padding: 20px; text-align: center; color: #666; font-style: italic; }

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.3; }
  100% { opacity: 1; }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
