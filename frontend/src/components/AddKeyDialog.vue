<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import {
  ElAlert,
  ElButton,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
} from 'element-plus';
import { ApiError } from '@/api/client';
import { useProviderStore } from '@/stores/useProviderStore';

interface Props {
  providerId: string;
  open: boolean;
}

const props = defineProps<Props>();
const emit = defineEmits<{ (e: 'close'): void }>();

const store = useProviderStore();

const provider = computed(() =>
  store.providers.find((p) => p.id === props.providerId) ?? null,
);

const label = ref<string>('default');
// Keyed by credential_field name; populated from provider's credential_fields.
const credValues = ref<Record<string, string>>({});
const submitting = ref(false);

function resetForm(): void {
  label.value = 'default';
  const next: Record<string, string> = {};
  if (provider.value) {
    for (const f of provider.value.credential_fields) next[f.name] = '';
  }
  credValues.value = next;
}

watch(
  () => [props.open, provider.value],
  () => {
    if (props.open) resetForm();
  },
  { immediate: true },
);

function close(): void {
  emit('close');
}

async function submit(): Promise<void> {
  if (!provider.value) return;
  if (!label.value.trim()) {
    ElMessage.warning('请填写 Label');
    return;
  }
  const missing: string[] = [];
  for (const f of provider.value.credential_fields) {
    if (f.required && !credValues.value[f.name]?.trim()) {
      missing.push(f.label);
    }
  }
  if (missing.length > 0) {
    ElMessage.warning(`请填写: ${missing.join(', ')}`);
    return;
  }
  submitting.value = true;
  try {
    const plain: Record<string, string> = {};
    for (const f of provider.value.credential_fields) {
      const v = credValues.value[f.name]?.trim() ?? '';
      if (v) plain[f.name] = v;
    }
    const result = await store.addKey(provider.value.id, label.value.trim(), plain);
    if (result.refreshError) {
      ElMessage.warning(`Key 已保存,但拉取模型失败: ${result.refreshError}`);
    } else {
      ElMessage.success(`Key 已保存,模型已就绪 (${result.models.length} 个)`);
    }
    close();
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.body.code === 'invalid_credentials' && err.body.missing_fields?.length) {
        ElMessage.error(`必填字段缺失: ${err.body.missing_fields.join(', ')}`);
      } else {
        ElMessage.error(err.message);
      }
    } else {
      ElMessage.error('添加 Key 失败');
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <ElDialog
    :model-value="open"
    :title="provider ? `添加 ${provider.display_name} Key` : '添加 Key'"
    width="480px"
    align-center
    append-to-body
    :before-close="(done) => { close(); done(); }"
  >
    <ElAlert
      type="info"
      :closable="false"
      title="凭据安全"
      description="字段会通过 RSA-OAEP 加密传输,后端 AES-256-GCM 加密入库 (normal 模式) 或仅入内存 (demo)。明文不会出现在日志或响应中。"
      style="margin-bottom: 16px;"
    />
    <ElForm v-if="provider" label-position="top" @submit.prevent="submit">
      <ElFormItem label="Label" required>
        <ElInput v-model="label" placeholder="便于区分多把 Key,如 personal / team" />
      </ElFormItem>
      <ElFormItem
        v-for="field in provider.credential_fields"
        :key="field.name"
        :label="field.label"
        :required="field.required"
      >
        <ElInput
          v-model="credValues[field.name]"
          :type="field.secret ? 'password' : 'text'"
          :show-password="field.secret"
          autocomplete="off"
        />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="close">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="submit">保存并拉取模型</ElButton>
    </template>
  </ElDialog>
</template>
