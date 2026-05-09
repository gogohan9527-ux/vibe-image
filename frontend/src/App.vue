<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue';
import { ElMessage } from 'element-plus';
import AppSidebar from '@/components/AppSidebar.vue';
import NewTaskDrawer from '@/components/NewTaskDrawer.vue';
import SettingsDialog from '@/components/SettingsDialog.vue';
import { useTaskStream } from '@/composables/useTaskStream';
import { useProviderStore } from '@/stores/useProviderStore';

const newTaskOpen = ref(false);
const settingsOpen = ref(false);

const providers = useProviderStore();
const { open: openStream, close: closeStream } = useTaskStream();

onMounted(async () => {
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
  <div class="app-shell">
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
</style>
