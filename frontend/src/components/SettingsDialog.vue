<script setup lang="ts">
import { ref, watch } from 'vue';
import {
  ElDialog,
  ElForm,
  ElFormItem,
  ElInputNumber,
  ElButton,
  ElMessage,
} from 'element-plus';
import type { FormInstance, FormItemRule } from 'element-plus';
import { ApiError, getSettings, putSettings } from '@/api/client';
import type { Settings } from '@/types/api';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>();

const formRef = ref<FormInstance | null>(null);
const loading = ref(false);
const submitting = ref(false);

const settings = ref<Settings>({
  concurrency: 3,
  queue_cap: 100,
  max_concurrency: 32,
  max_queue_size: 10000,
});

const fieldErrors = ref<{ concurrency?: string; queue_cap?: string }>({});

async function load(): Promise<void> {
  loading.value = true;
  try {
    settings.value = await getSettings();
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message);
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) {
      fieldErrors.value = {};
      void load();
    }
  },
);

const concurrencyRules: FormItemRule[] = [
  { required: true, message: '请输入并发数', trigger: 'blur' },
];
const queueRules: FormItemRule[] = [
  { required: true, message: '请输入队列上限', trigger: 'blur' },
];

function close(): void {
  emit('update:open', false);
}

async function submit(): Promise<void> {
  fieldErrors.value = {};
  submitting.value = true;
  try {
    const next = await putSettings({
      concurrency: settings.value.concurrency,
      queue_cap: settings.value.queue_cap,
    });
    settings.value = next;
    ElMessage.success('设置已更新');
    close();
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 400 && err.body.code === 'out_of_range' && err.body.field) {
        fieldErrors.value[err.body.field] = '该值超出允许范围';
        ElMessage.error(`字段 "${err.body.field}" 超出允许范围`);
      } else {
        ElMessage.error(err.message);
      }
    } else {
      ElMessage.error('保存失败');
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <ElDialog
    :model-value="open"
    title="设置"
    width="440"
    :before-close="(done) => { close(); done(); }"
    align-center
  >
    <ElForm
      ref="formRef"
      :model="settings"
      v-loading="loading"
      label-position="top"
    >
      <ElFormItem
        label="最大并发数"
        :rules="concurrencyRules"
        :error="fieldErrors.concurrency"
      >
        <ElInputNumber
          v-model="settings.concurrency"
          :min="1"
          :max="settings.max_concurrency"
          style="width: 100%"
        />
        <div class="hint">允许同时运行的任务数（1 - {{ settings.max_concurrency }}）</div>
      </ElFormItem>

      <ElFormItem
        label="队列上限"
        :rules="queueRules"
        :error="fieldErrors.queue_cap"
      >
        <ElInputNumber
          v-model="settings.queue_cap"
          :min="1"
          :max="settings.max_queue_size"
          style="width: 100%"
        />
        <div class="hint">队列容量上限（1 - {{ settings.max_queue_size }}）</div>
      </ElFormItem>
    </ElForm>

    <template #footer>
      <ElButton @click="close">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="submit">保存</ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.hint {
  font-size: 12px;
  color: var(--vi-text-faint);
  margin-top: 4px;
}
</style>
