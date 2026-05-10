<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import {
  ElInput,
  ElSelect,
  ElOption,
  ElTable,
  ElTableColumn,
  ElPagination,
  ElTag,
  ElIcon,
  ElButton,
  ElMessage,
  ElTooltip,
} from 'element-plus';
import { Search, Download, RefreshLeft, Delete, CopyDocument, WarningFilled } from '@element-plus/icons-vue';
import { ElMessageBox } from 'element-plus';
import { ApiError, createTask, deleteHistory, listHistory } from '@/api/client';
import PreviewImage from '@/components/PreviewImage.vue';
import type { CreateTaskRequest, HistoryStatusFilter, TaskItem } from '@/types/api';
import { useTaskStore } from '@/stores/useTaskStore';
import { formatDateTime } from '@/utils/format';

const search = ref('');
const status = ref<HistoryStatusFilter>('all');
const page = ref(1);
const pageSize = ref(10);
const total = ref(0);
const items = ref<TaskItem[]>([]);
const loading = ref(false);

const store = useTaskStore();

let debounceTimer: number | null = null;

async function fetchHistory(): Promise<void> {
  loading.value = true;
  try {
    const res = await listHistory({
      q: search.value.trim() || undefined,
      status: status.value,
      page: page.value,
      page_size: pageSize.value,
    });
    items.value = res.items;
    total.value = res.total;
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message);
  } finally {
    loading.value = false;
  }
}

function debouncedFetch(): void {
  if (debounceTimer != null) window.clearTimeout(debounceTimer);
  debounceTimer = window.setTimeout(() => {
    page.value = 1;
    void fetchHistory();
  }, 300);
}

watch(search, () => debouncedFetch());
watch(status, () => {
  page.value = 1;
  void fetchHistory();
});
watch(page, () => void fetchHistory());
watch(pageSize, () => {
  page.value = 1;
  void fetchHistory();
});

onMounted(() => void fetchHistory());

function statusMeta(s: TaskItem['status']): { label: string; type: 'success' | 'danger' | 'info' | 'warning' | 'primary' } {
  switch (s) {
    case 'succeeded':
      return { label: '成功', type: 'success' };
    case 'failed':
      return { label: '失败', type: 'danger' };
    case 'cancelled':
      return { label: '已取消', type: 'info' };
    default:
      return { label: s, type: 'info' };
  }
}

