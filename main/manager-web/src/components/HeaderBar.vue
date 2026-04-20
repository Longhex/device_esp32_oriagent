<template>
  <el-header class="header">
    <div class="header-container">
      <!-- 左侧留空 -->
      <div class="header-left">
      </div>

      <!-- 右侧元素 -->
      <div class="header-right">
        <div class="search-container" v-if="$route.path === '/home' && !(userInfo.superAdmin && isSmallScreen)">
          <div class="search-wrapper">
            <el-input v-model="search" :placeholder="$t('header.searchPlaceholder')" class="custom-search-input"
              @keyup.enter.native="handleSearch" @focus="showSearchHistory" @blur="hideSearchHistory" clearable
              ref="searchInput">
              <i slot="suffix" class="el-icon-search search-icon" @click="handleSearch"></i>
            </el-input>
            <!-- 搜索历史 -->
            <div v-if="showHistory && searchHistory.length > 0" class="search-history-dropdown">
              <div class="search-history-header">
                <span>{{ $t("header.searchHistory") }}</span>
                <el-button type="text" size="small" class="clear-history-btn" @click="clearSearchHistory">
                  {{ $t("header.clearHistory") }}
                </el-button>
              </div>
              <div class="search-history-list">
                <div v-for="(item, index) in searchHistory" :key="index" class="search-history-item"
                  @click.stop="selectSearchHistory(item)">
                  <span class="history-text">{{ item }}</span>
                  <i class="el-icon-close clear-item-icon" @click.stop="removeSearchHistory(index)"></i>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Change Password Dialog -->
    <ChangePasswordDialog v-model="isChangePasswordDialogVisible" />
  </el-header>
</template>

<script>
import i18n, { changeLanguage } from "@/i18n";
import { mapActions, mapState } from "vuex";
import ChangePasswordDialog from "./ChangePasswordDialog.vue";
import featureManager from "@/utils/featureManager";

export default {
  name: "HeaderBar",
  components: {
    ChangePasswordDialog,
  },
  props: ["devices"],
  data() {
    return {
      search: "",
      isChangePasswordDialogVisible: false,
      isSmallScreen: false,
      searchHistory: [],
      showHistory: false,
      SEARCH_HISTORY_KEY: "xiaozhi_search_history",
      MAX_HISTORY_COUNT: 3,
    };
  },
  computed: {
    ...mapState({
      userInfo: (state) => state.userInfo,
    }),
    currentLanguage() {
      return i18n.locale || "zh_CN";
    },
    xiaozhiAiIcon() {
      const currentLang = this.currentLanguage;
      switch (currentLang) {
        case "zh_CN": return require("@/assets/xiaozhi-ai.png");
        case "zh_TW": return require("@/assets/xiaozhi-ai_zh_TW.png");
        case "en": return require("@/assets/xiaozhi-ai_en.png");
        case "de": return require("@/assets/xiaozhi-ai_de.png");
        case "vi": return require("@/assets/xiaozhi-ai_vi.png");
        case "pt_BR": return require("@/assets/xiaozhi-ai_en.png");
        default: return require("@/assets/xiaozhi-ai.png");
      }
    },
  },
  async mounted() {
    this.checkScreenSize();
    window.addEventListener("resize", this.checkScreenSize);
    this.loadSearchHistory();
    await this.loadFeatureStatus();
  },
  beforeDestroy() {
    window.removeEventListener("resize", this.checkScreenSize);
  },
  methods: {
    async loadFeatureStatus() {
      await featureManager.waitForInitialization();
    },
    checkScreenSize() {
      this.isSmallScreen = window.innerWidth <= 1386;
    },
    handleSearch() {
      const searchValue = this.search.trim();
      if (!searchValue) {
        this.$emit("search-reset");
        return;
      }
      this.saveSearchHistory(searchValue);
      this.$emit("search", searchValue);
      if (this.$refs.searchInput) {
        this.$refs.searchInput.blur();
      }
    },
    showSearchHistory() {
      this.showHistory = true;
    },
    hideSearchHistory() {
      setTimeout(() => {
        this.showHistory = false;
      }, 200);
    },
    loadSearchHistory() {
      try {
        const history = localStorage.getItem(this.SEARCH_HISTORY_KEY);
        if (history) {
          this.searchHistory = JSON.parse(history);
        }
      } catch (error) {
        console.error("加载搜索历史失败:", error);
      }
    },
    saveSearchHistory(keyword) {
      if (!keyword || this.searchHistory.includes(keyword)) return;
      this.searchHistory.unshift(keyword);
      if (this.searchHistory.length > this.MAX_HISTORY_COUNT) {
        this.searchHistory = this.searchHistory.slice(0, this.MAX_HISTORY_COUNT);
      }
      try {
        localStorage.setItem(this.SEARCH_HISTORY_KEY, JSON.stringify(this.searchHistory));
      } catch (error) {
        console.error("保存搜索历史失败:", error);
      }
    },
    selectSearchHistory(keyword) {
      this.search = keyword;
      this.handleSearch();
    },
    removeSearchHistory(index) {
      this.searchHistory.splice(index, 1);
      try {
        localStorage.setItem(this.SEARCH_HISTORY_KEY, JSON.stringify(this.searchHistory));
      } catch (error) {
        console.error("更新搜索历史失败:", error);
      }
    },
    clearSearchHistory() {
      this.searchHistory = [];
      try {
        localStorage.removeItem(this.SEARCH_HISTORY_KEY);
      } catch (error) {
        console.error("清空搜索历史失败:", error);
      }
    },
    showChangePasswordDialog() {
      this.isChangePasswordDialogVisible = true;
    },
    ...mapActions(["logout"]),
  },
};
</script>

<style lang="scss" scoped>
.header {
  background: transparent;
  backdrop-filter: blur(5px);
  height: 60px !important;
  width: 100%;
  overflow: visible;
  position: sticky;
  top: 0;
  z-index: 1000;
}

.header-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 100%;
  padding: 0 20px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 300px;
  justify-content: flex-end;
}

.search-container {
  margin-right: 5px;
  flex: 0.9;
  min-width: 60px;
  max-width: none;
}

.search-wrapper {
  position: relative;
}

.search-history-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: white;
  border: 1px solid #e4e6ef;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  z-index: 1000;
  margin-top: 2px;
}

.search-history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid #f0f0f0;
  font-size: 12px;
  color: #909399;
}

.clear-history-btn {
  color: #909399;
  font-size: 11px;
  padding: 0;
  height: auto;
}

.search-history-list {
  max-height: 200px;
  overflow-y: auto;
}

.search-history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 12px;
  color: #606266;
  &:hover { background-color: #f5f7fa; .clear-item-icon { visibility: visible; } }
}

.clear-item-icon {
  font-size: 10px;
  color: #909399;
  visibility: hidden;
  &:hover { color: #ff4949; }
}

.custom-search-input>>>.el-input__inner {
  height: 32px;
  border-radius: 50px !important;
  background-color: #fff;
  border: 1px solid #e4e6ef;
  padding-left: 12px;
  font-size: 13px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  width: 100%;
}

.search-icon {
  cursor: pointer;
  color: #909399;
  margin-right: 5px;
  font-size: 14px;
  line-height: 32px;
}
</style>
