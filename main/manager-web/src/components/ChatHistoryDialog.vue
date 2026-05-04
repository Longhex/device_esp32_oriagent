<template>
  <el-dialog
    :title="$t('roleConfig.tabHistory')"
    :visible.sync="dialogVisible"
    width="80%"
    :before-close="handleClose"
    custom-class="server-logs-dialog"
  >
    <div class="logs-container" ref="logsContainer">
      <div class="logs-header">
        <div class="header-left">
          <i class="el-icon-document"></i>
          <span>{{ $t('roleConfig.tabHistory') }}</span>
        </div>
        <div class="header-right">
          <el-button type="primary" size="mini" icon="el-icon-refresh" @click="fetchLogs" :loading="loading">
            Refresh
          </el-button>
        </div>
      </div>
      <div class="logs-body">
        <pre v-if="logs" class="logs-content">{{ logs }}</pre>
        <div v-else-if="loading" class="loading-state">
          <i class="el-icon-loading"></i>
          <p>Fetching logs...</p>
        </div>
        <div v-else class="empty-state">
          <p>No logs found or failed to load.</p>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script>
import Api from '@/apis/api';

export default {
  name: 'ChatHistoryDialog',
  props: {
    visible: { type: Boolean, default: false },
    agentId: { type: String, required: true },
    agentName: { type: String, required: true }
  },
  data() {
    return {
      dialogVisible: false,
      logs: "",
      loading: false,
      timer: null
    };
  },
  watch: {
    visible(val) {
      this.dialogVisible = val;
      if (val) {
        this.fetchLogs();
        this.timer = setInterval(this.fetchLogs, 10000); // Auto refresh every 10s
      } else {
        if (this.timer) clearInterval(this.timer);
      }
    },
    dialogVisible(val) {
      if (!val) {
        this.$emit('update:visible', false);
      }
    }
  },
  methods: {
    handleClose() {
      this.dialogVisible = false;
    },
    fetchLogs() {
      this.loading = true;
      Api.admin.getServerLogs((res) => {
        this.loading = false;
        if (res.data && res.data.code === 0) {
          this.logs = res.data.data;
          this.$nextTick(() => {
            this.scrollToBottom();
          });
        }
      });
    },
    scrollToBottom() {
      const container = this.$refs.logsContainer?.querySelector('.logs-body');
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    }
  }
};
</script>

<style scoped lang="scss">
.logs-container {
  display: flex;
  flex-direction: column;
  height: 70vh;
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 8px;
  overflow: hidden;
}

.logs-header {
  padding: 10px 20px;
  background: #252526;
  border-bottom: 1px solid #333;
  display: flex;
  justify-content: space-between;
  align-items: center;
  .header-left { display: flex; align-items: center; gap: 8px; font-weight: 600; i { color: #08c45b; } }
}

.logs-body {
  flex: 1;
  padding: 15px;
  overflow-y: auto;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.4;
  
  &::-webkit-scrollbar { width: 8px; }
  &::-webkit-scrollbar-track { background: #1e1e1e; }
  &::-webkit-scrollbar-thumb { background: #333; border-radius: 4px; }
}

.logs-content {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.loading-state, .empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #666;
  gap: 10px;
}
</style>

<style>
.server-logs-dialog {
  border-radius: 12px !important;
  overflow: hidden;
}
.server-logs-dialog .el-dialog__body {
  padding: 10px 20px 20px 20px;
}
</style>