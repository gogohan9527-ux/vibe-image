<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import {
  ElButton,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElOption,
  ElSelect,
} from 'element-plus';
import { storeToRefs } from 'pinia';
import { ApiError } from '@/api/client';
import { useProviderStore } from '@/stores/useProviderStore';

interface Props {
  providerId: string;
  open: boolean;
}

const props = defineProps<Props>();
const emit = defineEmits<{ (e: 'close'): void }>();

const store = useProviderStore();
const { providers, keysByProvider, modelsByProviderKey } = storeToRefs(store);

const provider = computed(() => providers.value.find((p) => p.id === props.providerId) ?? null);
const keys = computed(() => keysByProvider.value[props.providerId] ?? []);

const form = ref<{ base_url: string; default_model: string; default_key_id: string }>({
  base_url: '',
  default_model: '',
  default_key_id: '',
});
const submitting = ref(false);
const modelsLoading = ref(false);
// Tracks whether we're past the dialog-open hydration step. Used to suppress the
// "clear default_model when key changes" rule on the initial sync.
const initialized = ref(false);

// Models available for the currently-selected default_key_id only. Empty when
// no key is chosen — the select stays usable via allow-create for manual input.
const modelsForSelectedKey = computed<string[]>(() => {
  const kid = form.value.default_key_id;
  if (!kid) return [];
  const list = modelsByProviderKey.value[`${props.providerId}::${kid}`] ?? [];
  return list.map((m) => m.id);
});

watch(
  () => [props.open, provider.value] as const,
  () => {
    if (!props.open || !provider.value) {
      initialized.value = false;
      return;
    }
    initialized.value = false;
    form.value.base_url = provider.value.config?.base_url ?? provider.value.default_base_url;
    form.value.default_key_id = provider.value.config?.default_key_id ?? '';
    form.value.default_model = provider.value.config?.default_model ?? '';
    // Allow the key watcher below to run once for hydration without clearing
    // the just-restored default_model.
    void Promise.resolve().then(() => {
      initialized.value = true;
    });
  },
  { immediate: true },
);

// When default_key_id changes: lazy-load that key's models, then drop any
// default_model that isn't valid for the new key. Skipped during initial sync.
watch(
  () => form.value.default_key_id,
  async (kid) => {
    if (!props.open) return;
    if (!kid) {
      if (initialized.value) form.value.default_model = '';
      return;
    }
    const cacheKey = `${props.providerId}::${kid}`;
    let models = modelsByProviderKey.value[cacheKey] ?? [];
    if (models.length === 0) {
      modelsLoading.value = true;
      try {
        models = await store.loadModels(props.providerId, kid);
      } catch (err) {
        if (err instanceof ApiError) ElMessage.warning(err.message);
      } finally {
        modelsLoading.value = false;
      }
    }
    if (initialized.value && form.value.default_model
      && !models.some((m) => m.id === form.value.default_model)) {
      form.value.default_model = '';
    }
  },
);

function close(): void {
  emit('close');
}

async function submit(): Promise<void> {
  if (!provider.value) return;
  if (!form.value.base_url.trim()) {
    ElMessage.warning('Base URL 不能为空');
    return;
  }
  try {
    new URL(form.value.base_url.trim());
  } catch {
    ElMessage.warning('Base URL 不是合法 URL');
    return;
  }
  submitting.value = true;
  try {
    const body: { base_url?: string; default_model?: string; default_key_id?: string } = {
      base_url: form.value.base_url.trim(),
    };
    if (form.value.default_model.trim()) {
      body.default_model = form.value.default_model.trim();
    }
    if (form.value.default_key_id) {
      body.default_key_id = form.value.default_key_id;
    }
    await store.updateConfig(provider.value.id, body);
    ElMessage.success('配置已更新');
    close();
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message);
    else ElMessage.error('更新配置失败');
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <ElDialog
    :model-value="open"
    :title="provider ? `编辑 ${provider.display_name} 配置` : '编辑配置'"
    width="520px"
    align-center
    append-to-body
    :before-close="(done) => { close(); done(); }"
  >
    <ElForm v-if="provider" :model="form" label-position="top" @submit.prevent="submit">
      <ElFormItem label="Base URL">
        <ElInput
          v-model="form.base_url"
          :placeholder="provider.default_base_url"
        />
      </ElFormItem>
      <ElFormItem label="默认 Key">
        <ElSelect v-model="form.default_key_id" clearable placeholder="选择默认使用的 Key">
          <ElOption v-for="k in keys" :key="k.id" :label="k.label" :value="k.id" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="默认 Model">
        <ElSelect
          v-model="form.default_model"
          filterable
          allow-create
          clearable
          :loading="modelsLoading"
          :disabled="!form.default_key_id"
          :placeholder="form.default_key_id ? '选择或输入 Model ID' : '请先选择默认 Key'"
        >
          <ElOption v-for="m in modelsForSelectedKey" :key="m" :label="m" :value="m" />
        </ElSelect>
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="close">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="submit">保存</ElButton>
    </template>
  </ElDialog>
</template>
