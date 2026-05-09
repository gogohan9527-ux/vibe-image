// Provider / Key / Model state. Replaces the old useApiAuthStore.
//
// Bootstrap fans out a few requests in parallel and eagerly hydrates keys +
// models for any provider that already has a default_key_id, so the
// new-task drawer can show a working three-level picker without extra clicks.

import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import {
  addProviderKey,
  deleteProviderKey,
  getConfigStatus,
  listProviderKeys,
  listProviderModels,
  listProviders,
  refreshProviderModels,
  updateProviderConfig,
} from '@/api/client';
import { encryptObject } from '@/services/crypto';
import type {
  ProviderConfigOut,
  ProviderKeyMeta,
  ProviderModelMeta,
  ProviderSummary,
  UpdateProviderConfigRequest,
} from '@/types/api';

function modelCacheKey(providerId: string, keyId: string): string {
  return `${providerId}::${keyId}`;
}

export const useProviderStore = defineStore('providers', () => {
  const providers = ref<ProviderSummary[]>([]);
  const keysByProvider = ref<Record<string, ProviderKeyMeta[]>>({});
  const modelsByProviderKey = ref<Record<string, ProviderModelMeta[]>>({});
  const mode = ref<'normal' | 'demo' | null>(null);
  const anyConfigured = ref<boolean>(false);
  const loaded = ref<boolean>(false);

  function providerById(id: string): ProviderSummary | undefined {
    return providers.value.find((p) => p.id === id);
  }

  async function loadKeys(providerId: string): Promise<ProviderKeyMeta[]> {
    const res = await listProviderKeys(providerId);
    keysByProvider.value = { ...keysByProvider.value, [providerId]: res.keys };
    return res.keys;
  }

  async function loadModels(
    providerId: string,
    keyId: string,
  ): Promise<ProviderModelMeta[]> {
    const res = await listProviderModels(providerId, keyId);
    modelsByProviderKey.value = {
      ...modelsByProviderKey.value,
      [modelCacheKey(providerId, keyId)]: res.models,
    };
    return res.models;
  }

  async function refreshModels(
    providerId: string,
    keyId: string,
  ): Promise<ProviderModelMeta[]> {
    const res = await refreshProviderModels(providerId, { key_id: keyId });
    modelsByProviderKey.value = {
      ...modelsByProviderKey.value,
      [modelCacheKey(providerId, keyId)]: res.models,
    };
    return res.models;
  }

  async function bootstrap(): Promise<void> {
    const [statusRes, providersRes] = await Promise.all([
      getConfigStatus(),
      listProviders(),
    ]);
    mode.value = statusRes.mode;
    anyConfigured.value = statusRes.any_provider_configured;
    providers.value = providersRes.providers;

    // Eager hydrate keys + default-key models so the picker is ready.
    const tasks: Array<Promise<unknown>> = [];
    for (const p of providersRes.providers) {
      tasks.push(
        loadKeys(p.id)
          .then(async (keys) => {
            const defaultKid = p.config?.default_key_id;
            if (defaultKid && keys.some((k) => k.id === defaultKid)) {
              try {
                await loadModels(p.id, defaultKid);
              } catch {
                // Ignore — user can manually refresh from /providers
              }
            }
          })
          .catch(() => {
            // Per-provider failures shouldn't break bootstrap
          }),
      );
    }
    await Promise.all(tasks);
    loaded.value = true;
  }

  async function updateConfig(
    providerId: string,
    body: UpdateProviderConfigRequest,
  ): Promise<ProviderConfigOut> {
    const updated = await updateProviderConfig(providerId, body);
    const idx = providers.value.findIndex((p) => p.id === providerId);
    if (idx >= 0) {
      const next = providers.value.slice();
      next[idx] = { ...next[idx], config: updated };
      providers.value = next;
    }
    return updated;
  }

  async function addKey(
    providerId: string,
    label: string,
    plainCreds: Record<string, string>,
  ): Promise<{ key: ProviderKeyMeta; models: ProviderModelMeta[]; refreshError: string | null }> {
    const encrypted_credentials = await encryptObject(plainCreds);
    const res = await addProviderKey(providerId, { label, encrypted_credentials });

    // Local cache update — appended key + models for that key.
    const existingKeys = keysByProvider.value[providerId] ?? [];
    keysByProvider.value = {
      ...keysByProvider.value,
      [providerId]: [...existingKeys, res.key],
    };
    modelsByProviderKey.value = {
      ...modelsByProviderKey.value,
      [modelCacheKey(providerId, res.key.id)]: res.models,
    };
    // Bump key_count on the provider summary
    const idx = providers.value.findIndex((p) => p.id === providerId);
    if (idx >= 0) {
      const next = providers.value.slice();
      next[idx] = { ...next[idx], key_count: next[idx].key_count + 1 };
      providers.value = next;
    }
    anyConfigured.value = true;
    return { key: res.key, models: res.models, refreshError: res.models_refresh_error };
  }

  async function deleteKey(providerId: string, keyId: string): Promise<void> {
    await deleteProviderKey(providerId, keyId);
    const existing = keysByProvider.value[providerId] ?? [];
    keysByProvider.value = {
      ...keysByProvider.value,
      [providerId]: existing.filter((k) => k.id !== keyId),
    };
    // Drop cached models for that key
    const next = { ...modelsByProviderKey.value };
    delete next[modelCacheKey(providerId, keyId)];
    modelsByProviderKey.value = next;

    const idx = providers.value.findIndex((p) => p.id === providerId);
    if (idx >= 0) {
      const cur = providers.value[idx];
      const cfg = cur.config;
      const newConfig: ProviderConfigOut | null =
        cfg && cfg.default_key_id === keyId
          ? { ...cfg, default_key_id: null }
          : cfg;
      const updated: ProviderSummary = {
        ...cur,
        key_count: Math.max(0, cur.key_count - 1),
        config: newConfig,
      };
      const slice = providers.value.slice();
      slice[idx] = updated;
      providers.value = slice;
    }
    // Recompute anyConfigured
    anyConfigured.value = providers.value.some((p) => {
      const ks = keysByProvider.value[p.id] ?? [];
      return ks.length > 0;
    });
  }

  const hasAnyKey = computed<boolean>(() =>
    providers.value.some((p) => (keysByProvider.value[p.id] ?? []).length > 0),
  );

  return {
    providers,
    keysByProvider,
    modelsByProviderKey,
    mode,
    anyConfigured,
    loaded,
    hasAnyKey,
    providerById,
    bootstrap,
    loadKeys,
    loadModels,
    refreshModels,
    updateConfig,
    addKey,
    deleteKey,
  };
});
