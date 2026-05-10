<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue';
import { ElMessage } from 'element-plus';
import AppSidebar from '@/components/AppSidebar.vue';
import NewTaskDrawer from '@/components/NewTaskDrawer.vue';
import SettingsDialog from '@/components/SettingsDialog.vue';
import { useTaskStream } from '@/composables/useTaskStream';
import { useProviderStore } from '@/stores/useProviderStore';
import { isDemoDenied, saveDemoToken } from '@/composables/useDemoGuard';
import { getHealth, ApiError } from '@/api/client';

const newTaskOpen = ref(false);
const settingsOpen = ref(false);

const providers = useProviderStore();
const { open: openStream, close: closeStream } = useTaskStream();

onMounted(async () => {
  // Read demo_token from URL, save to localStorage, clean the URL
  const params = new URLSearchParams(window.location.search);
  const urlToken = params.get('demo_token');
  if (urlToken) {
    saveDemoToken(urlToken);
    params.delete('demo_token');
    const cleaned = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
    history.replaceState(null, '', cleaned);
  }

  // Health check to verify demo token (works in both normal and demo mode)
  try {
    await getHealth();
  } catch (e) {
    if (e instanceof ApiError && e.code === 'demo_required') {
      // isDemoDenied already set by client.ts; don't open stream
      return;
    }
    // Other errors (network issues etc.) — still try to open stream
  }

  openStream();
  try {
    await providers.bootstrap();
  } catch {
    ElMessage.error('无法获取后端配置状态，请检查后端是否已启动');
  }
});
onBeforeUnmount(() => {
  closeStream();
});
</script>

<template>
  <!-- Demo access denied overlay -->
  <div v-if="isDemoDenied" class="demo-denied-overlay">
    <div class="demo-denied-card">
      <div class="demo-denied-icon">🔒</div>
      <h2 class="demo-denied-title">Demo 演示模式</h2>
      <p class="demo-denied-desc">
        抱歉，您没有收到此 Demo 的访问邀请。<br />
        请联系管理员获取访问链接。
      </p>
    </div>
  </div>

  <!-- Normal app shell (hidden when denied) -->
  <div v-else class="app-shell">
    <AppSidebar @new-task="newTaskOpen = true" @open-settings="settingsOpen = true" />
    <main class="app-main">
      <RouterView />
    </main>
    <NewTaskDrawer v-model:open="newTaskOpen" />
    <SettingsDialog v-model:open="settingsOpen" />
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  height: 100vh;
  background: var(--vi-bg);
}

.app-main {
  flex: 1;
  overflow: auto;
  padding: 24px 28px;
}

.demo-denied-overlay {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: #f0f2f5;
}

.demo-denied-card {
  background: #fff;
  border-radius: 12px;
  padding: 48px 56px;
  text-align: center;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.10);
  max-width: 420px;
}

.demo-denied-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.demo-denied-title {
  font-size: 20px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0 0 12px;
}

.demo-denied-desc {
  font-size: 14px;
  color: #666;
  line-height: 1.6;
  margin: 0;
}
</style>
