<template>
  <div class="chat-history-section">
    <div class="history-card">
      <div class="chat-container">
        <!-- Sidebar: Session List -->
        <div class="session-list" @scroll="handleScroll">
          <div class="session-header">
            <span>{{ $t('chatHistory.dialogTitle') }}</span>
            <el-tag size="mini" type="info" effect="plain" class="count-tag">{{ sessions.length }}</el-tag>
          </div>
          
          <div v-for="session in sessions" 
               :key="session.sessionId" 
               class="session-item"
               :class="{ active: currentSessionId === session.sessionId }" 
               @click="selectSession(session)">
            <img :src="getUserAvatar(session.sessionId)" class="avatar" />
            <div class="session-info">
              <div class="session-id">Session #{{ session.sessionId.substring(0, 8) }}</div>
              <div class="session-time">{{ formatTime(session.createdAt) }}</div>
            </div>
          </div>
          
          <div v-if="loading" class="loading-state">
            <i class="el-icon-loading"></i>
          </div>
          <div v-if="!hasMore" class="no-more">{{ $t('chatHistory.noMoreRecords') }}</div>
        </div>

        <!-- Main: Chat Content -->
        <div class="chat-content">
          <div class="chat-header" v-if="currentSessionId">
            <div class="session-status">Recording Session</div>
            <div class="download-actions">
              <el-button size="mini" round icon="el-icon-download" @click="downloadCurrentSession">{{ $t('chatHistory.downloadCurrentSession') }}</el-button>
            </div>
          </div>

          <div v-if="currentSessionId" class="messages-area">
            <div v-for="(message, index) in messagesWithTime" :key="message.id">
              <!-- Time Divider -->
              <div v-if="message.type === 'time'" class="time-divider">
                <span>{{ message.content }}</span>
              </div>

              <!-- Message Bubble -->
              <div v-else class="msg-wrapper" :class="message.chatType === 1 ? 'user' : 'bot'">
                <div class="msg-meta" v-if="message.chatType !== 1">{{ agentName || 'Agent' }}</div>
                <div class="msg-meta" v-else>User</div>
                
                <div class="msg-bubble">
                  <div class="msg-text">
                    {{ extractContentFromString(message.content) }}
                  </div>
                  <div v-if="message.audioId" class="audio-player" @click="playAudio(message)">
                    <i :class="getAudioIconClass(message)"></i>
                    <span>Audio Log</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="empty-state">
            <i class="el-icon-chat-round"></i>
            <p>{{ $t('chatHistory.selectSession') }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { debounce } from '@/utils'
import Api from '@/apis/api';

export default {
  name: "ChatHistorySection",
  props: {
    agentId: { type: String, required: true },
    agentName: { type: String, default: "" }
  },
  data() {
    return {
      sessions: [],
      messages: [],
      currentSessionId: '',
      page: 1,
      limit: 20,
      loading: false,
      hasMore: true,
      scrollTimer: null,
      playingAudioId: null,
      audioElement: null
    };
  },
  computed: {
    messagesWithTime() {
      if (!this.messages || this.messages.length === 0) return [];
      const result = [];
      const TIME_INTERVAL = 60 * 1000;
      if (this.messages[0]) {
        result.push({ type: 'time', content: this.formatTime(this.messages[0].createdAt), id: `time-${Date.now()}-0` });
      }
      for (let i = 0; i < this.messages.length; i++) {
        const currentMessage = this.messages[i];
        result.push(currentMessage);
        if (i < this.messages.length - 1) {
          const currentTime = new Date(currentMessage.createdAt).getTime();
          const nextTime = new Date(this.messages[i + 1].createdAt).getTime();
          if (nextTime - currentTime > TIME_INTERVAL) {
            result.push({ type: 'time', content: this.formatTime(this.messages[i + 1].createdAt), id: `time-${Date.now()}-${i+1}` });
          }
        }
      }
      return result;
    }
  },
  mounted() {
    if (this.agentId) this.loadSessions();
  },
  methods: {
    extractContentFromString(content) {
      if (!content) return "";
      try {
        const jsonObj = JSON.parse(content);
        if (jsonObj && jsonObj.content) return jsonObj.content;
      } catch (e) {}
      return content;
    },
    loadSessions() {
      if (this.loading || (this.page > 1 && !this.hasMore)) return;
      this.loading = true;
      Api.agent.getAgentSessions(this.agentId, { page: this.page, limit: this.limit }, (res) => {
        if (res.data && res.data.data && res.data.data.list) {
          const list = res.data.data.list;
          this.hasMore = list.length === this.limit;
          this.sessions = [...this.sessions, ...list];
          this.page++;
          if (this.sessions.length > 0 && !this.currentSessionId) this.selectSession(this.sessions[0]);
        }
        this.loading = false;
      });
    },
    selectSession(session) {
      this.currentSessionId = session.sessionId;
      Api.agent.getAgentChatHistory(this.agentId, session.sessionId, (res) => {
        if (res.data && res.data.data) {
          this.messages = res.data.data;
        }
      });
    },
    handleScroll(e) {
      if (this.scrollTimer) clearTimeout(this.scrollTimer);
      this.scrollTimer = setTimeout(() => {
        const { scrollTop, scrollHeight, clientHeight } = e.target;
        if (scrollHeight - scrollTop <= clientHeight + 50) this.loadSessions();
      }, 200);
    },
    formatTime(timestamp) {
      const date = new Date(timestamp);
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const hours = date.getHours().toString().padStart(2, '0');
      const minutes = date.getMinutes().toString().padStart(2, '0');
      if (date >= today) return `${this.$t('chatHistory.today')} ${hours}:${minutes}`;
      return `${date.getFullYear()}-${(date.getMonth() + 1)}-${date.getDate()} ${hours}:${minutes}`;
    },
    getAudioIconClass(message) {
      return this.playingAudioId === message.audioId ? 'el-icon-loading' : 'el-icon-headset';
    },
    playAudio: debounce(function(message) {
      if (this.playingAudioId === message.audioId) {
        if (this.audioElement) { this.audioElement.pause(); this.audioElement = null; }
        this.playingAudioId = null;
        return;
      }
      if (this.audioElement) { this.audioElement.pause(); this.audioElement = null; }
      this.playingAudioId = message.audioId;
      Api.agent.getAudioId(message.audioId, (res) => {
        if (res.data && res.data.data) {
          this.audioElement = new Audio();
          this.audioElement.src = Api.getServiceUrl() + `/agent/play/${res.data.data}`;
          this.audioElement.onended = () => { this.playingAudioId = null; this.audioElement = null; };
          this.audioElement.play();
        }
      });
    }, 300),
    getUserAvatar(sessionId) {
      const numbers = sessionId.match(/\d+/g);
      if (!numbers) return require('@/assets/user-avatar1.png');
      const sum = numbers.reduce((acc, num) => acc + parseInt(num), 0);
      return require(`@/assets/user-avatar${(sum % 5) + 1}.png`);
    },
    downloadCurrentSession() {
      Api.agent.getDownloadUrl(this.agentId, this.currentSessionId, (res) => {
        if (res?.data?.data) window.open(`${Api.getServiceUrl()}/agent/chat-history/download/${res.data.data}/current`, '_blank');
      });
    }
  }
};
</script>

<style scoped lang="scss">
$ori-dark: #313133;
$ori-slate: #64748b;
$ori-green: #08c45b;
$ori-light-bg: #f8fafc;
$ori-border: #f1f5f9;

.chat-history-section { padding: 0; animation: fadeIn 0.4s ease; }

.history-card { 
  border-radius: 20px; border: 1px solid $ori-border; background: white;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); overflow: hidden;
}

