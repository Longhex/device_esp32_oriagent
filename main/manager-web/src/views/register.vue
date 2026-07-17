<template>
  <div class="split-layout" @keyup.enter="register">
    <div class="split-left"></div>
    <div class="split-right">
      <!-- Logo top-left -->
      <div class="logo-area">
        <img src="@/assets/auth/logo.svg" alt="Oriagent" class="logo-img" @click="goToLogin" style="cursor: pointer" />
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
      <div class="form-center">
        <h1 class="form-title">{{ $t("auth.title") }}</h1>
        <p class="form-subtitle">{{ $t("auth.subtitle") }}</p>

        <!-- Google Register Button -->
        <div v-if="googleOAuthEnabled" class="google-btn" @click="handleGoogleLogin">
          <img src="@/assets/auth/icon-google.svg" alt="Google" class="google-icon" />
          <span>{{ $t("auth.google") }}</span>
        </div>

        <!-- Divider -->
        <div v-if="googleOAuthEnabled" class="divider">
          <span>{{ $t("auth.or") }}</span>
        </div>

        <form @submit.prevent="register">
          <!-- Username / Mobile input -->
          <div v-if="!enableMobileRegister">
            <label class="input-label">{{ $t("auth.emailLabel") }}</label>
            <div class="auth-input">
              <el-input v-model="form.username" :placeholder="$t('auth.emailPlaceholder')" />
            </div>
          </div>

          <!-- Mobile Registration Flow -->
          <template v-if="enableMobileRegister">
            <label class="input-label">{{ $t("login.mobileLabel") }}</label>
            <div class="auth-input mobile-input">
              <el-select v-model="form.areaCode" class="area-code-select">
                <el-option v-for="item in mobileAreaList" :key="item.key" :label="`${item.name} (${item.key})`" :value="item.key" />
              </el-select>
              <el-input v-model="form.mobile" :placeholder="$t('register.mobilePlaceholder')" />
            </div>

            <!-- Graphic Captcha for Mobile -->
            <label class="input-label">{{ $t("register.captcha") }}</label>
            <div class="captcha-row">
              <div class="auth-input">
                <el-input v-model="form.captcha" :placeholder="$t('register.captchaPlaceholder')" />
              </div>
              <img v-if="captchaUrl" :src="captchaUrl" alt="Captcha" class="captcha-img" @click="fetchCaptcha" />
            </div>

            <!-- SMS Verification -->
            <label class="input-label">{{ $t("register.mobileCaptcha") }}</label>
            <div class="captcha-row">
              <div class="auth-input">
                <el-input v-model="form.mobileCaptcha" :placeholder="$t('register.mobileCaptchaPlaceholder')" maxlength="6" />
              </div>
              <button type="button" class="send-captcha-btn" :disabled="!canSendMobileCaptcha" @click="sendMobileCaptcha">
                {{ countdown > 0 ? `${countdown}${$t('register.secondsLater')}` : $t('register.sendCaptcha') }}
              </button>
            </div>
          </template>

          <!-- Password -->
          <label class="input-label">{{ $t("auth.passwordLabel") }}</label>
          <div class="auth-input">
            <el-input v-model="form.password" :placeholder="$t('auth.passwordPlaceholder')" type="password" show-password />
          </div>

          <!-- Confirm Password -->
          <label class="input-label">{{ $t("auth.confirmPasswordLabel") }}</label>
          <div class="auth-input">
            <el-input v-model="form.confirmPassword" :placeholder="$t('auth.confirmPasswordPlaceholder')" type="password" show-password />
          </div>

          <!-- Graphic Captcha for Username Register -->
          <template v-if="!enableMobileRegister">
            <label class="input-label">{{ $t("auth.captchaLabel") }}</label>
            <div class="captcha-row">
              <div class="auth-input">
                <el-input v-model="form.captcha" :placeholder="$t('auth.captchaPlaceholder')" />
              </div>
              <img v-if="captchaUrl" :src="captchaUrl" alt="Captcha" class="captcha-img" @click="fetchCaptcha" />
            </div>
          </template>

          <!-- Links -->
          <div class="form-links">
            <div class="register-link">
              {{ $t("auth.haveAccount") }}
              <span class="link-action" @click="goToLogin">{{ $t("auth.loginBtn") }}</span>
            </div>
          </div>
        </form>

        <!-- Register button -->
        <div class="auth-btn" @click="register">{{ $t("auth.registerBtn") }}</div>


      </div>

      <!-- Footer -->
      <div class="footer-area">
        <version-footer />
      </div>
    </div>
  </div>
