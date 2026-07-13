<template>
  <div class="device-management-section">
    <div class="device-panel">
      <!-- Toolbar: tiêu đề + ô tìm kiếm (đồng bộ Model AI) -->
      <div class="studio-model-toolbar">
        <h2 class="studio-model-title">{{ $t('device.management') }}</h2>
        <div class="studio-search-group">
          <el-input
            :placeholder="$t('device.searchPlaceholder')"
            v-model="searchKeyword"
            class="search-input"
            clearable
            @keyup.enter.native="handleSearch"
          />
          <el-button class="btn-search" @click="handleSearch">{{ $t('device.search') }}</el-button>
        </div>
      </div>

      <el-card class="model-card" shadow="never">
        <el-table
          ref="deviceTable"
          style="width: 100%"
          v-loading="loading"
          :header-cell-style="{ background: 'transparent' }"
          :data="paginatedDeviceList"
          class="transparent-table"
          @selection-change="handleSelectionChange"
        >
          <el-table-column :label="$t('modelConfig.select')" align="center" width="55" type="selection"></el-table-column>

          <el-table-column :label="$t('device.model')" prop="model" align="center">
            <template slot-scope="scope">
              <span class="model-name-cell">
                <i class="el-icon-cpu model-name-icon"></i>{{ getFirmwareTypeName(scope.row.model) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column :label="$t('device.macAddress')" prop="macAddress" align="center">
            <template slot-scope="scope">
              <code class="mac-code">{{ scope.row.macAddress }}</code>
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
              <el-switch v-model="scope.row.otaSwitch" class="custom-switch" active-color="#08c45b" />
            </template>
          </el-table-column>

          <el-table-column :label="$t('device.operation')" align="center" width="120px">
            <template slot-scope="scope">
              <el-tooltip :content="$t('device.unbind')" placement="top" effect="light">
                <el-button
                  type="text"
                  circle
                  size="mini"
                  icon="el-icon-delete"
                  class="action-icon-btn action-icon-btn--danger"
                  @click="handleUnbind(scope.row.device_id)"
                ></el-button>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>

        <div class="table-footer">
          <div class="batch-actions">
            <el-button type="success" size="mini" class="add-btn" @click="$emit('add-device')">{{ $t('device.bindWithCode') }}</el-button>
            <el-button size="mini" type="primary" @click="$emit('manual-add')">{{ $t('device.manualAdd') }}</el-button>
            <el-button size="mini" type="danger" icon="el-icon-delete" @click="deleteSelected">{{ $t('device.unbind') }}</el-button>
          </div>

          <div class="custom-pagination">
            <el-select v-model="pageSize" @change="handlePageSizeChange" class="page-size-select">
              <el-option
                v-for="item in pageSizeOptions"
                :key="item"
                :label="$t('modelConfig.itemsPerPage', { items: item })"
                :value="item"
              ></el-option>
            </el-select>

            <button class="pagination-btn" :disabled="currentPage === 1" @click="goFirst">{{ $t('modelConfig.firstPage') }}</button>
            <button class="pagination-btn" :disabled="currentPage === 1" @click="goPrev">{{ $t('modelConfig.prevPage') }}</button>
            <button
              v-for="page in visiblePages"
              :key="page"
              class="pagination-btn"
              :class="{ active: page === currentPage }"
              @click="goToPage(page)"
            >{{ page }}</button>
            <button class="pagination-btn" :disabled="currentPage === pageCount || pageCount === 0" @click="goNext">{{ $t('modelConfig.nextPage') }}</button>
            <span class="total-text">{{ $t('modelConfig.totalRecords', { total }) }}</span>
          </div>
        </div>
      </el-card>
    </div>
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
      pageSizeOptions: [10, 20, 50, 100],
      searchKeyword: "",
      activeSearchKeyword: "",
      multipleSelection: []
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
    total() {
      return this.filteredDeviceList.length;
    },
    pageCount() {
      return Math.ceil(this.total / this.pageSize);
    },
    visiblePages() {
      const pages = [];
      const maxVisible = 3;
      let start = Math.max(1, this.currentPage - 1);
      let end = Math.min(this.pageCount, start + maxVisible - 1);
      if (end - start + 1 < maxVisible) {
        start = Math.max(1, end - maxVisible + 1);
      }
      for (let i = start; i <= end; i++) {
        pages.push(i);
      }
      return pages;
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
    handlePageSizeChange() {
      this.currentPage = 1;
    },
    goFirst() {
      this.currentPage = 1;
    },
    goPrev() {
      if (this.currentPage > 1) this.currentPage--;
    },
    goNext() {
      if (this.currentPage < this.pageCount) this.currentPage++;
    },
    goToPage(page) {
      this.currentPage = page;
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
    handleSelectionChange(val) {
      this.multipleSelection = val;
    },
    deleteSelected() {
      if (this.multipleSelection.length === 0) return this.$message.warning(this.$t('device.selectAtLeastOne'));
      this.$confirm(this.$t('device.confirmBatchUnbind').replace('{count}', this.multipleSelection.length), this.$t('message.warning'), { type: 'warning' })
      .then(() => {
         const promises = this.multipleSelection.map(d => {
            return new Promise(resolve => {
               Api.device.unbindDevice(d.device_id, () => resolve());
            });
         });
         Promise.all(promises).then(() => {
            this.$message.success(this.$t('common.success'));
            this.$emit('refresh');
         });
      });
    }
  }
};
</script>

<style scoped lang="scss">
@import "@/views/studio.scss";

.device-management-section { animation: fadeIn 0.4s ease; }

/* Panel nổi trắng bo góc — đồng bộ studio-model-panel của Model AI */
.device-panel {
  @include studio-panel;
  display: flex;
  flex-direction: column;
  padding: 18px 20px;
  box-sizing: border-box;
}

/* ── Toolbar (giống Model AI) ── */
.studio-model-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-shrink: 0;
  margin-bottom: 12px;
}
.studio-model-title { @include studio-title; margin: 0; white-space: nowrap; }
.studio-search-group { display: flex; gap: 8px; align-items: center; }
.search-input { width: 220px; }
.btn-search {
  background: linear-gradient(135deg, #555555, #a966ff);
  border: none;
  color: white;
  border-radius: $studio-radius-pill;
  &:hover { opacity: 0.9; transform: translateY(-1px); }
}
::v-deep .search-input .el-input__inner {
  border-radius: $studio-radius-pill;
  border: 1px solid $studio-border;
  background-color: $studio-soft-bg;
  transition: border-color 0.2s;
  &:focus { border-color: #555555; outline: none; }
}

/* ── Card + bảng ── */
.model-card {
  background: white;
  border: none;
  box-shadow: none;
  ::v-deep .el-card__body { padding: 0; }
}

.transparent-table {
  background: white;
  width: 100%;
  ::v-deep th {
    background: transparent !important;
    color: $studio-text-sub;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 14px 0;
    border-bottom: 1px solid $studio-border;
  }
  ::v-deep td {
    padding: 14px 0;
    color: $studio-text;
    font-size: 13px;
    font-weight: 500;
    border-bottom: 1px solid $studio-soft-bg;
  }
  ::v-deep .el-table__row:hover td { background-color: $studio-soft-bg !important; }
  ::v-deep .cell { padding-left: 10px; padding-right: 10px; }
}

.model-name-cell { display: inline-flex; align-items: center; gap: 6px; }
.model-name-icon { color: $studio-text-sub; }

.mac-code {
  background: $studio-soft-bg;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  color: $studio-text;
}

.status-tag {
  font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 4px 10px; border-radius: 8px; display: inline-block;
  &.online { background: #f0fdf4; color: $studio-accent; border: 1px solid #dcfce7; }
  &.offline { background: #fff1f2; color: #ef4444; border: 1px solid #ffe4e6; }
}

.remark-text {
  display: flex; align-items: center; gap: 8px; justify-content: center; cursor: pointer; transition: color 0.2s;
  &:hover { color: $studio-accent; }
  i { font-size: 12px; opacity: 0.5; }
}

/* Cụm action icon tròn (xóa) — giống Model AI */
.action-icon-btn {
  margin: 0 3px;
  padding: 0;
  width: 28px;
  height: 28px;
  color: $studio-text-sub !important;
  border: 1px solid $studio-border !important;
  background: $studio-soft-bg !important;
  &:hover { color: $studio-text !important; background: darken(#f7f7f7, 4%) !important; }
  &.action-icon-btn--danger:hover { color: #fd5b63 !important; border-color: #fd5b63 !important; }
}

/* ── Footer: batch actions + phân trang custom ── */
.table-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  flex-shrink: 0;
  min-height: 60px;
  margin-top: 8px;
  background: white;
}

.batch-actions {
  display: flex;
  gap: 8px;
  .el-button {
    min-width: 72px;
    height: 32px;
    padding: 7px 12px;
    font-size: 12px;
    border-radius: $studio-radius-pill;
    line-height: 1;
    font-weight: 500;
    border: none;
    transition: all 0.3s ease;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
    &:hover { transform: translateY(-1px); box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15); }
  }
  .el-button--primary { background: #5f70f3 !important; color: white; }
  .add-btn { background: $studio-accent !important; color: white; }
  .el-button--danger { background: #fd5b63; color: white; }
}

.custom-pagination {
  display: flex;
  align-items: center;
  gap: 8px;

  .pagination-btn:first-child,
  .pagination-btn:nth-child(2),
  .pagination-btn:nth-child(3),
  .pagination-btn:nth-last-child(2) {
    min-width: 60px;
    height: 32px;
    padding: 0 12px;
    border-radius: 4px;
    border: 1px solid #e4e7ed;
    background: #dee7ff;
    color: #606266;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.3s ease;
    &:hover { background: #d7dce6; }
    &:disabled { opacity: 0.6; cursor: not-allowed; }
  }

  .pagination-btn:not(:first-child):not(:nth-child(2)):not(:nth-child(3)):not(:nth-last-child(2)) {
    min-width: 28px;
    height: 32px;
    padding: 0;
    border-radius: 4px;
    border: 1px solid transparent;
    background: transparent;
    color: #606266;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.3s ease;
    &:hover { background: rgba(245, 247, 250, 0.3); }
  }

  .pagination-btn.active {
    background: #5f70f3 !important;
    color: #ffffff !important;
    border-color: #5f70f3 !important;
    &:hover { background: #6d7cf5 !important; }
  }

  .total-text { color: #909399; font-size: 14px; margin-left: 10px; }
}

::v-deep .page-size-select { width: 100px; margin-right: 8px; }
::v-deep .page-size-select .el-input__inner {
  height: 32px;
  line-height: 32px;
  border-radius: 4px;
  border: 1px solid #e4e7ed;
  background: #dee7ff;
  color: #606266;
  font-size: 14px;
}

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
</style>
