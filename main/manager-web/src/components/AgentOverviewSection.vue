<template>
  <div class="ov-root">
    <div class="ov-head">
      <div class="ov-crumb">
        <span class="ov-crumb-item">{{ agentName || $t('overview.crumbAgent') }}</span>
        <span class="ov-crumb-sep">/</span>
        <span>{{ $t('overview.title') }}</span>
      </div>
      <div class="ov-title">{{ $t('overview.title') }}</div>
      <div class="ov-desc">{{ $t('overview.desc') }}</div>
    </div>

    <div class="ov-kpi-grid">
      <div v-for="k in kpis" :key="k.key" class="ov-kpi">
        <div class="ov-kpi-label">{{ k.label }}</div>
        <div class="ov-kpi-value" :class="{ 'is-empty': !k.available }">{{ k.available ? k.value : '—' }}</div>
        <div class="ov-kpi-sub">{{ k.available ? k.sub : $t('overview.noData') }}</div>
        <div class="ov-kpi-ic"><span class="studio-ic" :class="'studio-ic--' + k.icon"></span></div>
        <div v-if="k.available && k.badge" class="ov-kpi-badge">{{ k.badge }}</div>
      </div>
    </div>

    <div class="ov-bottom">
      <div class="ov-panel ov-chart-panel">
        <div class="ov-panel-head">
          <div>
            <div class="ov-panel-title">{{ $t('overview.activityTitle') }}</div>
            <div class="ov-panel-sub">{{ $t('overview.activitySub') }}</div>
          </div>
          <div class="ov-filter-pill">{{ $t('overview.last24h') }}</div>
        </div>

        <div class="ov-chart">
          <div class="ov-chart-bars">
            <div v-for="(h, i) in hourly" :key="i" class="ov-bar-slot">
              <div class="ov-bar" :style="{ height: barHeight(h) }"></div>
            </div>
          </div>
          <div v-if="!activityAvailable" class="ov-chart-empty">{{ $t('overview.noData') }}</div>
          <div class="ov-chart-axis">
            <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span>
          </div>
        </div>
      </div>

      <div class="ov-panel ov-health-panel">
        <div class="ov-panel-title">{{ $t('overview.fleetHealth') }}</div>
        <div class="ov-health-list">
          <div v-for="row in fleetHealth" :key="row.key" class="ov-health-row">
            <div class="ov-health-top">
              <span class="ov-health-label">{{ row.label }}</span>
              <span class="ov-health-value" :class="{ 'is-empty': !row.available }">
                {{ row.available ? $t('overview.robotsCount', { n: row.value }) : '—' }}
              </span>
            </div>
            <div class="ov-progress">
              <div class="ov-progress-fill" :style="{ width: row.available ? row.percent + '%' : '0%' }"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
// Ngưỡng coi thiết bị là "online", dựa trên last_connected_at.
// CẢNH BÁO: last_connected_at chỉ được ghi khi thiết bị check-in OTA
// (DeviceServiceImpl.checkDeviceActive) — tức lúc khởi động, KHÔNG phải nhịp tim.
// Thiết bị bật lâu mà vẫn online sẽ bị tính là offline. Muốn chính xác phải lấy
// từ danh sách kết nối sống của xiaozhi-server hoặc MQTT gateway (chưa có API).
const ONLINE_WINDOW_MINUTES = 15;

