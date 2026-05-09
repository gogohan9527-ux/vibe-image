<script setup lang="ts">
import { computed, watch } from 'vue';
import { ElMessage, ElOption, ElSelect } from 'element-plus';
import { storeToRefs } from 'pinia';
import { ApiError } from '@/api/client';
import { useProviderStore } from '@/stores/useProviderStore';

export interface PickerValue {
  provider_id: string;
  key_id: string;
  model: string;
}

const props = defineProps<{ modelValue: PickerValue }>();
const emit = defineEmits<{ (e: 'update:modelValue', v: PickerValue): void }>();

const store = useProviderStore();
const { providers, keysByProvider, modelsByProviderKey } = storeToRefs(store);

function update(patch: Partial<PickerValue>): void {
  emit('update:modelValue', { ...props.modelValue, ...patch });
}

const currentProvider = computed(() =>
  providers.value.find((p) => p.id === props.modelValue.provider_id) ?? null,
);

const availableKeys = computed(() =>
  props.modelValue.provider_id ? keysByProvider.value[props.modelValue.provider_id] ?? [] : [],
);

const availableModels = computed(() => {
  const { provider_id, key_id } = props.modelValue;
  if (!provider_id || !key_id) return [];
  return modelsByProviderKey.value[`${provider_id}::${key_id}`] ?? [];
});

// When provider changes: pick its default_key_id (if usable), else first key, else clear.
watch(
  () => props.modelValue.provider_id,
  async (pid) => {
    if (!pid) {
      update({ key_id: '', model: '' });
      return;
    }
    let keys = keysByProvider.value[pid] ?? [];
    if (keys.length === 0) {
      try {
        keys = await store.loadKeys(pid);
      } catch {
        // Will surface as empty in the UI
      }
    }
    if (keys.length === 0) {
      update({ key_id: '', model: '' });
      return;
    }
    const defaultKid = currentProvider.value?.config?.default_key_id;
    const next = (defaultKid && keys.some((k) => k.id === defaultKid))
      ? defaultKid
      : keys[0].id;
    if (next !== props.modelValue.key_id) {
      update({ key_id: next, model: '' });
    }
  },
);

// When key changes: ensure models are loaded, pick default_model if present, else first.
watch(
  () => [props.modelValue.provider_id, props.modelValue.key_id] as const,
  async ([pid, kid]) => {
    if (!pid || !kid) return;
    const cacheKey = `${pid}::${kid}`;
    let models = modelsByProviderKey.value[cacheKey] ?? [];
    if (models.length === 0) {
      try {
        models = await store.loadModels(pid, kid);
      } catch (err) {
        if (err instanceof ApiError) ElMessage.warning(err.message);
        return;
      }
    }
    const provider = providers.value.find((p) => p.id === pid);
    const defaultModel = provider?.config?.default_model;
    if (props.modelValue.model && models.some((m) => m.id === props.modelValue.model)) {
      return;
    }
    let chosen = '';
    if (defaultModel && models.some((m) => m.id === defaultModel)) chosen = defaultModel;
    else if (models.length > 0) chosen = models[0].id;
    if (chosen !== props.modelValue.model) {
      update({ model: chosen });
    }
  },
);
</script>

<template>
  <div class="picker">
    <div class="picker-row">
      <label class="picker-label">Provider</label>
      <ElSelect
        :model-value="props.modelValue.provider_id"
        placeholder="选择 Provider"
        @update:model-value="(v: string) => update({ provider_id: v })"
      >
        <ElOption
          v-for="p in providers"
          :key="p.id"
          :label="p.display_name"
          :value="p.id"
        />
      </ElSelect>
    </div>
    <div class="picker-row">
      <label class="picker-label">Key</label>
      <ElSelect
        :model-value="props.modelValue.key_id"
        :disabled="!props.modelValue.provider_id"
        :placeholder="availableKeys.length === 0 ? '该 Provider 暂无 Key' : '选择 Key'"
        @update:model-value="(v: string) => update({ key_id: v, model: '' })"
      >
        <ElOption
          v-for="k in availableKeys"
          :key="k.id"
          :label="k.label"
          :value="k.id"
        />
      </ElSelect>
    </div>
    <div class="picker-row">
      <label class="picker-label">Model</label>
      <ElSelect
        :model-value="props.modelValue.model"
        :disabled="!props.modelValue.key_id"
        filterable
        allow-create
        placeholder="选择或输入 Model ID"
        @update:model-value="(v: string) => update({ model: v })"
      >
        <ElOption
          v-for="m in availableModels"
          :key="m.id"
          :label="m.id"
          :value="m.id"
        />
      </ElSelect>
    </div>
  </div>
</template>

<style scoped>
.picker {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.picker-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.picker-label {
  display: inline-block;
  width: 64px;
  font-size: 12px;
  color: var(--vi-text-muted);
}

.picker-row :deep(.el-select) {
  flex: 1;
}
</style>
