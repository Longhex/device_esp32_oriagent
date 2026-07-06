<template>
  <StudioLayout active="models" contextLabel="Agent Builder">
    <div class="studio-model-wrap">
      <!-- Panel trái: menu nhóm model (restyle của nav/activeTab cũ) -->
      <div class="studio-cat-panel">
        <div
          v-for="cat in catList"
          :key="cat.key"
          class="studio-cat-item"
          :class="{ active: activeTab === cat.key }"
          @click="$router.push({ query: { tab: cat.key } })"
        >
          <i :class="cat.icon"></i>
          <span>{{ $t(cat.labelKey) }}</span>
          <i v-if="activeTab === cat.key" class="el-icon-right studio-cat-arrow"></i>
        </div>
      </div>

      <!-- Panel phải: danh sách model -->
      <div class="studio-model-panel">
        <div class="studio-model-toolbar">
          <h2 class="studio-model-title">{{ $t("modelConfig." + activeTab) }}</h2>
          <div class="studio-search-group">
            <el-input
              :placeholder="$t('modelConfig.searchPlaceholder')"
              v-model="search"
              class="search-input"
              clearable
              @keyup.enter.native="handleSearch"
            />
            <el-button class="btn-search" @click="handleSearch">
              {{ $t("modelConfig.search") }}
            </el-button>
          </div>
        </div>

        <el-card class="model-card" shadow="never">
          <el-table
            ref="modelTable"
            style="width: 100%"
            v-loading="loading"
            :element-loading-text="$t('modelConfig.loading')"
            element-loading-spinner="el-icon-loading"
            element-loading-background="rgba(255, 255, 255, 0.7)"
            :header-cell-style="{ background: 'transparent' }"
            :data="displayModelList"
            :span-method="providerSpanMethod"
            :row-class-name="modelRowClassName"
            class="transparent-table"
            header-row-class-name="table-header"
            :header-cell-class-name="headerCellClassName"
            @selection-change="handleSelectionChange"
          >
            <el-table-column
              type="selection"
              width="55"
              align="center"
              :selectable="isModelRowSelectable"
              :cell-class-name="selectionCellClassName"
            ></el-table-column>
            <el-table-column
              :label="$t('modelConfig.modelId')"
              prop="id"
              align="center"
            >
              <template slot-scope="scope">
                <div v-if="scope.row.__groupHeader" class="provider-group-header">
                  <i class="el-icon-cpu provider-group-icon"></i>
                  <span class="provider-group-name">{{ scope.row.__provider }}</span>
                </div>
                <span v-else>{{ scope.row.id }}</span>
              </template>
            </el-table-column>
            <el-table-column
              :label="$t('modelConfig.modelName')"
              prop="modelName"
              align="center"
            >
              <template slot-scope="scope">
                <span class="model-name-cell">
                  <i class="el-icon-cpu model-name-icon"></i>{{ scope.row.modelName }}
                </span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('modelConfig.provider')" align="center">
              <template slot-scope="scope">
                <span v-if="!scope.row.__groupHeader" class="provider-tag">{{
                  (scope.row.configJson && scope.row.configJson.type) || $t("modelConfig.unknown")
                }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('modelConfig.isEnabled')" align="center">
              <template slot-scope="scope">
                <el-tooltip
                  v-if="scope.row.isDefault === 1 && scope.row.isEnabled === 1"
                  :content="$t('modelConfig.defaultModelCannotDisable')"
                  placement="top"
                  effect="light"
                >
                  <el-switch
                    v-model="scope.row.isEnabled"
                    class="custom-switch"
                    active-color="#08c45b"
                    :active-value="1"
                    :inactive-value="0"
                    disabled
                    @change="handleStatusChange(scope.row)"
                  />
                </el-tooltip>
                <el-switch
                  v-else
                  v-model="scope.row.isEnabled"
                  class="custom-switch"
                  active-color="#08c45b"
                  :active-value="1"
                  :inactive-value="0"
                  @change="handleStatusChange(scope.row)"
                />
              </template>
            </el-table-column>
            <el-table-column :label="$t('modelConfig.isDefault')" align="center">
              <template slot-scope="scope">
                <el-switch
                  v-model="scope.row.isDefault"
                  class="custom-switch"
                  active-color="#08c45b"
                  :active-value="1"
                  :inactive-value="0"
                  @change="handleDefaultChange(scope.row)"
                />
              </template>
            </el-table-column>
            <el-table-column
              v-if="activeTab === 'tts'"
              :label="$t('modelConfig.voiceManagement')"
              align="center"
            >
              <template slot-scope="scope">
                <el-button
                  type="text"
                  size="mini"
                  @click="openTtsDialog(scope.row)"
                  class="voice-management-btn"
                >
                  {{ $t("modelConfig.voiceManagement") }}
                </el-button>
              </template>
            </el-table-column>
            <el-table-column
              :label="$t('modelConfig.action')"
              align="center"
              width="140px"
            >
              <template slot-scope="scope">
                <el-tooltip :content="$t('modelConfig.edit')" placement="top" effect="light">
                  <el-button
                    type="text"
                    circle
                    size="mini"
                    icon="el-icon-edit"
                    @click="editModel(scope.row)"
                    class="action-icon-btn"
                  ></el-button>
                </el-tooltip>
                <el-tooltip :content="$t('modelConfig.duplicate')" placement="top" effect="light">
                  <el-button
                    type="text"
                    circle
                    size="mini"
                    icon="el-icon-copy-document"
                    @click="duplicateModel(scope.row)"
                    class="action-icon-btn"
                  ></el-button>
                </el-tooltip>
                <el-tooltip :content="$t('modelConfig.delete')" placement="top" effect="light">
                  <el-button
                    type="text"
                    circle
                    size="mini"
                    icon="el-icon-delete"
                    @click="deleteModel(scope.row)"
                    class="action-icon-btn action-icon-btn--danger"
                  ></el-button>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table>
          <div class="table-footer">
            <div class="batch-actions">
              <el-button size="mini" type="primary" @click="selectAll">
                {{
                  isAllSelected
                    ? $t("modelConfig.deselectAll")
                    : $t("modelConfig.selectAll")
                }}
              </el-button>
              <el-button type="success" size="mini" @click="addModel" class="add-btn">
                {{ $t("modelConfig.add") }}
              </el-button>
              <el-button
                size="mini"
                type="danger"
                icon="el-icon-delete"
                @click="batchDelete"
              >
                {{ $t("modelConfig.delete") }}
              </el-button>
            </div>
            <div class="custom-pagination">
              <el-select
                v-model="pageSize"
                @change="handlePageSizeChange"
                class="page-size-select"
              >
                <el-option
                  v-for="item in pageSizeOptions"
                  :key="item"
                  :label="$t('modelConfig.itemsPerPage', { items: item })"
                  :value="item"
                >
                </el-option>
              </el-select>

              <button
                class="pagination-btn"
                :disabled="currentPage === 1"
                @click="goFirst"
              >
                {{ $t("modelConfig.firstPage") }}
              </button>
              <button
                class="pagination-btn"
                :disabled="currentPage === 1"
                @click="goPrev"
              >
                {{ $t("modelConfig.prevPage") }}
              </button>

              <button
                v-for="page in visiblePages"
                :key="page"
                class="pagination-btn"
                :class="{ active: page === currentPage }"
                @click="goToPage(page)"
              >
                {{ page }}
              </button>

              <button
                class="pagination-btn"
                :disabled="currentPage === pageCount"
                @click="goNext"
              >
                {{ $t("modelConfig.nextPage") }}
              </button>
              <span class="total-text">{{
                $t("modelConfig.totalRecords", { total })
              }}</span>
            </div>
          </div>
        </el-card>
      </div>
    </div>

    <ModelEditDialog
      :modelType="activeTab"
      :visible.sync="editDialogVisible"
      :modelData="editModelData"
      @save="handleModelSave"
    />
    <TtsModel
      :visible.sync="ttsDialogVisible"
      :ttsModelId="selectedTtsModelId"
      :modelConfig="selectedModelConfig"
    />
    <AddModelDialog
      :modelType="activeTab"
      :visible.sync="addDialogVisible"
      @confirm="handleAddConfirm"
    />

    <el-footer>
      <version-footer />
    </el-footer>
  </StudioLayout>
</template>

<script>
import Api from "@/apis/api";
import AddModelDialog from "@/components/AddModelDialog.vue";
import ModelEditDialog from "@/components/ModelEditDialog.vue";
import StudioLayout from "@/components/StudioLayout.vue";
import TtsModel from "@/components/TtsModel.vue";
import VersionFooter from "@/components/VersionFooter.vue";
export default {
  components: { ModelEditDialog, TtsModel, AddModelDialog, VersionFooter, StudioLayout },
  data() {
    return {
      // Menu nhóm model (panel trái) - bê nguyên danh sách model-type từ SideBar.vue
      catList: [
        { key: "vad", icon: "el-icon-microphone", labelKey: "modelConfig.vad" },
        { key: "asr", icon: "el-icon-chat-dot-round", labelKey: "modelConfig.asr" },
        { key: "llm", icon: "el-icon-cpu", labelKey: "modelConfig.llm" },
        { key: "vllm", icon: "el-icon-picture-outline", labelKey: "modelConfig.vllm" },
        { key: "intent", icon: "el-icon-aim", labelKey: "modelConfig.intent" },
        { key: "tts", icon: "el-icon-headset", labelKey: "modelConfig.tts" },
        { key: "memory", icon: "el-icon-collection", labelKey: "modelConfig.memory" },
        { key: "rag", icon: "el-icon-notebook-2", labelKey: "modelConfig.rag" },
      ],
      addDialogVisible: false,
      activeTab: "llm",
      search: "",
      editDialogVisible: false,
      editModelData: {},
      ttsDialogVisible: false,
      selectedTtsModelId: "",
      modelList: [],
      pageSizeOptions: [10, 20, 50, 100],
      currentPage: 1,
      pageSize: 10,
      total: 0,
      selectedModels: [],
      isAllSelected: false,
      loading: false,
      selectedModelConfig: {},
    };
  },

  created() {
    if (this.$route.query.tab) {
      this.activeTab = this.$route.query.tab;
    }
    this.loadData();
  },

  watch: {
    "$route.query.tab"(newTab) {
      if (newTab) {
        this.activeTab = newTab;
        this.currentPage = 1;
        this.loadData();
      }
    },
  },

  mounted() {
    // 在组件挂载后确保表头翻译文本正确显示
    setTimeout(() => {
      this.updateSelectionHeaderText();
    }, 100);
  },

  updated() {
    // 在组件更新后重新设置表头翻译文本
    this.updateSelectionHeaderText();
  },

  computed: {
    // Gộp modelList thành các khối theo nhà cung cấp (configJson.type):
    // chèn 1 hàng header (__groupHeader) trước mỗi nhóm. Chỉ đổi HIỂN THỊ,
    // không đụng modelList gốc nên chọn-nhiều/phân trang/CRUD giữ nguyên.
    displayModelList() {
      const groups = [];
      const idxByProvider = {};
      for (const m of this.modelList) {
        const p =
          (m.configJson && m.configJson.type) || this.$t("modelConfig.unknown");
        if (!(p in idxByProvider)) {
          idxByProvider[p] = groups.length;
          groups.push({ provider: p, items: [] });
        }
        groups[idxByProvider[p]].items.push(m);
      }
      const rows = [];
      for (const g of groups) {
        rows.push({ __groupHeader: true, __provider: g.provider });
        for (const m of g.items) rows.push(m);
      }
      return rows;
    },
    modelTypeText() {
      return (
        this.$t("modelConfig." + this.activeTab) || this.$t("modelConfig.modelConfig")
      );
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
  },

  methods: {
    // Hàng header nhóm provider không cho chọn (checkbox ẩn)
    isModelRowSelectable(row) {
      return !row.__groupHeader;
    },
    modelRowClassName({ row }) {
      return row && row.__groupHeader ? "provider-group-row" : "";
    },
    // Hàng header nhóm: gộp 1 ô trải hết bảng; hàng model: bình thường
    providerSpanMethod({ row, columnIndex }) {
      if (row && row.__groupHeader) {
        const colCount = this.activeTab === "tts" ? 8 : 7;
        if (columnIndex === 0) return [0, 0];
        if (columnIndex === 1) return [1, colCount];
        return [0, 0];
      }
      return [1, 1];
    },
    // 更新选择列表头翻译文本
    updateSelectionHeaderText() {
      const thElement = document.querySelector(`.el-table__header th:nth-child(1) .cell`);
      if (thElement) {
        thElement.setAttribute("data-content", this.$t("modelConfig.select"));
      }
    },
    handlePageSizeChange(val) {
      this.pageSize = val;
      this.currentPage = 1;
      this.loadData();
    },
    openTtsDialog(row) {
      this.selectedTtsModelId = row.id;
      this.selectedModelConfig = row;
      this.ttsDialogVisible = true;
    },
    headerCellClassName({ column, columnIndex }) {
      if (columnIndex === 0) {
        return "custom-selection-header";
      }
      return "";
    },
    selectionCellClassName({ row, column, rowIndex, columnIndex }) {
      // 只对表头行设置data-content
      if (rowIndex === undefined) {
        // 使用setTimeout确保DOM已经渲染完成
        setTimeout(() => {
          const thElement = document.querySelector(
            `.el-table__header th:nth-child(1) .cell`
          );
          if (thElement) {
            thElement.setAttribute("data-content", this.$t("modelConfig.select"));
          }
        }, 0);
      }
      return "";
    },
    handleSearch() {
      this.currentPage = 1;
      this.loadData();
    },
    // 批量删除
    batchDelete() {
      if (this.selectedModels.length === 0) {
        this.$message.warning(this.$t("modelConfig.selectModelsFirst"));
        return;
      }

      this.$confirm(this.$t("modelConfig.confirmBatchDelete"), this.$t("message.info"), {
        confirmButtonText: this.$t("common.confirm"),
        cancelButtonText: this.$t("common.cancel"),
        type: "warning",
      })
        .then(() => {
          const deletePromises = this.selectedModels.map(
            (model) =>
              new Promise((resolve) => {
                Api.model.deleteModel(model.id, ({ data }) => resolve(data.code === 0));
              })
          );

          Promise.all(deletePromises).then((results) => {
            if (results.every(Boolean)) {
              this.$message.success({
                message: this.$t("modelConfig.batchDeleteSuccess"),
                showClose: true,
              });
              this.loadData();
            } else {
              this.$message.error({
                message: this.$t("modelConfig.partialDeleteFailed"),
                showClose: true,
              });
            }
          });
        })
        .catch(() => {
          this.$message.info(this.$t("modelConfig.deleteCancelled"));
        });
    },
    addModel() {
      this.addDialogVisible = true;
    },
    editModel(model) {
      this.editModelData = JSON.parse(JSON.stringify(model));
      this.editDialogVisible = true;
    },
    duplicateModel(model) {
      this.editModelData = JSON.parse(JSON.stringify(model));
      this.editModelData.duplicateMode = true;
      this.editDialogVisible = true;
    },
    // 删除单个模型
    deleteModel(model) {
      this.$confirm(this.$t("modelConfig.confirmDelete"), this.$t("message.info"), {
        confirmButtonText: this.$t("common.confirm"),
        cancelButtonText: this.$t("common.cancel"),
        type: "warning",
      })
        .then(() => {
          Api.model.deleteModel(model.id, ({ data }) => {
            if (data.code === 0) {
              this.$message.success({
                message: this.$t("modelConfig.deleteSuccess"),
                showClose: true,
              });
              this.loadData();
            } else {
              this.$message.error({
                message: data.msg || this.$t("modelConfig.deleteFailed"),
                showClose: true,
              });
            }
          });
        })
        .catch(() => {
          this.$message.info(this.$t("modelConfig.deleteCancelled"));
        });
    },
    handleCurrentChange(page) {
      this.currentPage = page;
      this.$refs.modelTable.clearSelection();
    },
    handleModelSave({ provideCode, formData, done }) {
      const modelType = this.activeTab;
      const id = formData.id;

      if (this.editModelData.duplicateMode) {
        formData.id = "";
        Api.model.addModel({ modelType, provideCode, formData }, ({ data }) => {
          if (data.code === 0) {
            this.$message.success(this.$t("modelConfig.duplicateSuccess"));
            this.loadData();
            this.editDialogVisible = false;
          } else {
            this.$message.error(data.msg || this.$t("modelConfig.duplicateFailed"));
          }
          done && done(); // 调用done回调关闭加载状态
        });
      } else {
        Api.model.updateModel({ modelType, provideCode, id, formData }, ({ data }) => {
          if (data.code === 0) {
            this.$message.success(this.$t("modelConfig.saveSuccess"));
            this.loadData();
            this.editDialogVisible = false;
          } else {
            this.$message.error(data.msg || this.$t("modelConfig.saveFailed"));
          }
          done && done(); // 调用done回调关闭加载状态
        });
      }
    },
    selectAll() {
      if (this.isAllSelected) {
        this.$refs.modelTable.clearSelection();
      } else {
        this.$refs.modelTable.toggleAllSelection();
      }
    },
    handleSelectionChange(val) {
      this.selectedModels = val;
      this.isAllSelected = val.length === this.modelList.length;
      if (val.length === 0) {
        this.isAllSelected = false;
      }
    },

    // 新增模型配置
    handleAddConfirm(newModel) {
      const params = {
        modelType: this.activeTab,
        provideCode: newModel.provideCode,
        formData: {
          ...newModel,
          isDefault: newModel.isDefault ? 1 : 0,
          isEnabled: newModel.isEnabled ? 1 : 0,
          configJson: newModel.configJson,
        },
      };

      Api.model.addModel(params, ({ data }) => {
        if (data.code === 0) {
          this.$message.success({
            message: this.$t("modelConfig.addSuccess"),
            showClose: true,
          });
          this.loadData();
        } else {
          this.$message.error({
            message: data.msg || this.$t("modelConfig.addFailed"),
            showClose: true,
          });
        }
      });
    },

    // 分页器
    goFirst() {
      this.currentPage = 1;
      this.loadData();
    },
    goPrev() {
      if (this.currentPage > 1) {
        this.currentPage--;
        this.loadData();
      }
    },
    goNext() {
      if (this.currentPage < this.pageCount) {
        this.currentPage++;
        this.loadData();
      }
    },
    goToPage(page) {
      this.currentPage = page;
      this.loadData();
    },

    // 获取模型配置列表
    loadData() {
      this.loading = true; // 开始加载
      const params = {
        modelType: this.activeTab,
        modelName: this.search,
        page: this.currentPage,
        limit: this.pageSize,
      };

      Api.model.getModelList(params, ({ data }) => {
        this.loading = false; // 结束加载
        if (data.code === 0) {
          this.modelList = data.data.list;
          this.total = data.data.total;
        } else {
          this.$message.error(data.msg || this.$t("modelConfig.fetchModelsFailed"));
        }
      });
    },
    // 处理启用/禁用状态变更
    handleStatusChange(model) {
      const newStatus = model.isEnabled ? 1 : 0;
      const originalStatus = model.isEnabled;

      model.isEnabled = !model.isEnabled;

      Api.model.updateModelStatus(model.id, newStatus, ({ data }) => {
        if (data.code === 0) {
          this.$message.success(
            newStatus === 1
              ? this.$t("modelConfig.enableSuccess")
              : this.$t("modelConfig.disableSuccess")
          );
          // 保持新状态
          model.isEnabled = newStatus;
          // 刷新表格数据
          this.loadData();
        } else {
          // 操作失败时恢复原状态
          model.isEnabled = originalStatus;
          this.$message.error(data.msg || this.$t("modelConfig.operationFailed"));
        }
      });
    },
    handleDefaultChange(model) {
      Api.model.setDefaultModel(model.id, ({ data }) => {
        if (data.code === 0) {
          this.$message.success(this.$t("modelConfig.setDefaultSuccess"));
          this.loadData();
        }
      });
    },
  },
};
</script>

<style lang="scss" scoped>
@import "./studio.scss";

.el-switch {
  height: 23px;
}

::v-deep .el-table tr {
  background: transparent;
}

/* ---------- Layout 2 panel (menu trái + danh sách model) ---------- */
.studio-model-wrap {
  display: flex;
  gap: $studio-gap;
  align-items: flex-start;
  flex: 1;
  min-height: 0;
}

.studio-cat-panel {
  @include studio-panel;
  width: 260px;
  flex-shrink: 0;
  padding: 14px 10px;
  box-sizing: border-box;
}

.studio-cat-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 14px;
  color: $studio-text;
  cursor: pointer;
  transition: background 0.2s ease;

  i {
    font-size: 15px;
  }

  span {
    flex: 1;
    text-align: left;
  }

  .studio-cat-arrow {
    flex: none;
    font-size: 14px;
  }

  &:hover:not(.active) {
    background: $studio-soft-bg;
  }

  &.active {
    background: $studio-accent-soft;
    color: #069d49;
    font-weight: 600;
  }

  & + .studio-cat-item {
    margin-top: 4px;
  }
}

.studio-model-panel {
  @include studio-panel;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 18px 20px;
  box-sizing: border-box;
  height: 100%;
}

.studio-model-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-shrink: 0;
  margin-bottom: 12px;
}

