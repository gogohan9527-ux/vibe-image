<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import {
  ElButton,
  ElCard,
  ElIcon,
  ElEmpty,
  ElMessage,
  ElMessageBox,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTooltip,
} from 'element-plus';
import { Plus, RefreshLeft, Setting, Delete } from '@element-plus/icons-vue';
import { storeToRefs } from 'pinia';
import { ApiError } from '@/api/client';
import { useProviderStore } from '@/stores/useProviderStore';
import type {
  ProviderKeyMeta,
  ProviderModelMeta,
  ProviderSummary,
} from '@/types/api';
import { formatDateTime } from '@/utils/format';
import ProviderConfigDialog from '@/components/ProviderConfigDialog.vue';
import AddKeyDialog from '@/components/AddKeyDialog.vue';

const store = useProviderStore();
const { providers, keysByProvider, modelsByProviderKey, loaded } = storeToRefs(store);

const refreshing = ref<Record<string, boolean>>({});
const configOpen = ref<string | null>(null);
const addKeyOpen = ref<string | null>(null);

onMounted(async () => {
  if (!loaded.value) {
    try {
      await store.bootstrap();
    } catch (err) {
      if (err instanceof ApiError) ElMessage.error(err.message);
      else ElMessage.error('加载 Provider 列表失败');
    }
  }
});

function keysFor(p: ProviderSummary): ProviderKeyMeta[] {
  return keysByProvider.value[p.id] ?? [];
}

function selectedKeyForModels(p: ProviderSummary): ProviderKeyMeta | null {
  const ks = keysFor(p);
  if (ks.length === 0) return null;
  const defaultKid = p.config?.default_key_id;
  if (defaultKid) {
    const found = ks.find((k) => k.id === defaultKid);
    if (found) return found;
  }
  return ks[0];
}

function modelsFor(p: ProviderSummary): ProviderModelMeta[] {
  const k = selectedKeyForModels(p);
  if (!k) return [];
  return modelsByProviderKey.value[`${p.id}::${k.id}`] ?? [];
}

async function onRefreshModels(p: ProviderSummary): Promise<void> {
  const k = selectedKeyForModels(p);
  if (!k) {
    ElMessage.warning('请先添加一个 Key');
    return;
  }
  refreshing.value = { ...refreshing.value, [p.id]: true };
  try {
    const models = await store.refreshModels(p.id, k.id);
    ElMessage.success(`已刷新模型列表（${models.length} 个）`);
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message);
    else ElMessage.error('刷新失败');
  } finally {
    refreshing.value = { ...refreshing.value, [p.id]: false };
  }
}

