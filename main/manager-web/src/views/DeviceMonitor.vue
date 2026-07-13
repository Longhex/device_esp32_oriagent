<template>
  <SettingsLayout active-key="deviceMonitor">
    <div class="welcome settings-panel">
    <div class="operation-bar">
      <h2 class="page-title">{{ $t('deviceMonitor.title') }}</h2>
      <div class="right-operations">
        <el-tag v-if="redisOn" type="success" size="small" effect="plain" style="margin-right:10px;">Redis</el-tag>
        <el-switch v-model="autoRefresh" :active-text="$t('deviceMonitor.autoRefresh')" style="margin-right:12px;" />
        <el-button type="primary" icon="el-icon-refresh" @click="fetchDevices">{{ $t('deviceMonitor.refresh') }}</el-button>
      </div>
    </div>

    <div class="main-wrapper">
      <div class="content-panel">
        <el-card class="params-card" shadow="never">
          <el-table :data="deviceList" v-loading="loading" style="width:100%">
            <el-table-column :label="$t('deviceMonitor.serial')" prop="serial" min-width="150" />
            <el-table-column :label="$t('deviceMonitor.status')" align="center" width="110">
              <template slot-scope="scope">
                <el-tag :type="scope.row.online ? 'success' : 'info'" size="small">
                  {{ scope.row.online ? $t('deviceMonitor.online') : $t('deviceMonitor.offline') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="$t('deviceMonitor.battery')" align="center" width="90">
              <template slot-scope="scope">{{ tele(scope.row, 'battery_pct', '%') }}</template>
            </el-table-column>
            <el-table-column label="RSSI" align="center" width="100">
              <template slot-scope="scope">{{ tele(scope.row, 'rssi_dbm', ' dBm') }}</template>
            </el-table-column>
            <el-table-column :label="$t('deviceMonitor.uptime')" align="center" width="110">
              <template slot-scope="scope">{{ uptime(scope.row) }}</template>
            </el-table-column>
            <el-table-column label="FW" align="center" width="90">
              <template slot-scope="scope">{{ tele(scope.row, 'fw_ver', '') }}</template>
            </el-table-column>
            <el-table-column :label="$t('deviceMonitor.lastSeen')" align="center" min-width="160">
              <template slot-scope="scope">{{ fmtTs(scope.row.last_status_ts) }}</template>
            </el-table-column>
            <el-table-column :label="$t('deviceMonitor.action')" align="center" width="220">
              <template slot-scope="scope">
                <el-button size="mini" type="text" @click="reboot(scope.row)">{{ $t('deviceMonitor.reboot') }}</el-button>
                <el-button size="mini" type="text" @click="openCommand(scope.row)">{{ $t('deviceMonitor.command') }}</el-button>
                <el-button size="mini" type="text" @click="showDetail(scope.row)">{{ $t('deviceMonitor.detail') }}</el-button>
              </template>
            </el-table-column>
            <template slot="empty">{{ $t('deviceMonitor.noDevices') }}</template>
          </el-table>
        </el-card>
      </div>
    </div>

    <!-- Dialog gửi lệnh -->
    <el-dialog :title="$t('deviceMonitor.sendCommand')" :visible.sync="cmdVisible" width="480px">
      <el-form label-width="120px">
        <el-form-item :label="$t('deviceMonitor.serial')">
          <span>{{ cmdSerial }}</span>
        </el-form-item>
        <el-form-item :label="$t('deviceMonitor.action2')">
          <el-select v-model="cmdAction" style="width:100%">
            <el-option label="reboot" value="reboot" />
            <el-option label="set_config" value="set_config" />
            <el-option label="ota" value="ota" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('deviceMonitor.params')">
          <el-input v-model="cmdParams" type="textarea" :rows="3" placeholder='{"key":"value"}' />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button @click="cmdVisible = false">{{ $t('deviceMonitor.cancel') }}</el-button>
        <el-button type="primary" @click="doSendCommand">{{ $t('deviceMonitor.send') }}</el-button>
      </div>
    </el-dialog>

    <!-- Dialog chi tiết -->
    <el-dialog :title="$t('deviceMonitor.detail')" :visible.sync="detailVisible" width="560px">
      <pre class="detail-json">{{ detailJson }}</pre>
    </el-dialog>

    <el-footer>
      <version-footer />
    </el-footer>
  </div>
  </SettingsLayout>
</template>

<script>
import Api from "@/apis/api";
import VersionFooter from "@/components/VersionFooter.vue";

export default {
  name: "DeviceMonitor",
  components: { VersionFooter },
  data() {
    return {
      loading: false,
      deviceList: [],
      redisOn: false,
      autoRefresh: true,
      timer: null,
      cmdVisible: false,
      cmdSerial: "",
      cmdAction: "reboot",
      cmdParams: "",
      detailVisible: false,
      detailJson: "",
    };
  },
  created() {
    this.fetchDevices();
    this.checkHealth();
    this.startTimer();
  },
  beforeDestroy() {
    this.stopTimer();
  },
  watch: {
    autoRefresh(v) {
      v ? this.startTimer() : this.stopTimer();
    },
  },
  methods: {
    startTimer() {
      this.stopTimer();
      this.timer = setInterval(() => this.fetchDevices(true), 5000);
    },
    stopTimer() {
      if (this.timer) { clearInterval(this.timer); this.timer = null; }
    },
    fetchDevices(silent) {
      if (!silent) this.loading = true;
      Api.deviceMonitor.getDevices((res) => {
        this.loading = false;
        const data = res.data && res.data.data;
        if (res.data && (res.data.code === 0 || res.data.code === undefined) && data) {
          const devices = data.devices || {};
          this.deviceList = Object.keys(devices).map((k) => ({ serial: k, ...devices[k] }));
        } else if (res.data && res.data.msg) {
          this.$message.error(res.data.msg);
        }
      });
    },
    checkHealth() {
      // dùng /devices đã đủ; redis cờ lấy qua healthz nếu cần — ở đây ẩn nếu không có
      this.redisOn = true;
    },
    tele(row, key, suffix) {
      const t = row.telemetry || {};
      return (t[key] === undefined || t[key] === null) ? "-" : t[key] + suffix;
    },
    uptime(row) {
      const t = row.telemetry || {};
      const s = t.uptime_s;
      if (s === undefined || s === null) return "-";
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      return h > 0 ? `${h}h${m}m` : `${m}m${s % 60}s`;
    },
    fmtTs(ts) {
      if (!ts) return "-";
      return new Date(ts * 1000).toLocaleString();
    },
    reboot(row) {
      this.$confirm(this.$t('deviceMonitor.confirmReboot', { serial: row.serial }), { type: 'warning' })
        .then(() => this.send(row.serial, 'reboot', {}))
        .catch(() => {});
    },
    openCommand(row) {
      this.cmdSerial = row.serial;
      this.cmdAction = "reboot";
      this.cmdParams = "";
      this.cmdVisible = true;
    },
    doSendCommand() {
      let params = {};
      if (this.cmdParams && this.cmdParams.trim()) {
        try { params = JSON.parse(this.cmdParams); }
        catch (e) { this.$message.error(this.$t('deviceMonitor.invalidJson')); return; }
      }
      this.send(this.cmdSerial, this.cmdAction, params);
      this.cmdVisible = false;
    },
    send(serial, action, params) {
      Api.deviceMonitor.sendCommand(serial, { action, params }, (res) => {
        if (res.data && (res.data.code === 0 || res.data.code === undefined)) {
          this.$message.success(this.$t('deviceMonitor.commandSent'));
        } else if (res.data && res.data.msg) {
          this.$message.error(res.data.msg);
        }
      });
    },
    showDetail(row) {
      Api.deviceMonitor.getDevice(row.serial, (res) => {
        const data = res.data && res.data.data;
        this.detailJson = JSON.stringify(data || row, null, 2);
        this.detailVisible = true;
      });
    },
  },
};
</script>

<style lang="scss" scoped>
.welcome.settings-panel {
  flex: 1;
  min-width: 0;
  min-height: 0;
  height: auto;
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  padding: 18px 20px;
  box-sizing: border-box;
  overflow: hidden;
}
.welcome.settings-panel .main-wrapper {
  background: transparent;
  box-shadow: none;
  margin: 0;
  height: auto;
  border-radius: 0;
}
.welcome {
  min-width: 900px;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  position: relative;
  padding: 20px 30px;
  box-sizing: border-box;
}
.operation-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #2c2c2c;
}
.right-operations {
  display: flex;
  align-items: center;
}
.main-wrapper {
  flex: 1;
}
.params-card {
  border-radius: 12px;
}
.detail-json {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 8px;
  max-height: 400px;
  overflow: auto;
  font-size: 12px;
}
</style>