.studio-model-title {
  @include studio-title;
  margin: 0;
  white-space: nowrap;
}

.studio-search-group {
  display: flex;
  gap: 8px;
  align-items: center;
}

.search-input {
  width: 220px;
}

.btn-search {
  background: linear-gradient(135deg, #555555, #a966ff);
  border: none;
  color: white;
  border-radius: $studio-radius-pill;
}

.btn-search:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

::v-deep .search-input .el-input__inner {
  border-radius: $studio-radius-pill;
  border: 1px solid $studio-border;
  background-color: $studio-soft-bg;
  transition: border-color 0.2s;
}

::v-deep .page-size-select {
  width: 100px;
  margin-right: 8px;
}

::v-deep .page-size-select .el-input__inner {
  height: 32px;
  line-height: 32px;
  border-radius: 4px;
  border: 1px solid #e4e7ed;
  background: #dee7ff;
  color: #606266;
  font-size: 14px;
}

::v-deep .page-size-select .el-input__suffix {
  right: 6px;
  width: 15px;
  height: 20px;
  display: flex;
  justify-content: center;
  align-items: center;
  top: 6px;
  border-radius: 4px;
}

::v-deep .page-size-select .el-input__suffix-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
}

::v-deep .page-size-select .el-icon-arrow-up:before {
  content: "";
  display: inline-block;
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-top: 9px solid #606266;
  position: relative;
  transform: rotate(0deg);
  transition: transform 0.3s;
}

