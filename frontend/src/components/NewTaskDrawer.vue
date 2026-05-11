<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useIsMobile } from '@/composables/useMobile';
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
  ElEmpty,
  ElImage,
  ElTooltip,
  ElUpload,
} from 'element-plus';
import type { UploadFile, UploadRawFile } from 'element-plus';
import { Delete, Picture } from '@element-plus/icons-vue';
import { ApiError, createTask, deletePrompt, listPrompts, uploadTempImage } from '@/api/client';
import { useTaskStore } from '@/stores/useTaskStore';
import { useProviderStore } from '@/stores/useProviderStore';
import ProviderPicker, { type PickerValue } from '@/components/ProviderPicker.vue';
import type { CreateTaskRequest, PromptItem } from '@/types/api';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>();

const taskStore = useTaskStore();
const providerStore = useProviderStore();
const router = useRouter();
const { isMobile } = useIsMobile();

type Quality = 'low' | 'medium' | 'high' | 'auto';

const prompt = ref('');
const selectedTemplateId = ref<string | null>(null);
const quality = ref<Quality>('low');
const ratio = ref<'1:1' | '16:9' | '9:16' | '4:3'>('1:1');
const size = ref('1024x1024');
const count = ref(1);
const priority = ref(false);
const saveAsTemplate = ref(false);

const picker = ref<PickerValue>({ provider_id: '', key_id: '', model: '' });

const submitting = ref(false);
const templates = ref<PromptItem[]>([]);
const templatesLoading = ref(false);

// img2img reference image (added 2026-05-09 II).
interface InputImageState { path: string; url: string; name: string }
const inputImages = ref<InputImageState[]>([]);
const uploadingCount = ref(0);
const uploading = computed(() => uploadingCount.value > 0);

const selectedProvider = computed(() =>
  picker.value.provider_id
    ? providerStore.providers.find((p) => p.id === picker.value.provider_id) ?? null
    : null,
);
const supportsImage = computed<boolean>(() => selectedProvider.value?.supports_image_input ?? false);

// If user switches to a provider that doesn't support image input, drop any
// previously selected reference image so we don't accidentally submit it.
watch(supportsImage, (next) => {
  if (!next && inputImages.value.length > 0) inputImages.value = [];
});

async function handleFileSelected(file: UploadFile): Promise<void> {
  const raw = file.raw as UploadRawFile | undefined;
  if (!raw) return;
  // Element Plus's <el-upload> calls on-change for status transitions too; we
  // only want the moment a fresh file is picked.
  if (file.status !== 'ready' && file.status !== undefined) return;
  uploadingCount.value += 1;
  try {
    const res = await uploadTempImage(raw);
    if (!inputImages.value.some((img) => img.path === res.input_image_path)) {
      inputImages.value.push({ path: res.input_image_path, url: res.url, name: raw.name });
    }
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.body.code === 'upload_too_large') {
        ElMessage.error('文件超过大小上限（10 MiB）');
      } else if (err.body.code === 'invalid_upload') {
        ElMessage.error('仅支持 PNG / JPEG / WEBP 图片');
      } else {
        ElMessage.error(err.message || '上传失败');
      }
    } else {
      ElMessage.error('上传失败');
    }
  } finally {
    uploadingCount.value = Math.max(0, uploadingCount.value - 1);
  }
}

function removeInputImage(path: string): void {
  inputImages.value = inputImages.value.filter((img) => img.path !== path);
}

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
  if (!sizeOptions.value.includes(size.value)) {
    size.value = sizeOptions.value[0];
  }
});

// "No provider has any key" empty state — drives the empty-state CTA.
const hasUsableProvider = computed<boolean>(() =>
  providerStore.providers.some((p) => (providerStore.keysByProvider[p.id] ?? []).length > 0),
);

// Default-pick a usable provider when the drawer first opens, so the picker
// is meaningful without making the user click around.
watch(
  () => props.open,
  async (next) => {
    if (!next) return;
    void loadTemplates();
    if (!providerStore.loaded) {
      try {
        await providerStore.bootstrap();
      } catch {
        // Surfaced via the empty state below
      }
    }
    const hasKeys = (pid: string): boolean =>
      (providerStore.keysByProvider[pid] ?? []).length > 0;
    const currentValid = picker.value.provider_id && hasKeys(picker.value.provider_id);
    if (!currentValid) {
      // Prefer a provider that has both default_key_id and default_model
      // configured; fall back to default_key_id only; finally any provider
      // with keys. This matches the auto-fill flow in ProviderPicker.
      const fullyConfigured = providerStore.providers.find(
        (p) => hasKeys(p.id) && p.config?.default_key_id && p.config?.default_model,
      );
      const keyOnly = providerStore.providers.find(
        (p) => hasKeys(p.id) && p.config?.default_key_id,
      );
      const anyWithKeys = providerStore.providers.find((p) => hasKeys(p.id));
      const chosen = fullyConfigured ?? keyOnly ?? anyWithKeys;
      if (chosen) picker.value = { provider_id: chosen.id, key_id: '', model: '' };
    }
  },
  { immediate: true },
);

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
  inputImages.value = [];
  // Clear picker so the next drawer open re-resolves provider defaults
  // (default_key_id / default_model) instead of reusing last submission.
  picker.value = { provider_id: '', key_id: '', model: '' };
}

function goToProviders(): void {
  close();
  void router.push('/providers');
}

