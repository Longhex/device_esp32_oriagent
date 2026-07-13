<template>
  <div class="google-callback-container">
    <div class="loading-box">
      <i class="el-icon-loading"></i>
      <p>{{ $t('login.googleLoginProcessing') || 'Đang xử lý đăng nhập Google...' }}</p>
    </div>
  </div>
</template>

<script>
import Api from '@/apis/api';
import { goToPage, showDanger, showSuccess } from '@/utils';

export default {
  name: 'GoogleCallback',
  mounted() {
    this.handleCallback();
  },
  methods: {
    getOAuthCallbackRedirectUri() {
      const publicPath = process.env.VUE_APP_PUBLIC_PATH || '/'
      const normalizedPublicPath = publicPath.endsWith('/') ? publicPath : `${publicPath}/`
      return `${window.location.origin}${normalizedPublicPath}oauth-callback.html`
    },
    handleCallback() {
      const error = this.$route.query.error;
      if (error) {
        const msg = error === 'access_denied'
          ? 'Bạn đã huỷ đăng nhập Google'
          : `Lỗi đăng nhập Google: ${error}`;
        showDanger(msg);
        goToPage('/login');
        return;
      }

      const code = this.$route.query.code;
      const state = this.$route.query.state;

      if (!code) {
        showDanger('Không nhận được authorization code từ Google');
        goToPage('/login');
        return;
      }

      const redirectUri = this.getOAuthCallbackRedirectUri();

      const callbackData = {
        code: code,
        state: state,
        redirectUri: redirectUri
      };

      Api.user.googleCallback(
        callbackData,
        ({ data }) => {
          showSuccess(this.$t('login.loginSuccess') || 'Đăng nhập thành công');
          this.$store.commit("setToken", JSON.stringify(data.data));
          this.getUserInfo();
        },
        (err) => {
          let errorMessage = (err && err.data && err.data.msg) ? err.data.msg : "Đăng nhập Google thất bại";
          showDanger(errorMessage);
          goToPage('/login');
        }
      );
    },
    getUserInfo() {
      Api.user.getUserInfo(({ data }) => {
        if (data.code === 0) {
          this.$store.commit("setUserInfo", data.data);
          goToPage("/home");
        } else {
          showDanger("Lấy thông tin người dùng thất bại");
          goToPage('/login');
        }
      });
    }
  }
}
</script>

<style scoped>
.google-callback-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background-color: #f5f5f5;
}

.loading-box {
  text-align: center;
  padding: 40px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.el-icon-loading {
  font-size: 40px;
  color: #1a1a1a;
  margin-bottom: 20px;
}
</style>
