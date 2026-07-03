<template>
  <div class="split-layout">
    <div class="split-left">
    </div>

    <div class="split-right">
      <!-- Logo top-left -->
      <div class="logo-area">
        <img src="@/assets/auth/logo.svg" alt="Oriagent" class="logo-img" />
      </div>

      <!-- Language pill top-right -->
      <div class="language-area">
        <el-dropdown trigger="click" @visible-change="handleLanguageDropdownVisibleChange">
          <span class="language-pill">
            <span class="language-flag">{{ currentLanguageFlag }}</span>
            <span class="language-text">{{ currentLanguageText }}</span>
            <i class="el-icon-arrow-down" :class="{ 'rotate-down': languageDropdownVisible }"></i>
          </span>
          <el-dropdown-menu slot="dropdown">
            <el-dropdown-item @click.native="changeLanguage('zh_CN')">{{ $t("language.zhCN") }}</el-dropdown-item>
            <el-dropdown-item @click.native="changeLanguage('zh_TW')">{{ $t("language.zhTW") }}</el-dropdown-item>
            <el-dropdown-item @click.native="changeLanguage('en')">{{ $t("language.en") }}</el-dropdown-item>
            <el-dropdown-item @click.native="changeLanguage('de')">{{ $t("language.de") }}</el-dropdown-item>
            <el-dropdown-item @click.native="changeLanguage('vi')">{{ $t("language.vi") }}</el-dropdown-item>
            <el-dropdown-item @click.native="changeLanguage('pt_BR')">{{ $t("language.ptBR") }}</el-dropdown-item>
          </el-dropdown-menu>
        </el-dropdown>
      </div>

      <!-- Form center -->
      <div class="form-center" @keyup.enter="login">
        <h1 class="form-title">Quản lý thiết bị</h1>
        <p class="form-subtitle">Kết nối thiết bị ESP32 vào hệ thống AI Agent</p>

        <!-- Google Login Button -->
        <div v-if="googleOAuthEnabled" class="google-btn" @click="handleGoogleLogin">
          <img src="@/assets/auth/icon-google.svg" alt="Google" class="google-icon" />
          <span>Đăng nhập hoặc đăng ký bằng Google</span>
        </div>

        <!-- Divider -->
        <div v-if="googleOAuthEnabled" class="divider">
          <span>hoặc</span>
        </div>

        <!-- Username / Mobile login -->
        <template v-if="!isMobileLogin">
          <label class="input-label">Địa chỉ Email</label>
          <div class="auth-input">
            <el-input v-model="form.username" placeholder="Email của bạn" />
          </div>
        </template>

        <template v-else>
          <label class="input-label">{{ $t("login.mobileLabel") }}</label>
          <div class="auth-input mobile-input">
            <el-select v-model="form.areaCode" class="area-code-select">
              <el-option v-for="item in mobileAreaList" :key="item.key" :label="`${item.name} (${item.key})`" :value="item.key" />
            </el-select>
            <el-input v-model="form.mobile" :placeholder="$t('login.mobilePlaceholder')" />
          </div>
        </template>

        <!-- Password -->
        <label class="input-label">Mật khẩu</label>
        <div class="auth-input">
          <el-input v-model="form.password" placeholder="Mật khẩu của bạn" type="password" show-password />
        </div>

        <!-- Register / Forgot links -->
        <div class="form-links">
          <div class="register-link">
            Bạn chưa có tài khoản?
            <span class="link-action" @click="goToRegister">Đăng ký ngay</span>
          </div>
          <div v-if="enableMobileRegister" class="forgot-link" @click="goToForgetPassword">
            {{ $t("login.forgetPassword") }}
          </div>
        </div>

        <!-- Login button -->
        <div class="auth-btn" @click="login">Đăng nhập</div>

        <!-- Login type toggle -->
        <div class="login-type-container" v-if="enableMobileRegister">
          <div style="display: flex; gap: 10px">
            <el-tooltip :content="$t('login.mobileLogin')" placement="bottom">
              <el-button :type="isMobileLogin ? 'primary' : 'default'" icon="el-icon-mobile" circle @click="switchLoginType('mobile')"></el-button>
            </el-tooltip>
            <el-tooltip :content="$t('login.usernameLogin')" placement="bottom">
              <el-button :type="!isMobileLogin ? 'primary' : 'default'" icon="el-icon-user" circle @click="switchLoginType('username')"></el-button>
            </el-tooltip>
          </div>
        </div>


      </div>

      <!-- Footer -->
      <div class="footer-area">
        <version-footer />
      </div>
    </div>
  </div>