const submitDisabled = computed<boolean>(
  () =>
    !hasUsableProvider.value
    || !picker.value.provider_id
    || !picker.value.key_id
    || !picker.value.model
    || prompt.value.trim().length === 0,
);

async function submit(): Promise<void> {
  const text = prompt.value.trim();
  if (text.length === 0) {
    ElMessage.warning('请填写提示词');
    return;
  }
  if (!picker.value.provider_id || !picker.value.key_id || !picker.value.model) {
    ElMessage.warning('请选择 Provider / Key / Model');
    return;
  }
  submitting.value = true;
  try {
    const payload: CreateTaskRequest = {
      prompt: text,
      prompt_template_id: selectedTemplateId.value,
      provider_id: picker.value.provider_id,
      key_id: picker.value.key_id,
      model: picker.value.model,
      quality: quality.value,
      size: size.value,
      n: count.value,
      priority: priority.value,
      save_as_template: saveAsTemplate.value || undefined,
      input_image_paths: inputImages.value.length > 0
        ? inputImages.value.map((img) => img.path)
        : undefined,
    };

    const res = await createTask(payload);
    for (const t of res.tasks) taskStore.upsert(t);
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
        ElMessage.error('凭据失效（后端可能已重启），请到 /providers 重新添加 Key');
      } else if (err.body.code === 'provider_not_configured' || err.body.code === 'key_not_found') {
        ElMessage.error(`${err.message}（请到 /providers 配置）`);
      } else if (err.body.code === 'provider_capability_unsupported') {
        ElMessage.error('当前 Provider 不支持图生图，请切换 Provider 或移除参考图');
      } else if (err.body.code === 'input_image_not_found') {
        ElMessage.error('参考图文件已失效，请重新上传');
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
    :direction="isMobile ? 'btt' : 'rtl'"
    :size="isMobile ? '92%' : '480px'"
    :with-header="false"
    :before-close="(done) => { close(); done(); }"
    class="new-task-drawer"
  >
    <div class="drawer-content">
      <header class="drawer-head">
        <h2>新建任务</h2>
        <p>填写提示词与参数，提交后即进入队列</p>
      </header>

      <div v-if="!hasUsableProvider" class="empty-wrap">
        <ElEmpty description="尚未配置任何 Provider Key">
          <ElButton type="primary" @click="goToProviders">去 /providers 配置插件</ElButton>
        </ElEmpty>
      </div>

      <div v-else class="form">
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
          <label>参考图（可选）</label>
          <ElTooltip
            :content="supportsImage ? '' : '当前 Provider 不支持图生图'"
            :disabled="supportsImage"
            placement="top"
          >
            <div class="upload-wrap">
              <ElUpload
                :show-file-list="false"
                :auto-upload="false"
                :disabled="!supportsImage || uploading"
                accept="image/png,image/jpeg,image/webp"
                drag
                multiple
                :on-change="handleFileSelected"
                class="ref-uploader"
              >
                <div class="upload-inner">
                  <ElIcon :size="22" color="#94a3b8"><Picture /></ElIcon>
                  <p class="upload-hint">
                    {{ uploading ? '上传中…' : '点击或拖入图片（PNG / JPEG / WEBP，≤ 10 MiB）' }}
                  </p>
                </div>
              </ElUpload>
              <div v-if="inputImages.length > 0" class="ref-list">
                <div v-for="img in inputImages" :key="img.path" class="ref-preview">
                  <ElImage
                    :src="img.url"
                    :preview-src-list="inputImages.map((x) => x.url)"
                    fit="cover"
                    preview-teleported
                    hide-on-click-modal
                    class="ref-thumb"
                  />
                  <div class="ref-meta">
                    <span class="ref-name" :title="img.name">{{ img.name }}</span>
                    <ElButton text type="danger" size="small" @click="removeInputImage(img.path)">
                      移除
                    </ElButton>
                  </div>
                </div>
              </div>
            </div>
          </ElTooltip>
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
          <label>2. 模型选择</label>
          <ProviderPicker v-model="picker" />
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
        <ElButton
          type="primary"
          :loading="submitting"
          :disabled="submitDisabled"
          @click="submit"
        >
          创建任务
        </ElButton>
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

.empty-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
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

.upload-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ref-uploader :deep(.el-upload-dragger) {
  padding: 14px;
}

.upload-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.upload-hint {
  margin: 0;
  font-size: 12px;
  color: var(--vi-text-muted);
}

.ref-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.ref-preview {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  border: 1px solid var(--vi-border);
  border-radius: 8px;
  background: #f9fafb;
}

.ref-thumb {
  width: 96px;
  height: 96px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
}

.ref-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.ref-name {
  font-size: 12px;
  color: var(--vi-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Mobile bottom-sheet tweaks */
@media (max-width: 767px) {
  .drawer-content {
    border-radius: 16px 16px 0 0;
    overflow: hidden;
  }

  .drawer-head {
    padding: 16px 16px 10px;
  }

  /* Visual drag handle */
  .drawer-head::before {
    content: '';
    display: block;
    width: 36px;
    height: 4px;
    background: #d1d5db;
    border-radius: 2px;
    margin: 0 auto 12px;
  }

  .form {
    padding: 12px 16px;
  }

  .drawer-foot {
    padding: 12px 16px;
    padding-bottom: calc(12px + env(safe-area-inset-bottom));
  }

  .ratio-group {
    flex-wrap: wrap;
  }
}
</style>
