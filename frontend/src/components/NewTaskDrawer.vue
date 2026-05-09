<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import {
  ElDrawer,
  ElInput,
  ElSelect,
  ElOption,
  ElRadioGroup,
  ElRadioButton,
  ElInputNumber,
  ElCheckbox,
  ElButton,
  ElMessage,
  ElIcon,
} from 'element-plus';
import { Delete } from '@element-plus/icons-vue';
import { ApiError, createTask, deletePrompt, listPrompts } from '@/api/client';
import { useTaskStore } from '@/stores/useTaskStore';
import { useApiAuthStore } from '@/stores/useApiAuthStore';
import { encryptApiKey, resetPublicKeyCache } from '@/services/crypto';
import type { CreateTaskRequest, PromptItem } from '@/types/api';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>();

const store = useTaskStore();
const auth = useApiAuthStore();

type Quality = 'low' | 'medium' | 'high' | 'auto';

const prompt = ref('');
const selectedTemplateId = ref<string | null>(null);
const model = ref('t8-/gpt-image-2');
const quality = ref<Quality>('low');
const ratio = ref<'1:1' | '16:9' | '9:16' | '4:3'>('1:1');
const size = ref('1024x1024');
const count = ref(1);
const priority = ref(false);
const saveAsTemplate = ref(false);

const submitting = ref(false);
const templates = ref<PromptItem[]>([]);
const templatesLoading = ref(false);

const sizeOptions = computed<string[]>(() => {
  switch (ratio.value) {
    case '1:1':
      return ['512x512', '768x768', '1024x1024', '1536x1536'];
    case '16:9':
      return ['1280x720', '1920x1080'];
    case '9:16':
      return ['720x1280', '1080x1920'];
    case '4:3':
      return ['1024x768', '1280x960'];
    default:
      return ['1024x1024'];
  }
});

watch(ratio, () => {
  // Snap to first available size for the chosen ratio if current isn't valid
  if (!sizeOptions.value.includes(size.value)) {
    size.value = sizeOptions.value[0];
  }
});

async function loadTemplates(): Promise<void> {
  templatesLoading.value = true;
  try {
    const res = await listPrompts();
    templates.value = res.prompts;
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message);
  } finally {
    templatesLoading.value = false;
  }
}

watch(
  () => props.open,
  (next) => {
    if (next) void loadTemplates();
  },
  { immediate: true },
);

watch(selectedTemplateId, (id) => {
  if (!id) return;
  const t = templates.value.find((x) => x.id === id);
  if (t) prompt.value = t.prompt;
});

async function onDeleteTemplate(id: string): Promise<void> {
  try {
    await deletePrompt(id);
    templates.value = templates.value.filter((t) => t.id !== id);
    if (selectedTemplateId.value === id) selectedTemplateId.value = null;
    ElMessage.success('模板已删除');
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message);
  }
}

function close(): void {
  emit('update:open', false);
}

function reset(): void {
  prompt.value = '';
  selectedTemplateId.value = null;
  quality.value = 'low';
  ratio.value = '1:1';
  size.value = '1024x1024';
  count.value = 1;
  priority.value = false;
  saveAsTemplate.value = false;
}