function onDownload(row: TaskItem): void {
  if (!row.image_url) {
    ElMessage.warning('该任务没有可下载的图片');
    return;
  }
  const a = document.createElement('a');
  a.href = row.image_url;
  a.download = `vibe-${row.id}.${row.format}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function narrowQuality(q: string): CreateTaskRequest['quality'] {
  return q === 'low' || q === 'medium' || q === 'high' || q === 'auto' ? q : null;
}

async function onRegenerate(row: TaskItem): Promise<void> {
  if (!row.provider_id || !row.key_id) {
    ElMessage.warning('该任务为旧版记录（无 provider/key 绑定），请到新建任务抽屉手动重新发起');
    return;
  }
  try {
    const res = await createTask({
      prompt: row.prompt,
      prompt_template_id: row.prompt_template_id,
      provider_id: row.provider_id,
      key_id: row.key_id,
      model: row.model,
      size: row.size,
      quality: narrowQuality(row.quality),
      format: row.format,
      n: 1,
    });
    for (const t of res.tasks) store.upsert(t);
    ElMessage.success('已重新生成');
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 429 && err.body.code === 'queue_full') {
        ElMessage.error(`队列已满 (${err.body.queue_size}/${err.body.cap})，请稍后再试`);
      } else {
        ElMessage.error(err.message);
      }
    }
  }
}

async function onDelete(row: TaskItem): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '确认删除该历史记录？图片文件也会被删除。',
      '删除确认',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      },
    );
  } catch {
    // user cancelled
    return;
  }
  try {
    await deleteHistory(row.id);
    ElMessage.success('已删除');
    await fetchHistory();
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 404 && err.body.code === 'task_not_found') {
        ElMessage.warning('记录已不存在，已刷新列表');
        await fetchHistory();
      } else if (err.status === 409 && err.body.code === 'task_active') {
        ElMessage.error('任务仍在进行中，请先在任务列表取消后再删除');
      } else {
        ElMessage.error(err.message ?? '删除失败');
      }
    } else {
      ElMessage.error((err as Error)?.message ?? '删除失败');
    }
  }
}

const totalForPager = computed(() => total.value);

async function copyError(msg: string | null): Promise<void> {
  if (!msg) return;
  try {
    await navigator.clipboard.writeText(msg);
    ElMessage.success('已复制');
  } catch {
    ElMessage.error('复制失败');
  }
}

function isLegacy(row: TaskItem): boolean {
  return row.provider_id == null;
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1 class="page-title">历史记录</h1>
        <p class="page-sub">查看已完成的图片生成记录</p>
      </div>
      <div class="filters">
        <ElInput
          v-model="search"
          placeholder="搜索提示词内容"
          clearable
          class="search-input"
        >
          <template #prefix>
            <ElIcon><Search /></ElIcon>
          </template>
        </ElInput>
        <ElSelect v-model="status" class="status-select">
          <ElOption label="全部状态" value="all" />
          <ElOption label="成功" value="succeeded" />
          <ElOption label="失败" value="failed" />
          <ElOption label="已取消" value="cancelled" />
        </ElSelect>
      </div>
    </header>

    <div class="table-wrap">
      <ElTable :data="items" v-loading="loading" stripe style="width: 100%" row-key="id">
        <ElTableColumn label="输入图" width="64" align="center">
          <template #default="{ row }: { row: TaskItem }">
            <div v-if="row.input_image_url" class="input-thumb">
              <PreviewImage :src="row.input_image_url" alt="input" />
            </div>
            <span v-else class="muted">—</span>
          </template>
        </ElTableColumn>

        <ElTableColumn label="缩略图" width="120">
          <template #default="{ row }: { row: TaskItem }">
            <div class="thumb">
              <PreviewImage :src="row.image_url" alt="thumbnail" />
            </div>
          </template>
        </ElTableColumn>

        <ElTableColumn label="提示词" min-width="240">
          <template #default="{ row }: { row: TaskItem }">
            <ElTooltip :content="row.prompt" placement="top" :show-after="400">
              <p class="cell-prompt">{{ row.title || row.prompt }}</p>
            </ElTooltip>
          </template>
        </ElTableColumn>

        <ElTableColumn label="模型版本" width="180">
          <template #default="{ row }: { row: TaskItem }">
            <span class="model-cell">{{ row.model }}</span>
            <ElTag
              v-if="isLegacy(row)"
              size="small"
              type="info"
              effect="plain"
              round
              class="legacy-tag"
            >
              legacy
            </ElTag>
          </template>
        </ElTableColumn>

        <ElTableColumn label="尺寸" width="120">
          <template #default="{ row }: { row: TaskItem }">
            {{ row.size }}
          </template>
        </ElTableColumn>

        <ElTableColumn label="生成时间" width="170">
          <template #default="{ row }: { row: TaskItem }">
            {{ formatDateTime(row.finished_at ?? row.created_at) }}
          </template>
        </ElTableColumn>

        <ElTableColumn label="状态" width="100">
          <template #default="{ row }: { row: TaskItem }">
            <ElTag size="small" :type="statusMeta(row.status).type" effect="light" round>
              {{ statusMeta(row.status).label }}
            </ElTag>
          </template>
        </ElTableColumn>

        <ElTableColumn label="错误信息" width="220">
          <template #default="{ row }: { row: TaskItem }">
            <div v-if="row.status === 'failed'" class="err-cell">
              <ElIcon class="err-icon" color="#ef4444"><WarningFilled /></ElIcon>
              <ElTooltip
                v-if="row.error_message"
                :content="row.error_message"
                placement="top"
                :show-after="300"
              >
                <span class="err-text">{{ row.error_message }}</span>
              </ElTooltip>
              <span v-else class="err-empty">无错误描述</span>
              <button
                v-if="row.error_message"
                type="button"
                class="err-copy"
                title="复制错误信息"
                @click="copyError(row.error_message)"
              >
                <ElIcon><CopyDocument /></ElIcon>
              </button>
            </div>
            <span v-else class="err-dash">—</span>
          </template>
        </ElTableColumn>

        <ElTableColumn label="操作" width="240" fixed="right">
          <template #default="{ row }: { row: TaskItem }">
            <div class="row-actions">
              <ElButton link type="primary" :disabled="!row.image_url" @click="onDownload(row)">
                <ElIcon><Download /></ElIcon>下载
              </ElButton>
              <ElButton link type="danger" @click="onDelete(row)">
                <ElIcon><Delete /></ElIcon>删除
              </ElButton>
              <ElButton link type="primary" @click="onRegenerate(row)">
                <ElIcon><RefreshLeft /></ElIcon>重新生成
              </ElButton>
            </div>
          </template>
        </ElTableColumn>
      </ElTable>
    </div>

    <div class="pagination">
      <ElPagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="totalForPager"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
        background
      />
    </div>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1200px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
}

.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
}

.page-sub {
  margin: 4px 0 0;
  color: var(--vi-text-muted);
  font-size: 13px;
}

.filters {
  display: flex;
  gap: 8px;
}

.search-input {
  width: 240px;
}

.status-select {
  width: 140px;
}

.table-wrap {
  background: var(--vi-card-bg);
  border: 1px solid var(--vi-border);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: var(--vi-shadow);
}

.thumb {
  width: 96px;
  height: 60px;
  border-radius: 6px;
  overflow: hidden;
  background: #f1f3f8;
  display: grid;
  place-items: center;
}

.input-thumb {
  width: 40px;
  height: 40px;
  border-radius: 6px;
  overflow: hidden;
  background: #f1f3f8;
  border: 1px solid var(--vi-border);
  margin: 0 auto;
}

.muted {
  color: var(--vi-text-faint);
  font-size: 13px;
}

.cell-prompt {
  margin: 0;
  font-size: 13px;
  color: var(--vi-text);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.row-actions {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 4px 0 24px;
}

.model-cell {
  font-size: 13px;
}

.legacy-tag {
  margin-left: 6px;
}

.err-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #ef4444;
  min-width: 0;
}

.err-icon {
  flex-shrink: 0;
}

.err-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.err-empty {
  flex: 1;
  color: var(--vi-text-faint);
}

.err-copy {
  flex-shrink: 0;
  border: 0;
  background: transparent;
  color: var(--vi-text-muted);
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  display: inline-flex;
}

.err-copy:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
}

.err-dash {
  color: var(--vi-text-faint);
  font-size: 13px;
}

/* Mobile: allow table to scroll horizontally */
@media (max-width: 767px) {
  .table-wrap {
    overflow-x: auto;
  }

  .filters {
    flex-wrap: wrap;
  }

  .search-input {
    width: 100%;
    flex: 1 1 100%;
  }

  .status-select {
    width: 120px;
  }

  .pagination {
    justify-content: center;
  }
}
</style>
