<template>
  <div class="sidebar">
    <div class="sidebar-logo" @click="goHome">
      <img src="@/assets/logo_oriagent.svg" alt="Oriagent" class="logo-img" />
    </div>
    
    <el-menu
      :default-active="activeMenu"
      class="sidebar-menu"
      @select="handleSelect"
      background-color="transparent"
      text-color="#3d4566"
      active-text-color="#000"
    >
      <el-menu-item index="/home">
        <i class="el-icon-monitor"></i>
        <span slot="title">{{ $t("header.smartManagement") }}</span>
      </el-menu-item>
      
      <el-submenu v-if="userInfo.superAdmin" index="models">
        <template slot="title">
          <i class="el-icon-cpu"></i>
          <span>{{ $t("header.modelConfig") }}</span>
        </template>
        <el-menu-item index="/model-config?tab=vad">
          <i class="el-icon-microphone"></i>
          <span>{{ $t("modelConfig.vad") }}</span>
        </el-menu-item>
        <el-menu-item index="/model-config?tab=asr">
          <i class="el-icon-chat-dot-round"></i>
          <span>{{ $t("modelConfig.asr") }}</span>
        </el-menu-item>
        <el-menu-item index="/model-config?tab=llm">
          <i class="el-icon-cpu"></i>
          <span>{{ $t("modelConfig.llm") }}</span>
        </el-menu-item>
        <el-menu-item index="/model-config?tab=vllm">
          <i class="el-icon-picture-outline"></i>
          <span>{{ $t("modelConfig.vllm") }}</span>
        </el-menu-item>
        <el-menu-item index="/model-config?tab=intent">
          <i class="el-icon-aim"></i>
          <span>{{ $t("modelConfig.intent") }}</span>
        </el-menu-item>
        <el-menu-item index="/model-config?tab=tts">
          <i class="el-icon-headset"></i>
          <span>{{ $t("modelConfig.tts") }}</span>
        </el-menu-item>
        <el-menu-item index="/model-config?tab=memory">
          <i class="el-icon-collection"></i>
          <span>{{ $t("modelConfig.memory") }}</span>
        </el-menu-item>
        <el-menu-item index="/model-config?tab=rag">
          <i class="el-icon-notebook-2"></i>
          <span>{{ $t("modelConfig.rag") }}</span>
        </el-menu-item>
      </el-submenu>
      
      <el-submenu index="more">

        <template slot="title">
          <i class="el-icon-more"></i>
          <span>{{ $t("header.paramDictionary") }}</span>
        </template>
        
        <el-menu-item v-if="featureStatus.voiceClone" index="/voice-clone-management">
          <i class="el-icon-mic"></i>
          <span>{{ $t("header.voiceCloneManagement") }}</span>
        </el-menu-item>
        
        <el-menu-item v-if="featureStatus.knowledgeBase" index="/knowledge-base-management">
          <i class="el-icon-notebook-1"></i>
          <span>{{ $t("header.knowledgeBase") }}</span>
        </el-menu-item>
        
        <template v-if="userInfo.superAdmin">
          <el-menu-item index="/user-management">
            <i class="el-icon-user"></i>
            <span>{{ $t("header.userManagement") }}</span>
          </el-menu-item>
          
          <el-menu-item index="/ota-management">
            <i class="el-icon-upload"></i>
            <span>{{ $t("header.otaManagement") }}</span>
          </el-menu-item>
          
          <el-menu-item index="/provider-management">
            <i class="el-icon-connection"></i>
            <span>{{ $t("header.providerManagement") }}</span>
          </el-menu-item>
          
          <el-menu-item index="/agent-template-management">
            <i class="el-icon-copy-document"></i>
            <span>{{ $t("header.agentTemplate") }}</span>
          </el-menu-item>
          
          <el-menu-item index="/params-management">
            <i class="el-icon-setting"></i>
            <span>{{ $t("header.paramManagement") }}</span>
          </el-menu-item>
          
          <el-menu-item index="/dict-management">
            <i class="el-icon-document"></i>
            <span>{{ $t("header.dictManagement") }}</span>
          </el-menu-item>
          
          <el-menu-item index="/server-side-management">
            <i class="el-icon-set-up"></i>
            <span>{{ $t("header.serverSideManagement") }}</span>
          </el-menu-item>
          
          <el-menu-item index="/feature-management">
            <i class="el-icon-magic-stick"></i>
            <span>{{ $t("header.featureManagement") }}</span>
          </el-menu-item>
        </template>
      </el-submenu>
    </el-menu>
    
    <div class="sidebar-footer">
      <div class="account-actions">
        <!-- Language Switcher Button -->
        <el-dropdown trigger="click" @command="handleLanguageChange" placement="top-start" class="action-dropdown">
          <div class="action-btn language-btn" :title="$t('sidebar.language')">
            <i class="el-icon-info action-icon"></i>
            <span class="action-label">{{ currentLanguageLabel }}</span>
          </div>
          <el-dropdown-menu slot="dropdown" class="modern-lang-dropdown">
            <el-dropdown-item v-for="lang in languages" :key="lang.value" :command="lang.value" :class="{ 'is-active': currentLanguage === lang.value }">
              {{ lang.label }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </el-dropdown>

        <!-- Logout Button -->
        <div class="action-btn logout-btn" @click="handleLogout" :title="$t('sidebar.logout')">
          <img src="@/assets/icons/LogOut01.svg" class="action-icon" />
          <span class="action-label">{{ $t('sidebar.logout') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { mapState, mapActions } from "vuex";
import { changeLanguage } from "@/i18n";

export default {
  name: "SideBar",
  data() {
    return {
      accountMenuVisible: false,
      isLanguageMenuVisible: false,
      languages: [
        { label: "中文简体", value: "zh_CN" },
        { label: "English", value: "en" },
        { label: "Tiếng Việt", value: "vi" }
      ]
    };
  },
  computed: {
    ...mapState({
      featureStatus: (state) => ({
        voiceClone: state.pubConfig.systemWebMenu?.features?.voiceClone?.enabled,
        knowledgeBase: state.pubConfig.systemWebMenu?.features?.knowledgeBase?.enabled,
      }),
      userInfo: (state) => state.userInfo,
    }),
    activeMenu() {
      const { path, query } = this.$route;
      if (path === '/model-config' && query.tab) {
        return `${path}?tab=${query.tab}`;
      }
      if (path === '/agent-config' || path === '/template-quick-config') {
          return '/home';
      }
      if (path === '/knowledge-file-upload') {
          return '/knowledge-base-management';
      }
      if (path === '/voice-resource-management') {
          return '/voice-clone-management';
      }
      return path;
    },
    currentLanguage() {
      return this.$i18n.locale || "zh_CN";
    },
    currentLanguageLabel() {
      const lang = this.languages.find(l => l.value === this.currentLanguage);
      if (this.currentLanguage === 'zh_CN') return 'CN';
      if (this.currentLanguage === 'en') return 'EN';
      if (this.currentLanguage === 'vi') return 'VI';
      return lang ? lang.label : 'EN';
    },
    hasGlobeIcon() {
       return false;
    }
  },
  watch: {
    $route() {
      // Force update active menu if needed
    }
  },
  methods: {

    handleSelect(index) {
      if (index && index !== 'more') {
        if (this.$route.path !== index) {
          this.$router.push(index);
        }
      }
    },
    goHome() {
      if (this.$route.path !== '/home') {
        this.$router.push("/home");
      }
    },
    handleLanguageChange(lang) {
      changeLanguage(lang);
      this.$message.success(this.$t("message.success"));
    },
    async handleLogout() {
      try {
        await this.logout();
        this.$router.push("/login"); // Ensure redirect after logout
        this.$message.success(this.$t("message.success"));
      } catch (error) {
        this.$message.error(this.$t("message.error"));
      }
    },
    ...mapActions(["logout"])
  }
};
</script>

<style lang="scss" scoped>
.sidebar {
  width: 240px;
  height: 100vh;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(15px);
  border-right: 1px solid rgba(0, 0, 0, 0.05);
  display: flex;
  flex-direction: column;
  transition: all 0.3s ease;
  position: fixed;
  left: 0;
  top: 0;
  z-index: 1001;
  box-shadow: 4px 0 15px rgba(0, 0, 0, 0.02);
}

.sidebar-logo {
  padding: 30px 20px;
  cursor: pointer;
  display: flex;
  justify-content: center;
  align-items: center;
  
  .logo-img {
    height: 36px;
    width: auto;
    filter: drop-shadow(0 2px 4px rgba(0,0,0,0.1));
  }
}

.sidebar-menu {
  border-right: none;
  flex: 1;
  overflow-y: auto;
  padding: 10px 0;
  
  &::-webkit-scrollbar {
    width: 4px;
  }
  &::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.05);
    border-radius: 2px;
  }
}

::v-deep {
  .el-menu {
    border-right: none;
  }
  
  .el-menu-item, .el-submenu__title {
    height: 48px;
    line-height: 48px;
    margin: 4px 16px;
    border-radius: 12px;
    font-weight: 500;
    color: #5c637a !important;
    transition: all 0.2s ease;
    text-align: left;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    
    i {
      color: #5c637a;
      margin-right: 12px;
      font-size: 18px;
      vertical-align: middle;
    }
    
    &:hover {
      background: rgba(0, 0, 0, 0.04) !important;
      color: #000 !important;
      
      i {
          color: #000;
      }
    }
    
    &.is-active {
      background: #000 !important;
      color: #fff !important;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      
      i {
        color: #fff;
      }
      
      span {
          color: #fff;
      }
    }
  }
  
  .el-submenu {
    &.is-active {
       .el-submenu__title {
          background: rgba(0, 0, 0, 0.02);
          color: #000 !important;
          
          i {
              color: #000;
          }
       }
    }
  }
  
  .el-submenu .el-menu-item {
    height: 40px;
    line-height: 40px;
    padding-left: 20px !important;
    margin: 2px 16px;
    font-size: 13.5px;
    
    i {
        font-size: 16px;
    }
  }
}

.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
  margin-top: auto;
}

.account-actions {
  display: flex;
  gap: 8px;
  width: 100%;

  .action-dropdown {
    flex: 1;
  }

  .action-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    height: 38px;
    padding: 0 12px;
    border-radius: 12px;
    border: 1px solid #E5E7EB;
    background-color: #F9FAFB;
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    flex: 1;
    min-width: 0;

    &:hover {
      background-color: #F3F4F6;
      border-color: #D1D5DB;
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }

    .action-icon {
      width: 18px;
      height: 18px;
      flex-shrink: 0;
      object-fit: contain;
    }

    .action-label {
      font-size: 13px;
      font-weight: 600;
      color: #374151;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  }

  .logout-btn {
    &:hover {
      background-color: #FEF2F2;
      border-color: #FECACA;
      .action-label { color: #DC2626; }
    }
  }
}

.modern-lang-dropdown {
  border-radius: 12px;
  padding: 4px;
  border: 1px solid rgba(0,0,0,0.05);
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  
  .el-dropdown-menu__item {
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 13px;
    margin: 2px 0;
    
    &:hover { background-color: #F3F4F6; color: #000; }
    &.is-active { background-color: #000; color: #fff; }
  }
}
</style>
