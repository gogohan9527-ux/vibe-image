<script setup lang="ts">
import { ref, watch } from 'vue';
import {
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElButton,
  ElMessage,
  ElAlert,
} from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import { useApiAuthStore } from '@/stores/useApiAuthStore';

const auth = useApiAuthStore();

const formRef = ref<FormInstance | null>(null);
const form = ref({ baseUrl: '', apiKey: '' });
const submitting = ref(false);

const rules: FormRules = {
  baseUrl: [
    { required: true, message: '请填写 base_url', trigger: 'blur' },
    {
      validator: (_r, value: string, cb) => {
        if (!value) return cb();
        try {
          new URL(value);
          cb();
        } catch {
          cb(new Error('base_url 不是合法 URL'));
        }
      },
      trigger: 'blur',
    },
  ],
  apiKey: [{ required: true, message: '请填写 api_key', trigger: 'blur' }],
};

watch(
  () => auth.needsPrompt,
  (next) => {
    if (next) {
      form.value.baseUrl = auth.serverBaseUrl || form.value.baseUrl;
      form.value.apiKey = '';
    }
  },
  { immediate: true },
);

async function submit(): Promise<void> {
  if (!formRef.value) return;
  const ok = await formRef.value.validate().catch(() => false);
  if (!ok) return;
  submitting.value = true;
  try {
    auth.setCredentials({
      apiKey: form.value.apiKey.trim(),
      baseUrl: form.value.baseUrl.trim(),
    });
    ElMessage.success('凭据已保存到内存（刷新页面后需重新填写）');
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <ElDialog
    :model-value="auth.needsPrompt"
    title="配置 API 凭据"
    width="480px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    align-center
    append-to-body
  >
    <ElAlert
      type="info"
      :closable="false"
      title="服务端未配置 api_key"
      description="请填写图片生成服务的 base_url 与 api_key。凭据仅保存在浏览器内存，刷新页面后需重新输入；提交时通过 RSA-OAEP 加密传输。"
      style="margin-bottom: 16px;"
    />
    <ElForm
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      @submit.prevent="submit"
    >
      <ElFormItem label="base_url" prop="baseUrl">
        <ElInput
          v-model="form.baseUrl"
          placeholder="https://momoapi.top/v1/images/generations"
        />
      </ElFormItem>
      <ElFormItem label="api_key" prop="apiKey">
        <ElInput
          v-model="form.apiKey"
          type="password"
          show-password
          placeholder="sk-..."
          autocomplete="off"
        />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton type="primary" :loading="submitting" @click="submit">
        保存并继续
      </ElButton>
    </template>
  </ElDialog>
</template>
