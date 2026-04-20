<template>
  <div class="device-management-section">
    <el-card class="device-card" shadow="never">
      <div class="section-title-bar">
        <h3>{{ $t('device.management') }}</h3>
        <div class="search-box">
           <el-input :placeholder="$t('device.searchPlaceholder')" v-model="searchKeyword" size="small" @keyup.enter.native="handleSearch" clearable />
           <el-button size="small" @click="handleSearch">{{ $t('device.search') }}</el-button>
        </div>
      </div>

      <el-table ref="deviceTable" :data="paginatedDeviceList" class="transparent-table" v-loading="loading">
        <el-table-column :label="$t('modelConfig.select')" align="center" width="60" type="selection"></el-table-column>
        
        <el-table-column :label="$t('device.model')" prop="model" align="center">
          <template slot-scope="scope">
            <span style="font-weight: 700;">{{ getFirmwareTypeName(scope.row.model) }}</span>
          </template>
        </el-table-column>
        
        <el-table-column :label="$t('device.macAddress')" prop="macAddress" align="center">
          <template slot-scope="scope">
            <code style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-weight: bold;">{{ scope.row.macAddress }}</code>
          </template>
        </el-table-column>

        <el-table-column v-if="mqttServiceAvailable" :label="$t('device.deviceStatus')" align="center">
          <template slot-scope="scope">
            <div :class="['status-tag', scope.row.deviceStatus]">
              {{ scope.row.deviceStatus === 'online' ? $t('device.online') : $t('device.offline') }}
            </div>
          </template>
        </el-table-column>

        <el-table-column :label="$t('device.remark')" align="center">
          <template #default="{ row }">
            <el-input v-show="row.isEdit" v-model="row.remark" size="mini" @blur="row.isEdit = false" @keyup.enter.native="row.isEdit = false" />
            <div v-show="!row.isEdit" class="remark-text" @click="row.isEdit = true">
              <span>{{ row.remark || '-' }}</span>
              <i class="el-icon-edit-outline"></i>
            </div>
          </template>
        </el-table-column>

        <el-table-column :label="$t('device.autoUpdate')" align="center">
          <template slot-scope="scope">
            <el-switch v-model="scope.row.otaSwitch" size="mini" active-color="#08c45b" inactive-color="#ef4444" />
          </template>
        </el-table-column>

        <el-table-column :label="$t('device.operation')" align="center">
          <template slot-scope="scope">
            <el-button size="mini" type="text" style="color: #ef4444; font-weight: 700;" @click="handleUnbind(scope.row.device_id)">
              {{ $t('device.unbind') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="table_bottom">
        <div class="ctrl_btn">
          <el-button type="success" size="mini" @click="$emit('add-device')">{{ $t('device.bindWithCode') }}</el-button>
          <el-button type="danger" size="mini" @click="deleteSelected">{{ $t('device.unbind') }}</el-button>
        </div>
        <el-pagination
          @current-change="handleCurrentChange"
          :current-page.sync="currentPage"
          :page-size="pageSize"
          layout="total, prev, pager, next"
          :total="filteredDeviceList.length">
        </el-pagination>
      </div>
    </el-card>
  </div>
</template>

<script>
import Api from '@/apis/api';

export default {
  name: "DeviceManagementSection",
  props: {
    agentId: String,
    deviceList: Array,
    loading: Boolean,
    mqttServiceAvailable: Boolean,
    firmwareTypes: Array
  },
  data() {
    return {
      currentPage: 1,
      pageSize: 10,
      searchKeyword: "",
      activeSearchKeyword: ""
    };
  },
  computed: {
    filteredDeviceList() {
      const keyword = this.activeSearchKeyword.toLowerCase();
      if (!keyword) return this.deviceList;
      return this.deviceList.filter(device =>
        (device.model && device.model.toLowerCase().includes(keyword)) ||
        (device.macAddress && device.macAddress.toLowerCase().includes(keyword))
      );
    },
    paginatedDeviceList() {
      const start = (this.currentPage - 1) * this.pageSize;
      return this.filteredDeviceList.slice(start, start + this.pageSize);
    }
  },
  methods: {
    handleSearch() {
      this.activeSearchKeyword = this.searchKeyword;
      this.currentPage = 1;
    },
    handleCurrentChange(val) {
      this.currentPage = val;
    },
    getFirmwareTypeName(type) {
      const ft = this.firmwareTypes.find(item => item.key === type);
      return ft ? ft.name : type;
    },
    handleUnbind(id) {
       this.$confirm(this.$t('device.confirmUnbind'), this.$t('message.warning'), { type: 'warning' })
       .then(() => {
          Api.device.unbindDevice(id, ({ data }) => {
            if (data.code === 0) {
              this.$message.success(this.$t('device.unbindSuccess'));
              this.$emit('refresh');
            }
          });
       });
    },
    deleteSelected() {
      const selected = this.deviceList.filter(d => d.selected);
      if (selected.length === 0) return this.$message.warning(this.$t('device.selectAtLeastOne'));
      this.$confirm(this.$t('device.confirmBatchUnbind').replace('{count}', selected.length), 'Warning', { type: 'warning' })
      .then(() => {
         selected.forEach(d => {
            Api.device.unbindDevice(d.device_id, () => {});
         });
         this.$message.success('Request sent');
         setTimeout(() => this.$emit('refresh'), 1000);
      });
    }
  }
};
</script>

<style scoped lang="scss">
$ori-dark: #313133;
$ori-slate: #64748b;
$ori-green: #08c45b;
$ori-border: #f1f5f9;

.device-management-section { padding: 0; animation: fadeIn 0.4s ease; }

.device-card {
  border-radius: 20px; border: 1px solid $ori-border; background: white;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); padding: 32px;
}

.section-title-bar {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px;
  h3 { margin: 0; font-size: 20px; font-weight: 700; color: $ori-dark; }
}

.search-box {
  display: flex; gap: 12px;
  ::v-deep .el-input__inner { border-radius: 12px; background: #f8fafc; border-color: $ori-border; }
  .el-button { border-radius: 12px; font-weight: 600; border-color: $ori-border; }
}

.transparent-table {
  ::v-deep th { background: #f8fafc !important; color: $ori-slate; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; padding: 16px 0; border-bottom: 1px solid $ori-border; }
  ::v-deep td { padding: 16px 0; color: $ori-dark; font-size: 13px; font-weight: 500; border-bottom: 1px solid #f8fafc; }
  ::v-deep .el-table__row:hover td { background-color: #f8fafc !important; }
}

.status-tag { 
  font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; padding: 4px 10px; border-radius: 8px;
  &.online { background: #f0fdf4; color: $ori-green; border: 1px solid #dcfce7; }
  &.offline { background: #fff1f2; color: #ef4444; border: 1px solid #ffe4e6; }
}

.remark-text { 
  display: flex; align-items: center; gap: 8px; justify-content: center; cursor: pointer; transition: color 0.2s;
  &:hover { color: $ori-green; }
  i { font-size: 12px; opacity: 0.5; }
}

.table_bottom {
  display: flex; justify-content: space-between; align-items: center; margin-top: 32px; padding-top: 24px; border-top: 1px solid $ori-border;
}

.ctrl_btn {
  display: flex; gap: 12px;
  .el-button { border-radius: 10px; font-weight: 700; padding: 10px 20px; }
  .el-button--success { background: $ori-green; border-color: $ori-green; &:hover { background: #07b052; box-shadow: 0 4px 12px rgba(8, 196, 91, 0.2); } }
}

::v-deep .el-pagination {
  .el-pager li { background: transparent; color: $ori-slate; font-weight: 600; &.active { color: $ori-green; font-weight: 800; } }
  button { background: transparent; &:disabled { opacity: 0.3; } }
}

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
</style>
