<script setup lang="ts">
import { onMounted, ref } from 'vue';
import {
  ElButton,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElPopconfirm,
  ElTable,
  ElTableColumn,
  ElTooltip,
} from 'element-plus';
import { ApiError, createPrompt, deletePrompt, listPrompts, updatePrompt } from '@/api/client';
import type { PromptItem } from '@/types/api';

const templates = ref<PromptItem[]>([]);
const loading = ref(false);

const dialogVisible = ref(false);
const dialogMode = ref<'create' | 'edit'>('create');
const editingId = ref('');
const formName = ref('');
const formContent = ref('');
const formSubmitting = ref(false);

async function fetchTemplates(): Promise<void> {
  loading.value = true;
  try {
    const res = await listPrompts();
    templates.value = res.prompts;
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void fetchTemplates();
});

function openCreateDialog(): void {
  dialogMode.value = 'create';
  editingId.value = '';
  formName.value = '';
  formContent.value = '';
  dialogVisible.value = true;
}

function openEditDialog(row: PromptItem): void {
  dialogMode.value = 'edit';
  editingId.value = row.id;
  formName.value = row.title;
  formContent.value = row.prompt;
  dialogVisible.value = true;
}

async function submitDialog(): Promise<void> {
  const name = formName.value.trim();
  const content = formContent.value.trim();
  if (!name) {
    ElMessage.warning('模板名称不能为空');
    return;
  }
  if (!content) {
    ElMessage.warning('模板提示词不能为空');
    return;
  }
  formSubmitting.value = true;
  try {
    if (dialogMode.value === 'create') {
      await createPrompt({ title: name, prompt: content });
      ElMessage.success('模板已创建');
    } else {
      await updatePrompt(editingId.value, { title: name, prompt: content });
      ElMessage.success('模板已更新');
    }
    dialogVisible.value = false;
    await fetchTemplates();
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message);
  } finally {
    formSubmitting.value = false;
  }
}

async function handleDelete(row: PromptItem): Promise<void> {
  try {
    await deletePrompt(row.id);
    ElMessage.success('模板已删除');
    await fetchTemplates();
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message);
  }
}

function formatPreview(content: string): string {
  return content.length > 60 ? content.slice(0, 60) + '…' : content;
}

function formatDate(dt: string): string {
  return new Date(dt).toLocaleString('zh-CN', { hour12: false });
}
</script>

<template>
  <div class="templates-view">
    <header class="view-head">
      <h1>模板配置</h1>
      <ElButton type="primary" @click="openCreateDialog">新建模板</ElButton>
    </header>

    <ElTable :data="templates" v-loading="loading" stripe class="templates-table">
      <ElTableColumn prop="title" label="名称" width="200" />
      <ElTableColumn label="提示词预览" min-width="300">
        <template #default="{ row }">
          <ElTooltip :content="row.prompt" placement="top" :show-after="300" effect="light">
            <span class="content-preview">{{ formatPreview(row.prompt) }}</span>
          </ElTooltip>
        </template>
      </ElTableColumn>
      <ElTableColumn label="创建时间" width="180">
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </ElTableColumn>
      <ElTableColumn label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <ElButton size="small" @click="openEditDialog(row)">编辑</ElButton>
          <ElTooltip
            :content="row.id === 'sample' ? '示例模板不可删除' : ''"
            :disabled="row.id !== 'sample'"
            placement="top"
          >
            <span>
              <ElPopconfirm
                title="确定删除该模板吗？"
                confirm-button-text="删除"
                cancel-button-text="取消"
                @confirm="handleDelete(row)"
              >
                <template #reference>
                  <ElButton
                    size="small"
                    type="danger"
                    :disabled="row.id === 'sample'"
                  >删除</ElButton>
                </template>
              </ElPopconfirm>
            </span>
          </ElTooltip>
        </template>
      </ElTableColumn>
    </ElTable>

    <ElDialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新建模板' : '编辑模板'"
      width="560px"
      :close-on-click-modal="false"
    >
      <ElForm label-position="top">
        <ElFormItem label="名称" required>
          <ElInput
            v-model="formName"
            maxlength="60"
            show-word-limit
            placeholder="请输入模板名称"
          />
        </ElFormItem>
        <ElFormItem label="提示词" required>
          <ElInput
            v-model="formContent"
            type="textarea"
            :rows="6"
            maxlength="2000"
            show-word-limit
            placeholder="请输入模板提示词"
            resize="none"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="formSubmitting" @click="submitDialog">
          {{ dialogMode === 'create' ? '创建' : '保存' }}
        </ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.templates-view {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.view-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.view-head h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--vi-text);
}

.templates-table {
  width: 100%;
}

.content-preview {
  font-size: 13px;
  color: var(--vi-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
  max-width: 280px;
}
</style>
