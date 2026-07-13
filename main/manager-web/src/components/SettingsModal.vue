<template>
  <el-dialog
    :visible.sync="show"
    custom-class="settings-dialog"
    :show-close="false"
    :append-to-body="true"
    :close-on-click-modal="true"
    width="1040px"
    top="6vh"
  >
    <div class="settings-shell">
      <!-- Nav trái -->
      <aside class="settings-nav">
        <div class="settings-nav-title">{{ $t('settings.title') }}</div>
        <div v-for="group in menu" :key="group.key" class="settings-nav-group">
          <div class="settings-nav-glabel">{{ $t(group.labelKey) }}</div>
          <div
            v-for="item in group.items"
            :key="item.key"
            class="settings-nav-item"
            :class="{ active: activeMenu === item.key }"
            @click="activeMenu = item.key"
          >
            <i :class="item.icon"></i>
            <span>{{ $t(item.labelKey) }}</span>
          </div>
        </div>
      </aside>

      <!-- Content phải -->
      <section class="settings-content">
        <div class="settings-content-head">
          <span class="settings-content-title">{{ activeTitle }}</span>
          <i class="el-icon-close settings-close" @click="show = false"></i>
        </div>

        <div class="settings-content-body">
          <!-- Ngôn ngữ (i18n thật) -->
          <div v-if="activeMenu === 'language'" class="settings-page">
            <div class="settings-field-label">{{ $t('settings.displayLanguage') }}</div>
            <el-select v-model="currentLang" class="settings-lang-select" @change="onChangeLang">
              <el-option v-for="l in languages" :key="l.value" :label="l.label" :value="l.value"></el-option>
            </el-select>
          </div>

          <!-- Tài khoản của tôi -->
          <div v-else-if="activeMenu === 'account'" class="settings-page">
            <div class="settings-acc-head">
              <span class="settings-acc-avatar">{{ userInitial }}</span>
              <div class="settings-acc-id">
                <div class="settings-acc-name">{{ userName }}</div>
                <div class="settings-acc-email" v-if="userEmail">{{ userEmail }}</div>
              </div>
            </div>
            <div class="settings-field-label">{{ $t('settings.password') }}</div>
            <el-button size="small" class="settings-pwd-btn" @click="pwdVisible = true">
              {{ $t('settings.changePassword') }}
            </el-button>
          </div>

          <!-- Nguồn dữ liệu (visual) -->
          <div v-else-if="activeMenu === 'data-source'" class="settings-page">
            <div class="settings-field-label">{{ $t('settings.ds.add') }}</div>
            <div class="ds-card">
              <div class="ds-icon ds-icon--notion">N</div>
              <div class="ds-info">
                <div class="ds-name">Notion</div>
                <div class="ds-desc">{{ $t('settings.ds.notionDesc') }}</div>
              </div>
              <el-button size="small" icon="el-icon-plus" class="ds-btn ds-btn--dark">{{ $t('settings.ds.addWorkspace') }}</el-button>
            </div>
            <div class="ds-card">
              <div class="ds-icon ds-icon--web"><i class="el-icon-connection"></i></div>
              <div class="ds-info">
                <div class="ds-name">Website <span class="ds-tag">With 🔥 FireCrawl</span></div>
                <div class="ds-desc">{{ $t('settings.ds.websiteDesc') }}</div>
              </div>
              <el-button size="small" class="ds-btn">{{ $t('settings.ds.configure') }}</el-button>
            </div>
          </div>

          <!-- Tích hợp (visual) -->
          <div v-else-if="activeMenu === 'integrations'" class="settings-page">
            <div class="settings-field-label">{{ $t('settings.int.connected') }}</div>
            <div class="int-row">
              <div class="int-icon int-icon--google">G</div>
              <div class="int-info">
                <div class="int-name">Google</div>
                <div class="int-desc">{{ $t('settings.int.googleDesc') }}</div>
              </div>
              <el-button size="small" class="int-btn">{{ $t('settings.int.connect') }}</el-button>
            </div>
            <div class="int-row">
              <div class="int-icon int-icon--gh"><i class="el-icon-s-platform"></i></div>
              <div class="int-info">
                <div class="int-name">GitHub</div>
                <div class="int-desc">{{ $t('settings.int.githubDesc') }}</div>
              </div>
              <el-button size="small" class="int-btn">{{ $t('settings.int.connect') }}</el-button>
            </div>
          </div>

          <!-- Mở rộng dựa trên API (visual) -->
          <div v-else-if="activeMenu === 'api-extension'" class="settings-page">
            <div class="api-desc">{{ $t('settings.api.desc') }}</div>
            <div class="api-empty">{{ $t('settings.api.empty') }}</div>
            <div class="api-add"><i class="el-icon-plus"></i>{{ $t('settings.api.add') }}</div>
          </div>

          <!-- Fallback -->
          <div v-else class="settings-page settings-empty">
            <i class="el-icon-time"></i>
            <span>{{ $t('settings.comingSoon') }}</span>
          </div>
        </div>
      </section>
    </div>

    <ChangePasswordDialog v-model="pwdVisible" />
  </el-dialog>
