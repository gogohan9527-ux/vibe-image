// Holds the runtime api credentials supplied by the user when the backend
// has no api_key configured. Memory-only by design — refreshing the page
// drops the credential and re-prompts, matching the "每次出现" requirement.

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { getConfigStatus } from '@/api/client';

export const useApiAuthStore = defineStore('apiAuth', () => {
  const serverConfigured = ref<boolean | null>(null);
  const serverBaseUrl = ref<string>('');
  const apiKey = ref<string | null>(null);
  const baseUrl = ref<string | null>(null);
  const loaded = ref(false);

  async function loadStatus(): Promise<void> {
    const res = await getConfigStatus();
    serverConfigured.value = res.api_key_configured;
    serverBaseUrl.value = res.base_url;
    loaded.value = true;
  }

  function setCredentials(payload: { apiKey: string; baseUrl: string }): void {
    apiKey.value = payload.apiKey;
    baseUrl.value = payload.baseUrl;
  }

  function clear(): void {
    apiKey.value = null;
    baseUrl.value = null;
  }

  const needsPrompt = computed<boolean>(() => {
    if (!loaded.value) return false;
    if (serverConfigured.value) return false;
    return !apiKey.value;
  });

  const hasUserCredentials = computed<boolean>(() => apiKey.value !== null);

  return {
    serverConfigured,
    serverBaseUrl,
    apiKey,
    baseUrl,
    loaded,
    needsPrompt,
    hasUserCredentials,
    loadStatus,
    setCredentials,
    clear,
  };
});
