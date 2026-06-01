<template>
  <div class="welcome">
    <div class="operation-bar">
      <h2 class="page-title">{{ $t('serialManagement.title') }}</h2>
      <div class="right-operations">
        <el-button type="primary" icon="el-icon-plus" @click="openDeclare">{{ $t('serialManagement.declare') }}</el-button>
        <el-button icon="el-icon-refresh" @click="fetchSerials">{{ $t('serialManagement.refresh') }}</el-button>
      </div>
    </div>

    <div class="main-wrapper">
      <div class="content-panel">
        <el-card class="params-card" shadow="never">
          <el-table :data="serialList" v-loading="loading" style="width:100%">
            <el-table-column :label="$t('serialManagement.serialNumber')" prop="serial" min-width="150" />
            <el-table-column :label="$t('serialManagement.statusCol')" align="center" width="120">
              <template slot-scope="scope">
                <el-tag :type="scope.row.status === 'activated' ? 'success' : 'warning'" size="small">
                  {{ scope.row.status === 'activated' ? $t('serialManagement.activated') : $t('serialManagement.declared') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="$t('serialManagement.batch')" prop="batch" align="center" width="120">
              <template slot-scope="scope">{{ scope.row.batch || '-' }}</template>
            </el-table-column>
            <el-table-column label="MAC" prop="mac" align="center" min-width="140">
              <template slot-scope="scope">{{ scope.row.mac || '-' }}</template>
            </el-table-column>
            <el-table-column :label="$t('serialManagement.declaredAt')" align="center" min-width="160">
              <template slot-scope="scope">{{ fmtTs(scope.row.declared_at) }}</template>
            </el-table-column>
            <el-table-column :label="$t('serialManagement.activatedAt')" align="center" min-width="160">
              <template slot-scope="scope">{{ fmtTs(scope.row.activated_at) }}</template>
            </el-table-column>
            <el-table-column :label="$t('serialManagement.action')" align="center" width="200">
              <template slot-scope="scope">
                <el-button size="mini" type="text" @click="activate(scope.row)">{{ $t('serialManagement.activate') }}</el-button>
                <el-button size="mini" type="text" style="color:#f56c6c;" @click="unbind(scope.row)">{{ $t('serialManagement.unbind') }}</el-button>
              </template>
            </el-table-column>
            <template slot="empty">{{ $t('serialManagement.noSerials') }}</template>
          </el-table>
        </el-card>
      </div>
    </div>

    <!-- Dialog khai báo -->
    <el-dialog :title="$t('serialManagement.declare')" :visible.sync="declareVisible" width="460px">
      <el-form label-width="120px">
        <el-form-item :label="$t('serialManagement.serialNumber')" required>
          <el-input v-model="newSerial" placeholder="HKHT2606010011" />
        </el-form-item>
        <el-form-item :label="$t('serialManagement.batch')">
          <el-input v-model="newBatch" />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button @click="declareVisible = false">{{ $t('serialManagement.cancel') }}</el-button>
        <el-button type="primary" @click="doDeclare">{{ $t('serialManagement.confirm') }}</el-button>
      </div>
    </el-dialog>

    <!-- Dialog hiện credential sau khi activate -->
    <el-dialog :title="$t('serialManagement.credential')" :visible.sync="credVisible" width="560px">
      <el-alert :title="$t('serialManagement.credentialHint')" type="warning" :closable="false" show-icon style="margin-bottom:12px;" />
      <pre class="detail-json">{{ credJson }}</pre>
      <div slot="footer">
        <el-button type="primary" @click="copyCred">{{ $t('serialManagement.copy') }}</el-button>
        <el-button @click="credVisible = false">{{ $t('serialManagement.close') }}</el-button>
      </div>
    </el-dialog>

    <el-footer>
      <version-footer />
    </el-footer>
  </div>
</template>

<script>
import Api from "@/apis/api";
import VersionFooter from "@/components/VersionFooter.vue";

export default {
  name: "SerialManagement",
  components: { VersionFooter },
  data() {
    return {
      loading: false,
      serialList: [],
      declareVisible: false,
      newSerial: "",
      newBatch: "",
      credVisible: false,
      credJson: "",
    };
  },
  created() {
    this.fetchSerials();
  },
  methods: {
    fetchSerials() {
      this.loading = true;
      Api.deviceMonitor.getSerials((res) => {
        this.loading = false;
        const data = res.data && res.data.data;
        if (data && data.serials) {
          this.serialList = data.serials.filter(Boolean);
        } else if (res.data && res.data.msg) {
          this.$message.error(res.data.msg);
        }
      });
    },
    fmtTs(ts) {
      if (!ts) return "-";
      return new Date(ts * 1000).toLocaleString();
    },
    openDeclare() {
      this.newSerial = "";
      this.newBatch = "";
      this.declareVisible = true;
    },
    doDeclare() {
      const serial = (this.newSerial || "").trim();
      if (!serial) { this.$message.error(this.$t('serialManagement.serialRequired')); return; }
      Api.deviceMonitor.declareSerial({ serial, batch: this.newBatch || null }, (res) => {
        if (res.data && (res.data.code === 0 || res.data.code === undefined)) {
          this.$message.success(this.$t('serialManagement.declareSuccess'));
          this.declareVisible = false;
          this.fetchSerials();
        } else if (res.data && res.data.msg) {
          this.$message.error(res.data.msg);
        }
      });
    },
    activate(row) {
      Api.deviceMonitor.activate({ serial: row.serial }, (res) => {
        const data = res.data && res.data.data;
        if (data && data.mqtt) {
          this.credJson = JSON.stringify(data, null, 2);
          this.credVisible = true;
          this.fetchSerials();
        } else if (res.data && res.data.msg) {
          this.$message.error(res.data.msg);
        }
      });
    },
    copyCred() {
      const ta = document.createElement("textarea");
      ta.value = this.credJson;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); this.$message.success(this.$t('serialManagement.copied')); }
      catch (e) { /* noop */ }
      document.body.removeChild(ta);
    },
    unbind(row) {
      this.$confirm(this.$t('serialManagement.confirmUnbind', { serial: row.serial }), { type: 'warning' })
        .then(() => {
          Api.deviceMonitor.deleteSerial(row.serial, (res) => {
            if (res.data && (res.data.code === 0 || res.data.code === undefined)) {
              this.$message.success(this.$t('serialManagement.unbindSuccess'));
              this.fetchSerials();
            } else if (res.data && res.data.msg) {
              this.$message.error(res.data.msg);
            }
          });
        })
        .catch(() => {});
    },
  },
};
</script>

<style lang="scss" scoped>
.welcome {
  min-width: 900px;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
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
  max-height: 360px;
  overflow: auto;
  font-size: 12px;
}
</style>
