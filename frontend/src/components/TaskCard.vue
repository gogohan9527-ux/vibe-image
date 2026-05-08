<script setup lang="ts">
import { computed } from 'vue';
import { ElIcon, ElProgress, ElTag, ElTooltip, ElMessage, ElMessageBox } from 'element-plus';
import { Picture, VideoPause, VideoPlay, Delete, Loading } from '@element-plus/icons-vue';
import type { TaskItem } from '@/types/api';
import { cancelTask, ApiError } from '@/api/client';
import { formatDateTime, formatEta } from '@/utils/format';

interface Props {
  task: TaskItem;
  index: number;
  averageDurationMs: number | null;
}

const props = defineProps<Props>();

const statusMeta = computed(() => {
  switch (props.task.status) {
    case 'queued':
      return { label: '排队中', type: 'info' as const };
    case 'running':
      return { label: '生成中', type: 'primary' as const };
    case 'cancelling':
      return { label: '取消中', type: 'warning' as const };
    case 'succeeded':
      return { label: '已完成', type: 'success' as const };
    case 'failed':
      return { label: '失败', type: 'danger' as const };
    case 'cancelled':
      return { label: '已取消', type: 'info' as const };
    default:
      return { label: props.task.status, type: 'info' as const };
  }
});

const progressColor = computed(() => {
  if (props.task.status === 'failed') return '#ef4444';
  if (props.task.status === 'cancelling') return '#f59e0b';
  return '#3b6cf5';
});

const etaText = computed(() => {
  const t = props.task;
  if (t.status === 'succeeded') return '已完成';
  if (t.status === 'failed') return '已失败';
  if (t.status === 'cancelled' || t.status === 'cancelling') return '取消中';
  if (props.averageDurationMs == null) return '—';
  const remainingFrac = Math.max(0, (100 - t.progress) / 100);
  const remainingSec = (props.averageDurationMs / 1000) * remainingFrac;
  return formatEta(remainingSec);
});

const isPaused = computed(() => props.task.status === 'cancelling');

async function onCancelOrPause(): Promise<void> {
  if (props.task.status === 'cancelling') return;
  try {
    await cancelTask(props.task.id);
  } catch (err) {
    if (err instanceof ApiError) {
      ElMessage.error(err.message);
    } else {
      ElMessage.error('取消任务失败');
    }
  }
}

async function onDelete(): Promise<void> {
  try {
    await ElMessageBox.confirm('确定要删除这个任务吗？', '删除任务', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
  } catch {
    return;
  }
  try {
    await cancelTask(props.task.id);
  } catch (err) {
    if (err instanceof ApiError && err.status !== 409) {
      ElMessage.error(err.message);
    }
  }
}

const avatarHue = computed(() => {
  // Stable color per index for the placeholder card icon
  const palette = ['#4f7df9', '#22c55e', '#a855f7', '#f59e0b', '#ec4899', '#06b6d4'];
  return palette[(props.index - 1) % palette.length];
});
</script>

<template>
  <article class="task-card">
    <div class="task-icon" :style="{ background: avatarHue }">
      <ElIcon :size="22" color="#fff"><Picture /></ElIcon>
    </div>

    <div class="task-body">
      <div class="task-head">
        <span class="task-title">任务 {{ index }}</span>
        <ElTag size="small" :type="statusMeta.type" effect="light" round>
          {{ statusMeta.label }}
        </ElTag>
      </div>

      <ElTooltip :content="task.prompt" placement="top" :show-after="400">
        <p class="task-prompt">{{ task.title || task.prompt }}</p>
      </ElTooltip>

      <div class="task-meta">创建时间：{{ formatDateTime(task.created_at) }}</div>

      <div class="task-progress">
        <ElProgress
          :percentage="task.progress"
          :stroke-width="6"
          :color="progressColor"
          :show-text="false"
        />
        <span class="progress-text">{{ task.progress }}%</span>
      </div>
    </div>

    <div class="task-thumb">
      <img v-if="task.image_url" :src="task.image_url" alt="thumbnail" />
      <div v-else class="thumb-placeholder">
        <ElIcon :size="22" color="#cbd5e1"><Picture /></ElIcon>
      </div>
    </div>

    <div class="task-side">
      <div class="task-eta">
        <div class="eta-label">预计剩余</div>
        <div class="eta-value">{{ etaText }}</div>
      </div>
      <div class="task-actions">
        <button
          type="button"
          class="icon-btn"
          :disabled="isPaused"
          :title="isPaused ? '取消中…' : '暂停 / 取消'"
          @click="onCancelOrPause"
        >
          <ElIcon><Loading v-if="isPaused" /><VideoPause v-else-if="task.status === 'running'" /><VideoPlay v-else /></ElIcon>
        </button>
        <button type="button" class="icon-btn danger" title="删除" @click="onDelete">
          <ElIcon><Delete /></ElIcon>
        </button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.task-card {
  display: grid;
  grid-template-columns: 56px 1fr 132px 110px;
  gap: 18px;
  align-items: center;
  background: var(--vi-card-bg);
  border: 1px solid var(--vi-border);
  border-radius: 12px;
  padding: 16px 18px;
  box-shadow: var(--vi-shadow);
}

.task-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.task-body {
  min-width: 0;
}

.task-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.task-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--vi-text);
}

.task-prompt {
  margin: 0 0 6px;
  color: var(--vi-text-muted);
  font-size: 13px;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.task-meta {
  font-size: 12px;
  color: var(--vi-text-faint);
  margin-bottom: 8px;
}

.task-progress {
  display: flex;
  align-items: center;
  gap: 10px;
}

.task-progress :deep(.el-progress) {
  flex: 1;
}

.progress-text {
  font-size: 12px;
  color: var(--vi-text-muted);
  width: 38px;
  text-align: right;
}

.task-thumb {
  width: 132px;
  height: 80px;
  border-radius: 8px;
  overflow: hidden;
  background: #f1f3f8;
  display: grid;
  place-items: center;
}

.task-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-placeholder {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
}

.task-side {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-end;
}

.task-eta {
  text-align: right;
}

.eta-label {
  font-size: 12px;
  color: var(--vi-text-faint);
}

.eta-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--vi-text);
  font-variant-numeric: tabular-nums;
}

.task-actions {
  display: flex;
  gap: 6px;
}

.icon-btn {
  width: 30px;
  height: 30px;
  border-radius: 6px;
  border: 1px solid var(--vi-border);
  background: #fff;
  color: var(--vi-text-muted);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: all 0.15s;
}

.icon-btn:hover:not(:disabled) {
  border-color: var(--vi-primary);
  color: var(--vi-primary);
}

.icon-btn.danger:hover:not(:disabled) {
  border-color: var(--vi-danger);
  color: var(--vi-danger);
}

.icon-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