</template>

<script>
import Api from "@/apis/api";
import VersionFooter from "@/components/VersionFooter.vue";
import i18n, { changeLanguage } from "@/i18n";
import { getUUID, goToPage, showDanger, showSuccess, sm2Encrypt, validateMobile } from "@/utils";
import { mapState } from "vuex";
import featureManager from "@/utils/featureManager";

export default {
  name: "login",
  components: {
    VersionFooter,
  },
  computed: {
    ...mapState({
      allowUserRegister: (state) => state.pubConfig.allowUserRegister,
      enableMobileRegister: (state) => state.pubConfig.enableMobileRegister,
      mobileAreaList: (state) => state.pubConfig.mobileAreaList,
      sm2PublicKey: (state) => state.pubConfig.sm2PublicKey,
      googleOAuthEnabled: (state) => state.pubConfig.googleOAuthEnabled || false,
    }),
    // 获取当前语言
    currentLanguage() {
      return i18n.locale || "zh_CN";
    },
    // 获取当前语言显示文本
    currentLanguageText() {
      const currentLang = this.currentLanguage;
      switch (currentLang) {
        case "zh_CN":
          return this.$t("language.zhCN");
        case "zh_TW":
          return this.$t("language.zhTW");
        case "en":
          return this.$t("language.en");
        case "de":
          return this.$t("language.de");
        case "vi":
          return this.$t("language.vi");
        case "pt_BR":
          return this.$t("language.ptBR");
        default:
          return this.$t("language.zhCN");
      }
    },
    currentLanguageFlag() {
      const currentLang = this.currentLanguage;
      const flags = {
        'zh_CN': '🇨🇳',
        'zh_TW': '🇹🇼',
        'en': '🇺🇸',
        'de': '🇩🇪',
        'vi': '🇻🇳',
        'pt_BR': '🇧🇷',
      };
      return flags[currentLang] || '🇨🇳';
    },
    // 根据当前语言获取对应的xiaozhi-ai图标
    xiaozhiAiIcon() {
      const currentLang = this.currentLanguage;
      switch (currentLang) {
        case "zh_CN":
          return require("@/assets/xiaozhi-ai.png");
        case "zh_TW":
          return require("@/assets/xiaozhi-ai_zh_TW.png");
        case "en":
          return require("@/assets/xiaozhi-ai_en.png");
        case "de":
          return require("@/assets/xiaozhi-ai_de.png");
        case "vi":
          return require("@/assets/xiaozhi-ai_vi.png");
        default:
          return require("@/assets/xiaozhi-ai.png");
      }
    },
  },
  data() {
    return {
      activeName: "username",
      form: {
        username: "",
        password: "",
        areaCode: "+86",
        mobile: "",
      },
      isMobileLogin: false,
      languageDropdownVisible: false,
    };
  },
  mounted() {
    this.$store.dispatch("fetchPubConfig").then(() => {
      // 根据配置决定默认登录方式
      this.isMobileLogin = this.enableMobileRegister;
    });
  },
  methods: {
    openPage(url) {
      const lang = this.$i18n ? this.$i18n.locale : 'zh_CN';
      if (!lang.startsWith('zh')) {
        url = url.replace('.html', '-en.html');
      }
      window.open(url, '_blank');
    },

    // 切换语言下拉菜单的可见状态变化
    handleLanguageDropdownVisibleChange(visible) {
      this.languageDropdownVisible = visible;
    },

    // 切换语言
    changeLanguage(lang) {
      changeLanguage(lang);
      this.languageDropdownVisible = false;
      this.$message.success({
        message: this.$t("message.success"),
        showClose: true,
      });
    },

    // 切换登录方式
    switchLoginType(type) {
      this.isMobileLogin = type === "mobile";
      // 清空表单
      this.form.username = "";
      this.form.mobile = "";
      this.form.password = "";
    },

    // 封装输入验证逻辑
    validateInput(input, messageKey) {
      if (!input.trim()) {
        showDanger(this.$t(messageKey));
        return false;
      }
      return true;
    },

    getUserInfo() {
      Api.user.getUserInfo(({ data }) => {
        if (data.code === 0) {
          this.$store.commit("setUserInfo", data.data);
          goToPage("/home");
        } else {
          showDanger("用户信息获取失败");
        }
      });
    },

    async login() {
      if (this.isMobileLogin) {
        // 手机号登录验证
        if (!validateMobile(this.form.mobile, this.form.areaCode)) {
          showDanger(this.$t('login.requiredMobile'));
          return;
        }
        // 拼接手机号作为用户名
        this.form.username = this.form.areaCode + this.form.mobile;
      } else {
        // 用户名登录验证
        if (!this.validateInput(this.form.username, 'login.requiredUsername')) {
          return;
        }
      }

      // 验证密码
      if (!this.validateInput(this.form.password, 'login.requiredPassword')) {
        return;
      }
      // 加密密码
      let encryptedPassword;
      try {
        encryptedPassword = sm2Encrypt(this.sm2PublicKey, this.form.password);
      } catch (error) {
        console.error("密码加密失败:", error);
        showDanger(this.$t('sm2.encryptionFailed'));
        return;
      }

      const plainUsername = this.form.username;

      const loginData = {
        username: plainUsername,
        password: encryptedPassword
      };

      Api.user.login(
        loginData,
        ({ data }) => {
          showSuccess(this.$t('login.loginSuccess'));
          this.$store.commit("setToken", JSON.stringify(data.data));
          this.getUserInfo();
        },
        (err) => {
          // 直接使用后端返回的国际化消息
          let errorMessage = err.data.msg || "登录失败";

          showDanger(errorMessage);
        }
      );


    },

    handleGoogleLogin() {
      const redirectUri = this.getOAuthCallbackRedirectUri()
      Api.user.getGoogleAuthUrl(
        redirectUri,
        ({ data }) => {
          const authUrl = data.data ? data.data.authUrl : data.authUrl
          window.location.href = authUrl
        },
        (err) => {
          const errorMessage = err && err.data && err.data.msg ? err.data.msg : this.$t('login.googleLoginFailed')
          showDanger(errorMessage)
        }
      )
    },

    getOAuthCallbackRedirectUri() {
      const publicPath = process.env.VUE_APP_PUBLIC_PATH || '/'
      const normalizedPublicPath = publicPath.endsWith('/') ? publicPath : `${publicPath}/`
      return `${window.location.origin}${normalizedPublicPath}oauth-callback.html`
    },

    goToRegister() {
      goToPage("/register");
    },
    goToForgetPassword() {
      goToPage("/retrieve-password");
    }
  },
};
</script>
<style lang="scss" scoped>
@import "./auth.scss";

.login-type-container {
  margin: 15px 0;
  display: flex;
  justify-content: center;
}

:deep(.el-button--primary) {
  background-color: #000000;
  border-color: #000000;

  &:hover,
  &:focus {
    background-color: #333333;
    border-color: #333333;
  }

  &:active {
    background-color: #111111;
    border-color: #111111;
  }
}
</style>
