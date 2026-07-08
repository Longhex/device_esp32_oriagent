<template>
  <div class="studio-agent-card" @click="handleCardClick">
    <div class="card-head">
      <div class="card-avatar"><img src="@/assets/home/robot-avatar.png" class="card-avatar-img" alt="" /></div>
      <div class="card-title-block">
        <el-tooltip :content="device.agentName" placement="top" effect="light">
          <div class="card-name">{{ device.agentName }}</div>
        </el-tooltip>
        <div class="card-sub">Agent</div>
      </div>
      <div class="card-actions">
        <img src="@/assets/home/delete.png" class="card-icon" @click.stop="handleDelete" />
        <el-tooltip effect="light" :content="device.systemPrompt" placement="top" popper-class="custom-tooltip">
          <img src="@/assets/home/info.png" class="card-icon" />
        </el-tooltip>
      </div>
    </div>

    <div class="card-chips">
      <div class="chip"><span class="chip-label"><i class="el-icon-microphone"></i> TTS</span><span class="chip-value">{{ device.ttsModelName }}</span></div>
      <div class="chip"><span class="chip-label"><i class="el-icon-cpu"></i> LLM</span><span class="chip-value">{{ device.llmModelName }}</span></div>
      <div class="chip"><span class="chip-label"><i class="el-icon-headset"></i> Voice</span><span class="chip-value">{{ device.ttsVoiceName }}</span></div>
    </div>

    <div class="card-foot">
      <span class="foot-badge"><span class="studio-ic studio-ic--device badge-ic"></span>{{ device.deviceCount || 0 }} {{ $t('roleConfig.tabDevice') }}</span>
      <span v-if="device.memModelId !== 'Memory_nomem'" class="foot-badge"><i class="el-icon-chat-dot-round"></i> History</span>
      <span class="foot-time">{{ formattedLastConnectedTime }}</span>
    </div>
    <el-tooltip v-if="tags.length" :content="tags.join()" placement="top" effect="light">
      <div class="card-tags">{{ tags.join() }}</div>
    </el-tooltip>
  </div>
</template>

<script>
export default {
  name: 'DeviceItem',
  props: {
    device: { type: Object, required: true },
    featureStatus: {
      type: Object,
      default: () => ({
        voiceprintRecognition: false,
        voiceClone: false,
        knowledgeBase: false
      })
    }
  },
  data() {
    return {}
  },
  computed: {
    formattedLastConnectedTime() {
      if (!this.device.lastConnectedAt) return this.$t('home.noConversation');

      const lastTime = new Date(this.device.lastConnectedAt);
      const now = new Date();
      const diffMinutes = Math.floor((now - lastTime) / (1000 * 60));

      if (diffMinutes <= 1) {
        return this.$t('home.justNow');
      } else if (diffMinutes < 60) {
        return this.$t('home.minutesAgo', { minutes: diffMinutes });
      } else if (diffMinutes < 24 * 60) {
        const hours = Math.floor(diffMinutes / 60);
        const minutes = diffMinutes % 60;
        return this.$t('home.hoursAgo', { hours, minutes });
      } else {
        return this.device.lastConnectedAt;
      }
    },
    tags() {
      if (!this.device.tags) return [];
      return this.device.tags.map((tag) => tag.tagName);
    }
  },
  methods: {
    handleDelete() {
      this.$emit('delete', this.device.agentId)
    },
    handleCardClick() {
      this.$router.push({ path: '/agent-config', query: { agentId: this.device.agentId } });
    }
  },
}
</script>
<style lang="scss" scoped>
@import "@/views/studio.scss";

.studio-agent-card {
  @include studio-panel;
  border: 1px solid $studio-border;
  padding: 14px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 12px;

  &:hover { box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08); }
}

.card-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-avatar {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.card-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.card-title-block {
  min-width: 0;
  flex: 1;
}

.card-name {
  font-weight: 700;
  font-size: 15px;
  color: $studio-text;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}

.card-sub {
  font-size: 12px;
  color: $studio-text-sub;
  text-align: left;
}

.card-actions {
  display: flex;
  gap: 8px;

  .card-icon {
    width: 18px;
    height: 18px;
    cursor: pointer;
  }
}

.card-chips {
  display: flex;
  gap: 8px;

  .chip {
    flex: 1;
    background: $studio-soft-bg;
    border-radius: 10px;
    padding: 6px 8px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;

    .chip-label { font-size: 11px; color: $studio-text-sub; }
    .chip-label i { margin-right: 3px; font-size: 11px; }
    .chip-value { font-size: 12px; font-weight: 600; color: $studio-text; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  }
}

.card-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;

  .foot-badge { display: inline-flex; align-items: center; gap: 4px; background: $studio-soft-bg; border-radius: 999px; padding: 3px 10px; font-size: 12px; color: $studio-text-sub;
    .badge-ic { width: 13px; height: 13px; }
  }
  .foot-time { margin-left: auto; font-size: 11px; color: $studio-text-sub; }
}

.card-tags {
  font-size: 11px;
  color: $studio-text-sub;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}
</style>

<style>
.custom-tooltip {
  max-width: 400px;
  word-break: break-word;
}
</style>