export default {
  name: 'AgentOverviewSection',
  props: {
    agentName: { type: String, default: '' },
    devices: { type: Array, default: () => [] }
  },
  data() {
    return {
      // 24 ô cho 24 giờ. Cần API thống kê theo giờ mới có số thật (chưa có).
      hourly: new Array(24).fill(0),
      activityAvailable: false
    };
  },
  computed: {
    totalRobots() {
      return this.devices.length;
    },
    onlineRobots() {
      const limit = Date.now() - ONLINE_WINDOW_MINUTES * 60 * 1000;
      return this.devices.filter(d => {
        const t = this.parseTime(d.lastConnectedAt);
        return t !== null && t >= limit;
      }).length;
    },
    onlinePercent() {
      if (!this.totalRobots) return 0;
      return (this.onlineRobots / this.totalRobots) * 100;
    },
    kpis() {
      return [
        {
          key: 'robots',
          label: this.$t('overview.kpiRobots'),
          icon: 'stat-robot',
          available: true,
          value: this.onlineRobots,
          sub: this.$t('overview.ofTotal', { n: this.totalRobots }),
          badge: this.totalRobots ? this.onlinePercent.toFixed(1) + '%' : null
        },
        // Bảng chat history có dữ liệu nhưng chưa có API đếm theo 24h.
        { key: 'conversations', label: this.$t('overview.kpiConversations'), icon: 'stat-comments', available: false },
        // Chưa có bảng nào ghi lại tool/plugin execution.
        { key: 'tools', label: this.$t('overview.kpiToolSuccess'), icon: 'stat-tools', available: false },
        // perf_metrics chỉ nằm trong RAM của xiaozhi-server, không lưu, không có API.
        { key: 'latency', label: this.$t('overview.kpiAvgResponse'), icon: 'stat-bolt', available: false }
      ];
    },
    fleetHealth() {
      return [
        {
          key: 'online',
          label: this.$t('overview.healthOnline'),
          available: true,
          value: this.onlineRobots,
          percent: this.onlinePercent
        },
        // Hệ thống chưa có khái niệm certificate cho thiết bị.
        { key: 'cert', label: this.$t('overview.healthCert'), available: false, value: 0, percent: 0 },
        // Bảng ai_ota rỗng -> không có phiên bản mốc để so với app_version.
        { key: 'firmware', label: this.$t('overview.healthFirmware'), available: false, value: 0, percent: 0 },
        // Chưa có khái niệm đồng bộ agent xuống thiết bị.
        { key: 'synced', label: this.$t('overview.healthSynced'), available: false, value: 0, percent: 0 }
      ];
    },
    maxHourly() {
      return Math.max(...this.hourly, 1);
    }
  },
  methods: {
    parseTime(value) {
      if (!value) return null;
      // Backend trả "yyyy-MM-dd HH:mm:ss" — Safari không parse được dạng có dấu cách.
      const t = new Date(String(value).replace(' ', 'T')).getTime();
      return Number.isNaN(t) ? null : t;
    },
    barHeight(v) {
      if (!this.activityAvailable) return '2px';
      return Math.max(2, (v / this.maxHourly) * 100) + '%';
    }
  }
};
</script>

<style lang="scss" scoped>
@import "@/views/studio.scss";

$ov-border: #ececec;
$ov-mint: #0a9d4f;

/* Nền trắng theo ảnh mẫu ("nền trang: trắng, card phân tách bằng viền xám nhạt").
   flex:1 + min-height:0 -> panel lấp hết chiều cao khả dụng và cuộn nội bộ nếu tràn,
   không đẩy dài shell (shell đã khoá 100vh). */
.ov-root {
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 14px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background: #fff;
  border-radius: $studio-radius-panel;
  border: 1px solid $ov-border;
  padding: 22px;
}