async function onDeleteKey(p: ProviderSummary, k: ProviderKeyMeta): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除 Key "${k.label}"？该 Key 缓存的 Models 也会一并清除。`,
      '删除 Key',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    );
  } catch {
    return;
  }
  try {
    await store.deleteKey(p.id, k.id);
    ElMessage.success('Key 已删除');
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message);
    else ElMessage.error('删除失败');
  }
}

async function onSetDefaultKey(p: ProviderSummary, k: ProviderKeyMeta): Promise<void> {
  try {
    await store.updateConfig(p.id, { default_key_id: k.id });
    ElMessage.success(`已设为默认 Key`);
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message);
    else ElMessage.error('设置默认 Key 失败');
  }
}

function isDefaultKey(p: ProviderSummary, k: ProviderKeyMeta): boolean {
  return p.config?.default_key_id === k.id;
}

const providerCards = computed<ProviderSummary[]>(() => providers.value);
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1 class="page-title">插件配置</h1>
        <p class="page-sub">管理图片生成 Provider 的配置。</p>
      </div>
    </header>

    <ElEmpty v-if="loaded && providerCards.length === 0" description="暂无可用 Provider" />

    <section v-else class="provider-list">
      <ElCard v-for="p in providerCards" :key="p.id" class="provider-card" shadow="never">
        <template #header>
          <div class="card-head">
            <div class="card-head-left">
              <h2 class="provider-name">{{ p.display_name }}</h2>
              <ElTag size="small" round effect="light">已配置 {{ p.key_count }} 把 Key</ElTag>
            </div>
            <div class="card-head-actions">
              <ElButton
                size="small"
                :icon="Setting"
                @click="configOpen = p.id"
              >
                编辑配置
              </ElButton>
            </div>
          </div>
        </template>

        <div class="meta-grid">
          <div class="meta-item">
            <div class="meta-label">Base URL</div>
            <div class="meta-value mono">{{ p.config?.base_url || p.default_base_url }}</div>
          </div>
          <div class="meta-item">
            <div class="meta-label">默认 Model</div>
            <div class="meta-value mono">{{ p.config?.default_model || '—' }}</div>
          </div>
          <div class="meta-item">
            <div class="meta-label">默认 Key</div>
            <div class="meta-value mono">
              <span v-if="p.config?.default_key_id">
                {{
                  keysFor(p).find((k) => k.id === p.config?.default_key_id)?.label
                    || p.config?.default_key_id
                }}
              </span>
              <span v-else>—</span>
            </div>
          </div>
        </div>

        <div class="section">
          <div class="section-head">
            <h3>Keys</h3>
            <ElButton size="small" type="primary" :icon="Plus" @click="addKeyOpen = p.id">
              添加 Key
            </ElButton>
          </div>
          <ElTable v-if="keysFor(p).length > 0" :data="keysFor(p)" stripe size="small">
            <ElTableColumn label="Label" prop="label" min-width="160">
              <template #default="{ row }: { row: ProviderKeyMeta }">
                <span>{{ row.label }}</span>
                <ElTag
                  v-if="isDefaultKey(p, row)"
                  size="small"
                  type="success"
                  effect="light"
                  round
                  style="margin-left: 6px;"
                >
                  默认
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn label="创建时间" width="180">
              <template #default="{ row }: { row: ProviderKeyMeta }">
                {{ formatDateTime(row.created_at) }}
              </template>
            </ElTableColumn>
            <ElTableColumn label="操作" width="200" align="right">
              <template #default="{ row }: { row: ProviderKeyMeta }">
                <ElButton
                  v-if="!isDefaultKey(p, row)"
                  link
                  type="primary"
                  size="small"
                  @click="onSetDefaultKey(p, row)"
                >
                  设为默认
                </ElButton>
                <ElButton link type="danger" size="small" @click="onDeleteKey(p, row)">
                  <ElIcon><Delete /></ElIcon>删除
                </ElButton>
              </template>
            </ElTableColumn>
          </ElTable>
          <div v-else class="empty-hint">尚未添加 Key,点击"添加 Key"开始配置。</div>
        </div>

        <div class="section">
          <div class="section-head">
            <h3>
              Models
              <span v-if="selectedKeyForModels(p)" class="model-key-hint">
                (当前 Key: {{ selectedKeyForModels(p)?.label }})
              </span>
            </h3>
            <ElButton
              size="small"
              :icon="RefreshLeft"
              :loading="refreshing[p.id]"
              :disabled="!selectedKeyForModels(p)"
              @click="onRefreshModels(p)"
            >
              刷新
            </ElButton>
          </div>
          <div v-if="modelsFor(p).length > 0" class="model-chips">
            <ElTooltip
              v-for="m in modelsFor(p)"
              :key="m.id"
              :content="`缓存于 ${formatDateTime(m.fetched_at)}`"
              placement="top"
              :show-after="400"
            >
              <ElTag size="small" class="model-chip" effect="plain" round>
                {{ m.id }}
              </ElTag>
            </ElTooltip>
          </div>
          <div v-else class="empty-hint">
            无模型缓存。添加 Key 后会自动拉取,也可以手动点击"刷新"。
          </div>
        </div>
      </ElCard>
    </section>

    <ProviderConfigDialog
      v-if="configOpen"
      :provider-id="configOpen"
      :open="!!configOpen"
      @close="configOpen = null"
    />
    <AddKeyDialog
      v-if="addKeyOpen"
      :provider-id="addKeyOpen"
      :open="!!addKeyOpen"
      @close="addKeyOpen = null"
    />
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1080px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 12px;
}

.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: var(--vi-text);
}

.page-sub {
  margin: 4px 0 0;
  color: var(--vi-text-muted);
  font-size: 13px;
}

.provider-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.provider-card :deep(.el-card__header) {
  padding: 14px 18px;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card-head-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.provider-name {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--vi-text);
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px 24px;
  padding-bottom: 14px;
  border-bottom: 1px dashed var(--vi-border);
}

.meta-item {
  min-width: 0;
}

.meta-label {
  font-size: 12px;
  color: var(--vi-text-faint);
  margin-bottom: 4px;
}

.meta-value {
  font-size: 13px;
  color: var(--vi-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mono {
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}

.section {
  padding-top: 14px;
}

.section + .section {
  border-top: 1px dashed var(--vi-border);
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.section-head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--vi-text);
}

.model-key-hint {
  font-size: 12px;
  color: var(--vi-text-muted);
  font-weight: 400;
  margin-left: 6px;
}

.empty-hint {
  font-size: 13px;
  color: var(--vi-text-muted);
  padding: 8px 0;
}

.model-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.model-chip {
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