</template>

<script>
import { changeLanguage } from "@/i18n";
import ChangePasswordDialog from "@/components/ChangePasswordDialog.vue";

export default {
  name: "SettingsModal",
  components: { ChangePasswordDialog },
  props: {
    value: { type: Boolean, default: false },
  },
  data() {
    return {
      activeMenu: "account",
      pwdVisible: false,
      currentLang: this.$i18n.locale,
      languages: [
        { label: "中文简体", value: "zh_CN" },
        { label: "English", value: "en" },
        { label: "Tiếng Việt", value: "vi" },
      ],
      menu: [
        {
          key: "workspace",
          labelKey: "settings.workspaceGroup",
          items: [
            { key: "data-source", labelKey: "settings.dataSource", icon: "el-icon-coin" },
            { key: "api-extension", labelKey: "settings.apiExtension", icon: "el-icon-magic-stick" },
          ],
        },
        {
          key: "account",
          labelKey: "settings.accountGroup",
          items: [
            { key: "account", labelKey: "settings.account", icon: "el-icon-user" },
            { key: "integrations", labelKey: "settings.integrations", icon: "el-icon-connection" },
            { key: "language", labelKey: "settings.language", icon: "el-icon-position" },
          ],
        },
      ],
    };
  },
  computed: {
    show: {
      get() { return this.value; },
      set(v) { this.$emit("input", v); },
    },
    userInfo() { return this.$store.getters.getUserInfo || {}; },
    userName() { return this.userInfo.username || "User"; },
    userEmail() { return this.userInfo.email || ""; },
    userInitial() { return (this.userName || "U").charAt(0).toUpperCase(); },
    activeTitle() {
      const all = this.menu.reduce((acc, g) => acc.concat(g.items), []);
      const item = all.find((i) => i.key === this.activeMenu);
      return item ? this.$t(item.labelKey) : "";
    },
  },
  watch: {
    // Đồng bộ dropdown khi ngôn ngữ đổi từ nơi khác
    "$i18n.locale"(v) { this.currentLang = v; },
  },
  methods: {
    onChangeLang(lang) {
      changeLanguage(lang);
    },
  },
};
</script>

<style lang="scss">
/* el-dialog append vào body -> style KHÔNG scoped */
.settings-dialog {
  border-radius: 16px;
  overflow: hidden;
}
.settings-dialog .el-dialog__header { display: none; }
.settings-dialog .el-dialog__body { padding: 0; }

.settings-shell {
  display: flex;
  height: 640px;
}

