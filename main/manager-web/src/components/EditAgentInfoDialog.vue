<template>
  <el-dialog :title="$t('agentCard.editTitle')" :visible="visible" width="520px" :close-on-click-modal="false"
    custom-class="agent-edit-dialog" @close="handleClose" @open="handleOpen">
    <div class="edit-block">
      <div class="edit-label"><span class="edit-req">*</span>{{ $t('agentCard.name') }}</div>
      <el-input v-model="form.agentName" maxlength="64" :placeholder="$t('agentCard.namePlaceholder')" />
    </div>

    <div class="edit-block">
      <div class="edit-label">{{ $t('agentCard.description') }}</div>
      <el-input v-model="form.systemPrompt" type="textarea" :rows="9" resize="vertical"
        :placeholder="$t('agentCard.descriptionPlaceholder')" />
    </div>

    <div slot="footer" class="edit-foot">
      <div class="edit-btn edit-btn--ghost" @click="handleClose">{{ $t('agentCard.cancel') }}</div>
      <div class="edit-btn edit-btn--dark" :class="{ 'is-loading': saving }" @click="handleSave">
        {{ $t('agentCard.save') }}
      </div>
    </div>
  </el-dialog>
</template>

<script>
import Api from '@/apis/api';

export default {
  name: 'EditAgentInfoDialog',
  props: {
    visible: { type: Boolean, default: false },
    agent: { type: Object, default: null }
  },
  data() {
    return {
      form: { agentName: '', systemPrompt: '' },
      saving: false
    };
  },
  methods: {
    // Nạp lại form mỗi lần mở — tránh giữ giá trị của agent mở lần trước.
    handleOpen() {
      this.form.agentName = this.agent?.agentName || '';
      this.form.systemPrompt = this.agent?.systemPrompt || '';
      this.saving = false;
    },
    handleClose() {
      if (this.saving) return;
      this.$emit('update:visible', false);
    },
    handleSave() {
      if (this.saving) return;
      const agentName = (this.form.agentName || '').trim();
      if (!agentName) {
        this.$message.error(this.$t('agentCard.nameRequired'));
        return;
      }
      if (!this.agent?.agentId) return;

      this.saving = true;
      // Chỉ gửi 2 trường: backend chỉ ghi đè trường khác null nên TTS/LLM/Voice giữ nguyên.
      Api.agent.updateAgentConfig(this.agent.agentId, {
        agentName,
        systemPrompt: this.form.systemPrompt || ''
      }, ({ data }) => {
        this.saving = false;
        if (data?.code === 0) {
          this.$message.success(this.$t('message.success'));
          this.$emit('update:visible', false);
          this.$emit('saved');
        } else {
          this.$message.error(data?.msg || this.$t('message.error'));
        }
      });
    }
  }
};
</script>

<style lang="scss" scoped>
@import "@/views/studio.scss";

.edit-block {
  margin-bottom: 18px;
  text-align: left;

  &:last-of-type { margin-bottom: 0; }
}

.edit-label {
  font-size: 13px;
  font-weight: 500;
  color: $studio-text;
  margin-bottom: 8px;
}

.edit-req {
  color: #f56c6c;
  margin-right: 4px;
}

.edit-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.edit-btn {
  height: 36px;
  padding: 0 20px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;

  &.is-loading { opacity: 0.6; cursor: not-allowed; }
}

.edit-btn--ghost {
  border: 1px solid $studio-border;
  color: $studio-text;
  background: #fff;

  &:hover { background: $studio-soft-bg; }
}

.edit-btn--dark {
  background: #1a1a1c;
  color: #fff;

  &:hover { opacity: 0.88; }
}
</style>

<style>
.agent-edit-dialog {
  border-radius: 14px;
}
.agent-edit-dialog .el-dialog__body {
  padding: 20px 24px;
}
</style>
