import 'element-ui/lib/theme-chalk/index.css';
import 'normalize.css/normalize.css'; // A modern alternative to CSS resets
import Vue from 'vue';
import ElementUI from 'element-ui';
import ElementLocale from 'element-ui/lib/locale';
import App from './App.vue';
import router from './router';
import store from './store';
// Import SAU store: SettingsLayout kéo theo chuỗi ChangePasswordDialog -> apis/module/user;
// nếu import trước store sẽ front-load user.js -> circular import -> Api.user undefined.
import SettingsLayout from './components/SettingsLayout.vue';
import i18n from './i18n';
import './styles/global.scss';
import { register as registerServiceWorker } from './registerServiceWorker';
import featureManager from './utils/featureManager';

// 创建事件总线，用于组件间通信
Vue.prototype.$eventBus = new Vue();

Vue.use(ElementUI);
// Đăng ký global -> mọi trang quản lý dùng <SettingsLayout> khỏi import lẻ.
Vue.component('SettingsLayout', SettingsLayout);
// Nối Element UI với vue-i18n -> các text mặc định của Element (phân trang "共 X 条",
// nút hộp thoại 确定/取消...) hiển thị theo NGÔN NGỮ app thay vì tiếng Trung mặc định.
ElementLocale.i18n((key, value) => i18n.t(key, value));

Vue.config.productionTip = false

// 注册Service Worker
registerServiceWorker();

// 创建Vue实例
new Vue({
  router,
  store,
  i18n,
  render: function (h) { return h(App) }
}).$mount('#app')
