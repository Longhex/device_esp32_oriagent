<template>
  <SettingsLayout active-key="emoji">
    <div class="welcome settings-panel">
    <div class="operation-bar">
      <h2 class="page-title">{{ $t('emojiManagement.title') }}</h2>
      <div class="right-operations">
        <el-input :placeholder="$t('emojiManagement.searchPlaceholder')" v-model="searchName" class="search-input"
          @keyup.enter.native="handleSearch" clearable />
        <el-button class="btn-search" @click="handleSearch">{{ $t('otaManagement.search') }}</el-button>
        <el-button class="btn-api" @click="copyApiUrl">{{ $t('emojiManagement.copyApiUrl') }}</el-button>
        <el-button class="btn-api" @click="openAssetsApi">{{ $t('emojiManagement.viewApi') }}</el-button>
      </div>
    </div>

    <div class="main-wrapper">
      <div class="content-panel">
        <div class="content-area">
          <el-card class="params-card" shadow="never">
            <el-table ref="emojiTable" :data="list" class="transparent-table" v-loading="loading"
              element-loading-text="Loading" element-loading-spinner="el-icon-loading"
              element-loading-background="rgba(255, 255, 255, 0.7)"
              :empty-text="$t('emojiManagement.empty')">
              <el-table-column :label="$t('emojiManagement.typeColumn')" align="center" width="120">
                <template slot-scope="scope">
                  <el-tag size="small">{{ stripPrefix(scope.row.type) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column :label="$t('emojiManagement.name')" prop="firmwareName" align="center"></el-table-column>
              <el-table-column :label="$t('emojiManagement.version')" prop="version" align="center"></el-table-column>
              <el-table-column :label="$t('emojiManagement.fileSize')" prop="size" align="center">
                <template slot-scope="scope">{{ formatFileSize(scope.row.size) }}</template>
              </el-table-column>
              <el-table-column :label="$t('emojiManagement.linkLabel')" align="center" min-width="220">
                <template slot-scope="scope">
                  <span class="link-text" :title="buildStableUrl(scope.row.id)">{{ buildStableUrl(scope.row.id) }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="$t('emojiManagement.remark')" prop="remark" align="center"
                show-overflow-tooltip></el-table-column>
              <el-table-column :label="$t('emojiManagement.updateTime')" prop="updateDate" align="center">
                <template slot-scope="scope">{{ formatDate(scope.row.updateDate) }}</template>
              </el-table-column>
              <el-table-column :label="$t('emojiManagement.action')" align="center" min-width="240">
                <template slot-scope="scope">
                  <el-button size="mini" type="text" @click="copyLink(scope.row)">{{ $t('emojiManagement.copyLink') }}</el-button>
                  <el-button size="mini" type="text" @click="downloadFile(scope.row)">{{ $t('emojiManagement.download') }}</el-button>
                  <el-button size="mini" type="text" @click="editRow(scope.row)">{{ $t('emojiManagement.edit') }}</el-button>
                  <el-button size="mini" type="text" @click="deleteRow(scope.row)">{{ $t('emojiManagement.delete') }}</el-button>
                </template>
              </el-table-column>
            </el-table>

            <div class="table_bottom">
              <div class="ctrl_btn">
                <el-button size="mini" type="success" @click="showAddDialog"
                  style="background: #5bc98c;border: None;">{{ $t('emojiManagement.addNew') }}</el-button>
              </div>
            </div>
          </el-card>
        </div>
      </div>
    </div>

    <!-- 上传/替换 资源文件对话框 -->
    <el-dialog :title="dialogTitle" :visible.sync="dialogVisible" :close-on-click-modal="false" @open="handleDialogOpen">
      <el-form ref="form" :model="form" :rules="rules" label-width="auto">
        <el-form-item :label="$t('emojiManagement.resourceType')" prop="typeKey">
          <el-input v-model="form.typeKey" :disabled="!!form.id"
            :placeholder="$t('emojiManagement.resourceTypePlaceholder')"></el-input>
          <div class="hint-text">{{ $t('emojiManagement.resourceTypeHint') }}</div>
        </el-form-item>
        <el-form-item :label="$t('emojiManagement.name')" prop="firmwareName">
          <el-input v-model="form.firmwareName" :placeholder="$t('emojiManagement.requiredName')"></el-input>
        </el-form-item>
        <el-form-item :label="$t('emojiManagement.version')" prop="version">
          <el-input v-model="form.version" placeholder="1.0.0"></el-input>
        </el-form-item>
        <el-form-item :label="$t('emojiManagement.dialogTitle')" prop="firmwarePath">
          <el-upload ref="upload" class="upload-demo" action="#" :http-request="handleUpload"
            :before-upload="beforeUpload" :accept="'.tar,.gz,.zip'" :limit="1" :multiple="false" :auto-upload="true"
            :on-remove="handleRemove">
            <el-button size="small" type="primary">{{ $t('firmwareDialog.clickUpload') }}</el-button>
            <div slot="tip" class="el-upload__tip">{{ $t('emojiManagement.fileTip') }}</div>
          </el-upload>
          <el-progress v-if="isUploading || uploadStatus === 'success'" :percentage="uploadProgress"
            :status="uploadStatus"></el-progress>
        </el-form-item>
        <el-form-item :label="$t('emojiManagement.remark')" prop="remark">
          <el-input type="textarea" v-model="form.remark"></el-input>
        </el-form-item>
      </el-form>
      <div slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible = false">{{ $t('button.cancel') }}</el-button>
        <el-button type="primary" @click="handleSubmit">{{ $t('button.save') }}</el-button>
      </div>
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
import { formatDate, formatFileSize } from "@/utils/format";

// Tài nguyên dùng chung bảng ai_ota, phân biệt với firmware bằng tiền tố type này.
// Mỗi loại tài nguyên (emoj/logo/music/video...) = 1 type = asset-<key> = 1 link cố định riêng.
const ASSET_PREFIX = "asset-";

export default {
  components: { VersionFooter },
  data() {
    return {
      searchName: "",
      loading: false,
      list: [],
      dialogVisible: false,
      dialogTitle: "",
      uploadProgress: 0,
      uploadStatus: "",
      isUploading: false,
      form: {
        id: null,
        typeKey: "",
        firmwareName: "",
        version: "1.0.0",
        size: 0,
        remark: "",
        firmwarePath: ""
      },
      rules: {
        typeKey: [
          { required: true, message: this.$t('emojiManagement.requiredType'), trigger: 'blur' },
          { pattern: /^[a-z0-9-]+$/, message: this.$t('emojiManagement.invalidType'), trigger: 'blur' }
        ],
        firmwareName: [
          { required: true, message: this.$t('emojiManagement.requiredName'), trigger: 'blur' }
        ],
        version: [
          { required: true, message: this.$t('firmwareDialog.requiredVersion'), trigger: 'blur' },
          { pattern: /^\d+\.\d+\.\d+$/, message: this.$t('firmwareDialog.versionFormatError'), trigger: 'blur' }
        ]
      }
    };
  },
  created() {
    this.fetchList();
  },
  methods: {
    formatDate,
    formatFileSize,
    stripPrefix(type) {
      if (!type) return "";
      return type.startsWith(ASSET_PREFIX) ? type.slice(ASSET_PREFIX.length) : type;
    },
    buildStableUrl(id) {
      const baseUrl = process.env.VUE_APP_API_BASE_URL || '';
      return `${window.location.origin}${baseUrl}/otaMag/file/${id}`;
    },
    assetsApiUrl() {
      const baseUrl = process.env.VUE_APP_API_BASE_URL || '';
      return `${window.location.origin}${baseUrl}/otaMag/assets`;
    },
    openAssetsApi() {
      window.open(this.assetsApiUrl());
    },
    async copyApiUrl() {
      const url = this.assetsApiUrl();
      try {
        await navigator.clipboard.writeText(url);
        this.$message.success(this.$t('emojiManagement.copied'));
      } catch (e) {
        try {
          const ta = document.createElement('textarea');
          ta.value = url;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          this.$message.success(this.$t('emojiManagement.copied'));
        } catch (e2) {
          this.$message.warning(this.$t('emojiManagement.copyFailed') + ': ' + url);
        }
      }
    },
    fetchList() {
      this.loading = true;
      const params = {
        page: 1,
        limit: 100,
        typePrefix: ASSET_PREFIX,
        firmwareName: this.searchName || "",
        orderField: "update_date",
        order: "desc"
      };
      Api.ota.getOtaList(params, (res) => {
        this.loading = false;
        res = res.data;
        if (res.code === 0) {
          this.list = res.data.list || [];
        } else {
          this.list = [];
          this.$message.error({ message: res?.msg || this.$t('otaManagement.getFirmwareListFailed'), showClose: true });
        }
      });
    },
    handleSearch() {
      this.fetchList();
    },
    showAddDialog() {
      this.dialogTitle = this.$t('emojiManagement.dialogTitle');
      this.form = { id: null, typeKey: "", firmwareName: "", version: "1.0.0", size: 0, remark: "", firmwarePath: "" };
      this.dialogVisible = true;
    },
    editRow(row) {
      this.dialogTitle = this.$t('emojiManagement.dialogEditTitle');
      this.form = { ...row, typeKey: this.stripPrefix(row.type) };
      this.dialogVisible = true;
    },
    handleDialogOpen() {
      this.uploadProgress = 0;
      this.uploadStatus = "";
      this.isUploading = false;
      this.$nextTick(() => {
        if (this.$refs.upload) this.$refs.upload.clearFiles();
        if (this.$refs.form) this.$refs.form.clearValidate();
      });
    },
    beforeUpload(file) {
      const isValidSize = file.size / 1024 / 1024 < 100;
      const isValidType = ['.tar', '.gz', '.zip'].some(ext => file.name.toLowerCase().endsWith(ext));
      if (!isValidType) {
        this.$message.error(this.$t('emojiManagement.invalidFileType'));
        return false;
      }
      if (!isValidSize) {
        this.$message.error(this.$t('emojiManagement.invalidFileSize'));
        return false;
      }
      return true;
    },
    handleUpload(options) {
      const { file } = options;
      this.uploadProgress = 0;
      this.uploadStatus = "";
      this.isUploading = true;
      const timer = setTimeout(() => {
        if (this.uploadProgress < 50) this.uploadProgress = 50;
      }, 1000);
      Api.ota.uploadFirmware(file, (res) => {
        clearTimeout(timer);
        res = res.data;
        if (res.code === 0) {
          this.form.firmwarePath = res.data;
          this.form.size = file.size;
          this.uploadProgress = 100;
          this.uploadStatus = 'success';
          this.$message.success(this.$t('emojiManagement.uploadSuccess'));
          setTimeout(() => { this.isUploading = false; }, 1500);
        } else {
          this.uploadStatus = 'exception';
          this.$message.error(res.msg || this.$t('emojiManagement.uploadFailed'));
          this.isUploading = false;
        }
      }, (progressEvent) => {
        if (progressEvent.total) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          if (progress > 50) this.uploadProgress = progress;
        }
      });
    },
    handleRemove() {
      this.form.firmwarePath = "";
      this.form.size = 0;
      this.uploadProgress = 0;
      this.uploadStatus = "";
      this.isUploading = false;
    },
    handleSubmit() {
      this.$refs.form.validate(valid => {
        if (!valid) return;
        if (!this.form.firmwarePath) {
          this.$message.error(this.$t('emojiManagement.requiredFile'));
          return;
        }
        const payload = {
          id: this.form.id,
          firmwareName: this.form.firmwareName,
          type: ASSET_PREFIX + this.form.typeKey,
          version: this.form.version,
          size: this.form.size,
          remark: this.form.remark,
          firmwarePath: this.form.firmwarePath
        };
        const done = (res) => {
          res = res.data;
          if (res.code === 0) {
            this.$message.success(this.$t('emojiManagement.saveSuccess'));
            this.dialogVisible = false;
            this.fetchList();
          } else {
            this.$message.error(res.msg || this.$t('emojiManagement.saveFailed'));
          }
        };
        if (payload.id) {
          Api.ota.updateOta(payload.id, payload, done);
        } else {
          Api.ota.saveOta(payload, done);
        }
      });
    },
    async copyLink(row) {
      const url = this.buildStableUrl(row.id);
      try {
        await navigator.clipboard.writeText(url);
        this.$message.success(this.$t('emojiManagement.copied'));
      } catch (e) {
        try {
          const ta = document.createElement('textarea');
          ta.value = url;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          this.$message.success(this.$t('emojiManagement.copied'));
        } catch (e2) {
          this.$message.warning(this.$t('emojiManagement.copyFailed') + ': ' + url);
        }
      }
    },
    downloadFile(row) {
      window.open(this.buildStableUrl(row.id));
    },
    deleteRow(row) {
      this.$confirm(this.$t('emojiManagement.confirmDelete'), this.$t('common.warning'), {
        confirmButtonText: this.$t('common.confirm'),
        cancelButtonText: this.$t('common.cancel'),
        type: 'warning'
      }).then(() => {
        Api.ota.deleteOta([row.id], (res) => {
          res = res.data;
          if (res.code === 0) {
            this.$message.success(this.$t('emojiManagement.deleteSuccess'));
            this.fetchList();
          } else {
            this.$message.error(res.msg || this.$t('otaManagement.deleteFailed'));
          }
        });
      }).catch(() => {});
    }
  }
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
  min-height: 506px;
  height: 100vh;
  display: flex;
  position: relative;
  flex-direction: column;
  background-size: cover;
  background: linear-gradient(to bottom right, #dce8ff, #e4eeff, #e6cbfd) center;
  overflow: hidden;
}

.main-wrapper {
  height: calc(100vh - 63px - 35px - 72px);
  margin: 0 22px;
  border-radius: 15px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  position: relative;
  background: rgba(237, 242, 255, 0.5);
  display: flex;
  flex-direction: column;
}

.operation-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
}

.page-title {
  font-size: 24px;
  margin: 0;
}

.right-operations {
  display: flex;
  gap: 10px;
  margin-left: auto;
}

.search-input {
  width: 240px;
}

.btn-search {
  background: linear-gradient(135deg, #555555, #a966ff);
  border: none;
  color: white;
}

.btn-api {
  background: #eef1ff;
  border: 1px solid #c7d0ff;
  color: #5f70f3;
}

.content-panel {
  flex: 1;
  display: flex;
  overflow: hidden;
  height: 100%;
  border-radius: 15px;
  background: transparent;
  border: 1px solid #fff;
}

.content-area {
  flex: 1;
  height: 100%;
  min-width: 600px;
  overflow: auto;
  background-color: white;
  display: flex;
  flex-direction: column;
}

.params-card {
  background: white;
  flex: 1;
  display: flex;
  flex-direction: column;
  border: none;
  box-shadow: none;
  overflow: hidden;

  ::v-deep .el-card__body {
    padding: 15px;
    display: flex;
    flex-direction: column;
    flex: 1;
    overflow: hidden;
  }
}

.table_bottom {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  margin-top: 10px;
}

.ctrl_btn {
  display: flex;
  gap: 8px;
  padding-left: 26px;
}

.link-text {
  font-size: 12px;
  color: #5f70f3;
  word-break: break-all;
}

.hint-text {
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
}

.upload-demo {
  text-align: left;
}

.el-upload__tip {
  line-height: 1.2;
  padding-top: 2%;
  color: #909399;
}

:deep(.transparent-table) {
  background: white;
  flex: 1;
  width: 100%;
}

:deep(.el-table .el-button--text) {
  color: #7079aa !important;
}
</style>