::v-deep .search-input .el-input__inner:focus {
  border-color: #555555;
  outline: none;
}

.table-header th {
  background-color: transparent !important;
  color: #606266;
  font-weight: 600;
}

.table-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  flex-shrink: 0;
  min-height: 60px;
  background: white;
}

.batch-actions {
  display: flex;
  gap: 8px;
}

.batch-actions .el-button {
  min-width: 72px;
  height: 32px;
  padding: 7px 12px 7px 10px;
  font-size: 12px;
  border-radius: $studio-radius-pill;
  line-height: 1;
  font-weight: 500;
  border: none;
  transition: all 0.3s ease;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
}

.batch-actions .el-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}

.batch-actions .el-button--primary {
  background: #5f70f3 !important;
  color: white;
}

/* Nút "Thêm mới model" - pill accent xanh giống mẫu */
.batch-actions .add-btn {
  background: $studio-accent !important;
  color: white;
}

.batch-actions .el-button--danger {
  background: #fd5b63;
  color: white;
}

.el-table th ::v-deep .el-table__cell {
  overflow: hidden;
  -webkit-user-select: none;
  -moz-user-select: none;
  user-select: none;
  background-color: transparent !important;
}

::v-deep .el-table .custom-selection-header .cell .el-checkbox__inner {
  display: none !important;
}