</template>

<script>
import Api from '@/apis/api';
import VersionFooter from '@/components/VersionFooter.vue';
import { getUUID, goToPage, showDanger, showSuccess, sm2Encrypt, validateMobile } from '@/utils';
import { mapState } from 'vuex';
import i18n, { changeLanguage } from '@/i18n';

export default {
  name: 'register',
  components: {
    VersionFooter
  },
  computed: {
    ...mapState({
      allowUserRegister: state => state.pubConfig.allowUserRegister,
      enableMobileRegister: state => state.pubConfig.enableMobileRegister,
      mobileAreaList: state => state.pubConfig.mobileAreaList,
      sm2PublicKey: state => state.pubConfig.sm2PublicKey,
      googleOAuthEnabled: state => state.pubConfig.googleOAuthEnabled || false,
    }),
    currentLanguage() {
      return i18n.locale || "zh_CN";
    },
    currentLanguageText() {
      const currentLang = this.currentLanguage;
      switch (currentLang) {
        case "zh_CN": return this.$t("language.zhCN");
        case "zh_TW": return this.$t("language.zhTW");
        case "en": return this.$t("language.en");
        case "de": return this.$t("language.de");
        case "vi": return this.$t("language.vi");
        case "pt_BR": return this.$t("language.ptBR");
        default: return this.$t("language.zhCN");
      }
    },
    currentLanguageFlag() {
      const currentLang = this.currentLanguage;
      const flags = {
        'zh_CN': '🇨🇳', 'zh_TW': '🇹🇼', 'en': '🇺🇸', 'de': '🇩🇪', 'vi': '🇻🇳', 'pt_BR': '🇧🇷',
      };
      return flags[currentLang] || '🇨🇳';
    },
    canSendMobileCaptcha() {
      return this.countdown === 0 && validateMobile(this.form.mobile, this.form.areaCode);
    }
  },
  data() {
    return {
      form: {
        username: '',
        password: '',
        confirmPassword: '',
        captcha: '',
        captchaId: '',
        areaCode: '+86',
        mobile: '',
        mobileCaptcha: ''
      },
      captchaUrl: '',
      countdown: 0,
      timer: null,
      languageDropdownVisible: false,
    }
  },
  mounted() {
    this.$store.dispatch('fetchPubConfig').then(() => {
      // Bỏ chặn redirect để phục vụ demo UI như yêu cầu. 
      // Nếu backend chặn đăng ký thật thì gọi API register sẽ báo lỗi sau.
      /*
      if (!this.allowUserRegister) {
        showDanger(this.$t('register.notAllowRegister'));
        setTimeout(() => {
          goToPage('/login');
        }, 1500);
      }
      */
    });
    this.fetchCaptcha();
  },
  methods: {
    openPage(url) {
      const lang = this.$i18n ? this.$i18n.locale : 'zh_CN';
      if (!lang.startsWith('zh')) {
        url = url.replace('.html', '-en.html');
      }
      window.open(url, '_blank');
    },
    handleLanguageDropdownVisibleChange(visible) {
      this.languageDropdownVisible = visible;
    },
    changeLanguage(lang) {
      changeLanguage(lang);
      this.languageDropdownVisible = false;
      this.$message.success({
        message: this.$t("message.success"),
        showClose: true,
      });
    },
    fetchCaptcha() {
      this.form.captchaId = getUUID();
      Api.user.getCaptcha(this.form.captchaId, (res) => {
        if (res.status === 200) {
          const blob = new Blob([res.data], { type: res.data.type });
          this.captchaUrl = URL.createObjectURL(blob);
        } else {
          console.error('验证码加载异常:', res);
          showDanger(this.$t('register.captchaLoadFailed'));
        }
      });
    },
    validateInput(input, message) {
      if (!input.trim()) {
        showDanger(message);
        return false;
      }
      return true;
    },
    sendMobileCaptcha() {
      if (!validateMobile(this.form.mobile, this.form.areaCode)) {
        showDanger(this.$t('register.inputCorrectMobile'));
        return;
      }
      if (!this.validateInput(this.form.captcha, this.$t('register.inputCaptcha'))) {
        this.fetchCaptcha();
        return;
      }

      if (this.timer) {
        clearInterval(this.timer);
        this.timer = null;
      }

      this.countdown = 60;
      this.timer = setInterval(() => {
        if (this.countdown > 0) {
          this.countdown--;
        } else {
          clearInterval(this.timer);
          this.timer = null;
        }
      }, 1000);

      Api.user.sendSmsVerification({
        phone: this.form.areaCode + this.form.mobile,
        captcha: this.form.captcha,
        captchaId: this.form.captchaId
      }, (res) => {
        showSuccess(this.$t('register.captchaSendSuccess'));
      }, (err) => {
        showDanger(err.data.msg || this.$t('register.captchaSendFailed'));
        this.countdown = 0;
        this.fetchCaptcha();
      });
    },
    async register() {
      if (this.enableMobileRegister) {
        if (!validateMobile(this.form.mobile, this.form.areaCode)) {
          showDanger(this.$t('register.inputCorrectMobile'));
          return;
        }
        if (!this.form.mobileCaptcha) {
          showDanger(this.$t('register.requiredMobileCaptcha'));
          return;
        }
      } else {
        if (!this.validateInput(this.form.username, this.$t('register.requiredUsername'))) {
          return;
        }
      }

      if (!this.validateInput(this.form.password, this.$t('register.requiredPassword'))) {
        return;
      }
      if (this.form.password !== this.form.confirmPassword) {
        showDanger(this.$t('register.passwordsNotMatch'))
        return
      }
      if (!this.validateInput(this.form.captcha, this.$t('register.requiredCaptcha'))) {
        return;
      }

      let encryptedPassword;
      try {
        const captchaAndPassword = this.form.captcha + this.form.password;
        encryptedPassword = sm2Encrypt(this.sm2PublicKey, captchaAndPassword);
      } catch (error) {
        console.error("密码加密失败:", error);
        showDanger(this.$t('sm2.encryptionFailed'));
        return;
      }

      let plainUsername;
      if (this.enableMobileRegister) {
        plainUsername = this.form.areaCode + this.form.mobile;
      } else {
        plainUsername = this.form.username;
      }

      const registerData = {
        username: plainUsername,
        password: encryptedPassword,
        captchaId: this.form.captchaId,
        mobileCaptcha: this.form.mobileCaptcha
      };

      Api.user.register(registerData, ({ data }) => {
        showSuccess(this.$t('register.registerSuccess'))
        goToPage('/login')
      }, (err) => {
        showDanger(err.data.msg || this.$t('register.registerFailed'))
        if (err.data != null && err.data.msg != null && err.data.msg.indexOf('图形验证码') > -1) {
          this.fetchCaptcha()
        }
      })
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
    goToLogin() {
      goToPage('/login')
    }
  },
  beforeDestroy() {
    if (this.timer) {
      clearInterval(this.timer);
    }
  }
}
</script>

<style lang="scss" scoped>
@import './auth.scss';

.captcha-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  
  .auth-input {
    flex: 1 1 auto;
    min-width: 0;
  }
}

.captcha-img {
  flex: 0 0 clamp(88px, 6vw, 100px);
  width: clamp(88px, 6vw, 100px);
  height: clamp(40px, 2.8vw, 50px);
  object-fit: contain;
  border-radius: 8px;
  cursor: pointer;
}

.send-captcha-btn {
  flex: 0 0 clamp(88px, 6vw, 100px);
  width: clamp(88px, 6vw, 100px);
  height: clamp(40px, 2.8vw, 50px);
  border-radius: 8px;
  font-size: 13px;
  background: #1a1a1a;
  color: #fff;
  border: none;
  cursor: pointer;
  transition: background 0.2s;

  &:hover {
    background: #333;
  }

  &:disabled {
    background: #c0c4cc;
    cursor: not-allowed;
  }
}
</style>