async function submit(): Promise<void> {
  const text = prompt.value.trim();
  if (text.length === 0) {
    ElMessage.warning('请填写提示词');
    return;
  }
  submitting.value = true;
  try {
    const payload: CreateTaskRequest = {
      prompt: text,
      prompt_template_id: selectedTemplateId.value,
      model: model.value,
      quality: quality.value,
      size: size.value,
      n: count.value,
      priority: priority.value,
      save_as_template: saveAsTemplate.value || undefined,
    };

    if (auth.hasUserCredentials && auth.apiKey && auth.baseUrl) {
      try {
        payload.encrypted_api_key = await encryptApiKey(auth.apiKey);
        payload.base_url = auth.baseUrl;
      } catch (err) {
        // Public key may have rotated (backend restart) — drop cache and retry once.
        resetPublicKeyCache();
        payload.encrypted_api_key = await encryptApiKey(auth.apiKey);
        payload.base_url = auth.baseUrl;
      }
    }

    const res = await createTask(payload);
    for (const t of res.tasks) store.upsert(t);
    ElMessage.success(`已创建 ${res.tasks.length} 个任务`);
    reset();
    close();
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 429 && err.body.code === 'queue_full') {
        const cap = err.body.cap ?? 0;
        const qs = err.body.queue_size ?? 0;
        ElMessage.error(`队列已满 (${qs}/${cap})，请减少数量或稍后再试`);
      } else if (err.body.code === 'credential_decrypt_failed') {
        // Backend restarted (rotated keypair) — clear in-memory creds and re-prompt.
        resetPublicKeyCache();
        auth.clear();
        ElMessage.error('凭据失效（后端可能已重启），请重新填写');
      } else if (err.body.code === 'api_key_missing') {
        ElMessage.error('api_key 未配置，请先填写凭据');
      } else {
        ElMessage.error(err.message);
      }
    } else {
      ElMessage.error('创建任务失败');
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <ElDrawer
    :model-value="open"
    direction="rtl"
    size="480px"
    :with-header="false"
    :before-close="(done) => { close(); done(); }"
    class="new-task-drawer"
  >
    <div class="drawer-content">
      <header class="drawer-head">
        <h2>新建任务</h2>
        <p>填写提示词与参数，提交后即进入队列</p>
      </header>

      <div class="form">
        <div class="field">
          <label>1. 提示词</label>
          <ElInput
            v-model="prompt"
            type="textarea"
            :rows="6"
            placeholder="请输入您的提示词，描述您想生成的图片"
            resize="none"
          />
        </div>

        <div class="field">
          <label>选择模板</label>
          <ElSelect
            v-model="selectedTemplateId"
            placeholder="从已保存的模板中选择"
            clearable
            filterable
            :loading="templatesLoading"
          >
            <ElOption
              v-for="t in templates"
              :key="t.id"
              :label="t.title"
              :value="t.id"
            >
              <div class="option-row">
                <span class="option-name">{{ t.title }}</span>
                <button
                  v-if="t.id !== 'sample'"
                  type="button"
                  class="option-delete"
                  title="删除模板"
                  @click.stop="onDeleteTemplate(t.id)"
                >
                  <ElIcon><Delete /></ElIcon>
                </button>
              </div>
            </ElOption>
          </ElSelect>
        </div>

        <div class="field">
          <label>2. 模型版本</label>
          <ElSelect v-model="model">
            <ElOption label="t8-/gpt-image-2" value="t8-/gpt-image-2" />
          </ElSelect>
        </div>

        <div class="field">
          <label>3. 图片参数</label>
          <div class="quality-row">
            <span class="sub-label">质量</span>
            <ElSelect v-model="quality">
              <ElOption label="低 (low)" value="low" />
              <ElOption label="中 (medium)" value="medium" />
              <ElOption label="高 (high)" value="high" />
              <ElOption label="自动 (auto)" value="auto" />
            </ElSelect>
          </div>
          <div class="ratio-group">
            <span class="sub-label">比例</span>
            <ElRadioGroup v-model="ratio" size="default">
              <ElRadioButton label="1:1" value="1:1" />
              <ElRadioButton label="16:9" value="16:9" />
              <ElRadioButton label="9:16" value="9:16" />
              <ElRadioButton label="4:3" value="4:3" />
            </ElRadioGroup>
          </div>
          <div class="size-row">
            <span class="sub-label">尺寸</span>
            <ElSelect v-model="size">
              <ElOption v-for="opt in sizeOptions" :key="opt" :label="opt" :value="opt" />
            </ElSelect>
          </div>
        </div>

        <div class="field">
          <label>4. 生成数量</label>
          <div class="count-row">
            <ElInputNumber v-model="count" :min="1" :max="10" />
            <ElCheckbox v-model="priority">优先（插入队列前列）</ElCheckbox>
          </div>
        </div>

        <div class="field">
          <ElCheckbox v-model="saveAsTemplate">将本次提示词保存为模板</ElCheckbox>
        </div>
      </div>

      <footer class="drawer-foot">
        <ElButton @click="close">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="submit">创建任务</ElButton>
      </footer>
    </div>
  </ElDrawer>
</template>

<style scoped>
.drawer-content {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.drawer-head {
  padding: 20px 24px 12px;
  border-bottom: 1px solid var(--vi-border);
}

.drawer-head h2 {
  margin: 0 0 4px;
  font-size: 18px;
  color: var(--vi-text);
}

.drawer-head p {
  margin: 0;
  color: var(--vi-text-muted);
  font-size: 12px;
}

.form {
  padding: 16px 24px;
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field > label {
  font-size: 13px;
  font-weight: 600;
  color: var(--vi-text);
}

.sub-label {
  display: inline-block;
  width: 40px;
  font-size: 12px;
  color: var(--vi-text-muted);
}

.ratio-group,
.size-row,
.quality-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.size-row :deep(.el-select),
.quality-row :deep(.el-select) {
  flex: 1;
}

.count-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.option-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.option-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.option-delete {
  border: 0;
  background: transparent;
  color: var(--vi-text-faint);
  cursor: pointer;
  padding: 2px 4px;
}

.option-delete:hover {
  color: var(--vi-danger);
}

.drawer-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 24px;
  border-top: 1px solid var(--vi-border);
  background: #fff;
}
</style>