::v-deep .el-table .custom-selection-header .cell::before {
  content: attr(data-content);
  display: block;
  text-align: center;
  line-height: 32px;
  /* 设置合适的行高，确保文本完整显示 */
  color: black;
  margin-top: 0;
  /* 移除可能导致偏移的上边距 */
  height: 32px;
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 100%;
}

.custom-selection-header .cell {
  position: relative;
}

::v-deep .el-table__body .el-checkbox__inner {
  display: inline-block !important;
  background: #e6edfa;
}

::v-deep .el-table thead th:not(:first-child) .cell {
  color: #303133 !important;
}

::v-deep .nav-panel .el-menu-item.is-active .menu-text {
  color: #fff !important;
}

.el-button img {
  height: 1em;
  vertical-align: middle;
  padding-right: 2px;
  padding-bottom: 2px;
}

::v-deep .el-checkbox__inner {
  border-color: #cfcfcf !important;
  transition: all 0.2s ease-in-out;
}

::v-deep .el-checkbox__input.is-checked .el-checkbox__inner {
  background-color: #5f70f3;
  border-color: #5f70f3;
}

.voice-management-btn {
  background: #9db3ea;
  color: white;
  min-width: 68px;
  line-height: 14px;
  white-space: nowrap;
  transition: all 0.3s;
  border-radius: 10px;
}