/* Nav trái */
.settings-nav {
  width: 200px;
  flex-shrink: 0;
  padding: 16px;
  border-right: 1px solid #f2f4f7;
  box-sizing: border-box;
}
.settings-nav-title {
  font-size: 16px;
  font-weight: 500;
  color: #101828;
  margin: 4px 8px 20px;
}
.settings-nav-group { margin-bottom: 16px; }
.settings-nav-glabel {
  font-size: 12px;
  font-weight: 500;
  color: #667085;
  padding: 0 8px;
  margin-bottom: 6px;
  text-transform: uppercase;
}
.settings-nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 37px;
  padding: 0 8px;
  margin-bottom: 2px;
  border-radius: 8px;
  font-size: 14px;
  color: #475467;
  cursor: pointer;
  i { font-size: 16px; }
  &:hover:not(.active) { background: #f9fafb; }
  &.active { background: #eff4ff; color: #155eef; font-weight: 600; }
}

/* Content phải */
.settings-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.settings-content-head {
  display: flex;
  align-items: center;
  height: 56px;
  padding: 0 24px;
  border-bottom: 1px solid #f2f4f7;
}
.settings-content-title {
  font-size: 16px;
  font-weight: 500;
  color: #101828;
  flex: 1;
}
.settings-close {
  font-size: 18px;
  color: #98a2b3;
  cursor: pointer;
  &:hover { color: #475467; }
}
.settings-content-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
}
.settings-field-label {
  font-size: 14px;
  font-weight: 500;
  color: #101828;
  margin-bottom: 8px;
}
.settings-lang-select { width: 320px; }

/* Account */
.settings-acc-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 28px;
}
.settings-acc-avatar {
  width: 48px; height: 48px; border-radius: 50%;
  background: #dff5e8; color: #069d49;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 18px; flex-shrink: 0;
}
.settings-acc-name { font-size: 15px; font-weight: 600; color: #1d2939; }
.settings-acc-email { font-size: 13px; color: #667085; }
.settings-pwd-btn { border-radius: 8px; }

/* Trang trống */
.settings-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 320px;
  color: #98a2b3;
  gap: 10px;
  i { font-size: 32px; }
}

/* Nguồn dữ liệu — thẻ */
.settings-dialog .ds-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border: 0.5px solid #eaecf0;
  border-radius: 12px;
  margin-bottom: 12px;
}
.settings-dialog .ds-icon {
  width: 40px; height: 40px; border-radius: 10px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 18px; border: 1px solid #f2f4f7; background: #fff;
}
.settings-dialog .ds-icon--notion { color: #101828; }
.settings-dialog .ds-icon--web { color: #475467; i { font-size: 20px; } }
.settings-dialog .ds-info { flex: 1; min-width: 0; }
.settings-dialog .ds-name { font-size: 14px; font-weight: 600; color: #101828; }
.settings-dialog .ds-tag { font-size: 12px; font-weight: 400; color: #667085; margin-left: 4px; }
.settings-dialog .ds-desc { font-size: 12px; color: #667085; margin-top: 2px; }
.settings-dialog .ds-btn { border-radius: 8px; font-weight: 500; }
.settings-dialog .ds-btn--dark {
  background: #1a1a1c; border-color: #1a1a1c; color: #fff;
}
.settings-dialog .ds-btn--dark:hover,
.settings-dialog .ds-btn--dark:focus { background: #333335; border-color: #333335; color: #fff; }

/* Tích hợp — row */
.settings-dialog .int-row {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 12px; margin-bottom: 8px;
  background: #f9fafb; border: 0.5px solid #eaecf0; border-radius: 10px;
}
.settings-dialog .int-icon {
  width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0;
  background: #fff; border: 1px solid #f2f4f7;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 14px; color: #475467;
}
.settings-dialog .int-icon--google { color: #ea4335; }
.settings-dialog .int-info { flex: 1; min-width: 0; }
.settings-dialog .int-name { font-size: 14px; font-weight: 500; color: #1d2939; }
.settings-dialog .int-desc { font-size: 12px; color: #667085; }
.settings-dialog .int-btn { border-radius: 8px; }

/* Mở rộng API */
.settings-dialog .api-desc { font-size: 13px; color: #475467; margin-bottom: 16px; line-height: 1.5; }
.settings-dialog .api-empty {
  padding: 28px; text-align: center; color: #98a2b3; font-size: 13px;
  background: #f9fafb; border-radius: 12px; margin-bottom: 12px;
}
.settings-dialog .api-add {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  height: 36px; border-radius: 10px; background: #f9fafb; color: #475467;
  font-size: 13px; font-weight: 500; cursor: pointer;
}
.settings-dialog .api-add:hover { background: #f2f4f7; }
</style>