/* ---------- Tiêu đề ---------- */
.ov-crumb {
  font-size: 12px;
  color: #9a9a9a;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.ov-crumb-item { max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ov-crumb-sep { color: #cfcfcf; }

.ov-title {
  font-size: 28px;
  font-weight: 700;
  color: #17171a;
  line-height: 1.2;
}
.ov-desc {
  font-size: 14px;
  color: #6b6b6b;
  margin-top: 6px;
}

/* ---------- Hàng KPI ---------- */
.ov-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.ov-kpi {
  position: relative;
  background: #fff;
  border: 1px solid $ov-border;
  border-radius: 15px;
  padding: 16px;
  min-height: 116px;
}

.ov-kpi-label {
  font-size: 12px;
  color: #7a7a7a;
  padding-right: 44px;
}

.ov-kpi-value {
  font-size: 30px;
  font-weight: 700;
  color: #17171a;
  line-height: 1.25;
  margin-top: 6px;

  &.is-empty { color: #c6c6c6; }
}

.ov-kpi-sub {
  font-size: 12px;
  color: #9a9a9a;
  padding-right: 62px;
}

.ov-kpi-ic {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: #f1f1f1;
  color: #666;
  display: flex;
  align-items: center;
  justify-content: center;

  .studio-ic { width: 15px; height: 15px; }
}

.ov-kpi-badge {
  position: absolute;
  right: 14px;
  bottom: 14px;
  border: 1px solid $ov-border;
  border-radius: $studio-radius-pill;
  padding: 3px 9px;
  font-size: 11px;
  font-weight: 600;
  color: $ov-mint;
  background: #fff;
}

/* ---------- Khu vực dưới ---------- */
/* flex:1 -> 2 card dưới giãn lấp hết chiều cao còn lại của panel (ảnh mẫu:
   "vùng biểu đồ phải dùng đúng phần không gian còn lại, không bị ép thấp").
   min-height giữ sàn để màn thấp không bóp nát biểu đồ. */
.ov-bottom {
  display: grid;
  grid-template-columns: 6fr 4fr;
  gap: 12px;
  flex: 1;
  min-height: 240px;
}

.ov-panel {
  background: #fff;
  border: 1px solid $ov-border;
  border-radius: 15px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.ov-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.ov-panel-title { font-size: 15px; font-weight: 600; color: #17171a; }
.ov-panel-sub { font-size: 12px; color: #9a9a9a; margin-top: 2px; }

.ov-filter-pill {
  border: 1px solid $ov-border;
  border-radius: $studio-radius-pill;
  padding: 4px 12px;
  font-size: 12px;
  color: #6b6b6b;
  flex-shrink: 0;
}

/* ---------- Biểu đồ ---------- */
/* flex:1 + min-height:0 -> vùng biểu đồ ăn hết chỗ còn lại của card,
   thay cho height:150px cố định (ảnh mẫu: biểu đồ không bị ép thấp). */
.ov-chart {
  position: relative;
  margin-top: 18px;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.ov-chart-bars {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  flex: 1;
  min-height: 90px;
  border-bottom: 1px solid #ededed;
  padding-bottom: 1px;
}

.ov-bar-slot {
  flex: 1;
  height: 100%;
  display: flex;
  align-items: flex-end;
}

.ov-bar {
  width: 100%;
  background: #e2e2e2;
  border-radius: 4px 4px 0 0;
  transition: height 0.2s ease;
}

.ov-chart-empty {
  position: absolute;
  inset: 0 0 22px 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: #b5b5b5;
}

.ov-chart-axis {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 11px;
  color: #a8a8a8;
}

/* ---------- Fleet health ---------- */
/* Các hàng chia đều chỗ còn lại -> card Fleet health không để trống đáy
   khi nó bị kéo cao bằng card biểu đồ. */
.ov-health-list {
  margin-top: 18px;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  gap: 16px;
}

.ov-health-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 7px;
}

.ov-health-label { font-size: 13px; color: #4a4a4a; }
.ov-health-value {
  font-size: 13px;
  font-weight: 600;
  color: #17171a;

  &.is-empty { color: #c6c6c6; font-weight: 400; }
}

.ov-progress {
  height: 6px;
  border-radius: $studio-radius-pill;
  background: #f0f0f0;
  overflow: hidden;
}

.ov-progress-fill {
  height: 100%;
  border-radius: $studio-radius-pill;
  background: #17171a;
  transition: width 0.3s ease;
}

/* ---------- Responsive ---------- */
@media (max-width: 1200px) {
  .ov-kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .ov-bottom { grid-template-columns: 1fr; }
}

@media (max-width: 640px) {
  .ov-kpi-grid { grid-template-columns: 1fr; }
  .ov-title { font-size: 24px; }
}
</style>