.voice-management-btn:hover {
  background: #8aa2e0;
  /* 悬停时颜色加深 */
  transform: scale(1.05);
}

::v-deep .el-table .el-table-column--selection .cell {
  padding-left: 15px !important;
}

::v-deep .el-table .el-table__fixed-right .cell {
  padding-right: 15px !important;
}

/* Cụm action icon tròn (sửa/nhân bản/xóa) */
.action-icon-btn {
  margin: 0 3px;
  padding: 0;
  width: 28px;
  height: 28px;
  color: $studio-text-sub !important;
  border: 1px solid $studio-border !important;
  background: $studio-soft-bg !important;

  &:hover {
    color: $studio-text !important;
    background: darken(#f7f7f7, 4%) !important;
  }

  &.action-icon-btn--danger:hover {
    color: #fd5b63 !important;
    border-color: #fd5b63 !important;
  }
}

/* Cột tên model kèm icon */
.model-name-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.model-name-icon {
  color: $studio-text-sub;
}

/* Tag loại provider */
.provider-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: $studio-radius-pill;
  background: $studio-soft-bg;
  color: $studio-text-sub;
  font-size: 12px;
}

/* Hàng header nhóm theo nhà cung cấp (như mẫu: khối "OpenAI" ...) */
.provider-group-header {
  display: flex;
  align-items: center;
  gap: 10px;
  text-align: left;
  padding: 4px 2px;
}
.provider-group-icon {
  font-size: 18px;
  color: $studio-text;
}
.provider-group-name {
  font-size: 15px;
  font-weight: 700;
  color: $studio-text;
}
::v-deep .transparent-table .provider-group-row > td {
  background: $studio-soft-bg;
}
::v-deep .transparent-table .provider-group-row:hover > td {
  background: $studio-soft-bg; /* không đổi màu khi hover header */
}