.chat-container { 
  display: flex; height: 650px; 
  @media (max-width: 1024px) { height: 500px; }
  @media (max-width: 768px) { flex-direction: column; height: auto; }
}

.session-list { 
  width: 320px; border-right: 1px solid $ori-border; background: #fff; display: flex; flex-direction: column;
  @media (max-width: 768px) { width: 100%; height: 250px; border-right: none; border-bottom: 1px solid $ori-border; }
  
  .session-header { padding: 20px; border-bottom: 1px solid $ori-border; font-size: 14px; font-weight: 700; color: $ori-dark; display: flex; justify-content: space-between; align-items: center; }
}

.session-item { 
  padding: 16px 20px; cursor: pointer; border-bottom: 1px solid #f8fafc; transition: all 0.2s;
  display: flex; align-items: center; gap: 12px;
  &:hover { background: $ori-light-bg; }
  &.active { 
    background: #f0fdf4; 
    border-left: 4px solid $ori-green;
    .session-id { color: $ori-green; }
  }
}

.avatar { width: 36px; height: 36px; border-radius: 10px; background: $ori-light-bg; }

.session-info {
  display: flex; flex-direction: column; gap: 2px;
  .session-id { font-size: 13px; font-weight: 700; color: $ori-dark; }
  .session-time { font-size: 11px; color: $ori-slate; font-weight: 500; }
}

.chat-content { 
  flex: 1; display: flex; flex-direction: column; background: #fff;
  .chat-header { padding: 16px 24px; border-bottom: 1px solid $ori-border; display: flex; align-items: center; justify-content: space-between; }
  .session-status { font-size: 12px; font-weight: 600; color: $ori-green; display: flex; align-items: center; gap: 6px; &::before { content: ''; width: 8px; height: 8px; background: $ori-green; border-radius: 50%; } }
}

.messages-area { 
  flex: 1; padding: 24px; overflow-y: auto; display: flex; flex-direction: column; gap: 24px; background: #fdfdfd; 
}

.time-divider { 
  text-align: center; margin: 8px 0; 
  span { font-size: 11px; font-weight: 700; color: $ori-slate; background: $ori-light-bg; padding: 4px 12px; border-radius: 20px; text-transform: uppercase; letter-spacing: 0.1em; }
}

.msg-wrapper {
  display: flex; flex-direction: column; gap: 6px;
  &.bot { align-items: flex-start; }
  &.user { align-items: flex-end; }
}

.msg-bubble { 
  padding: 14px 18px; border-radius: 16px; font-size: 14px; line-height: 1.6; max-width: 80%; position: relative;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.msg-wrapper.bot .msg-bubble { 
  background: white; color: $ori-dark; border: 1px solid $ori-border; border-bottom-left-radius: 4px; 
}
.msg-wrapper.user .msg-bubble { 
  background: $ori-green; color: white; border-bottom-right-radius: 4px;
}

.audio-player { 
  margin-top: 10px; padding: 8px 12px; background: rgba(0,0,0,0.03); border-radius: 10px; cursor: pointer; display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600;
  &:hover { background: rgba(0,0,0,0.06); }
  i { font-size: 16px; color: $ori-green; }
}
.user .audio-player { background: rgba(255,255,255,0.1); i { color: white; } }

.msg-meta { font-size: 10px; color: $ori-slate; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding: 0 4px; }

.empty-state { 
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: $ori-slate; gap: 16px;
  i { font-size: 48px; opacity: 0.2; }
  p { font-size: 14px; font-weight: 500; }
}

.loading-state { text-align: center; padding: 20px; color: $ori-green; font-size: 20px; }
.no-more { text-align: center; padding: 20px; font-size: 12px; color: $ori-slate; }

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