::v-deep .el-table .cell {
  padding-left: 10px;
  padding-right: 10px;
}

/* 分页器 */
.custom-pagination {
  display: flex;
  align-items: center;
  gap: 8px;

  /* 导航按钮样式 (首页、上一页、下一页) */
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

    &:hover {
      background: #d7dce6;
    }

    &:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
  }

  /* 数字按钮样式 */
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

    &:hover {
      background: rgba(245, 247, 250, 0.3);
    }
  }

  .pagination-btn.active {
    background: #5f70f3 !important;
    color: #ffffff !important;
    border-color: #5f70f3 !important;

    &:hover {
      background: #6d7cf5 !important;
    }
  }

  .total-text {
    color: #909399;
    font-size: 14px;
    margin-left: 10px;
  }
}

.model-card {
  background: white;
  flex: 1;
  display: flex;
  flex-direction: column;
  border: none;
  box-shadow: none;
  overflow: hidden;
  min-height: 0;
}

.model-card ::v-deep .el-card__body {
  padding: 0;
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

:deep(.transparent-table) {
    background: white;
    flex: 1;
    width: 100%;
    display: flex;
    flex-direction: column;

    .el-table__body-wrapper {
        flex: 1;
        overflow-y: auto;
        max-height: none !important;
    }

    .el-table__header-wrapper {
        flex-shrink: 0;
    }

    /* Bỏ kẻ ô, header nền phụ chữ chính theo token studio */
    td, th {
        border: none !important;
    }

    .el-table__header th {
        background: $studio-soft-bg !important;
        color: $studio-text;
        font-weight: 600;
        height: 44px;
        padding: 8px 0;
        font-size: 14px;
        border-bottom: none;
    }

    /* Hàng cao thoáng, bo góc nhẹ */
    .el-table__body tr {
        background-color: white;

        td {
            border: none;
            padding: 14px 0;
            height: 52px;
            color: #606266;
            font-size: 14px;
        }
    }

    .el-table__row:hover>td {
        background-color: $studio-soft-bg !important;
    }

    &::before {
        display: none;
    }
}


::v-deep .el-loading-mask {
  background-color: rgba(255, 255, 255, 0.6) !important;
  backdrop-filter: blur(2px);
}

::v-deep .el-loading-spinner .circular {
  width: 28px;
  height: 28px;
}

::v-deep .el-loading-spinner .path {
  stroke: #555555;
}

::v-deep .el-loading-text {
  color: #555555 !important;
  font-size: 14px;
  margin-top: 8px;
}
</style>
