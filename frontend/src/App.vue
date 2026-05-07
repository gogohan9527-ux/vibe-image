<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue';
import AppSidebar from '@/components/AppSidebar.vue';
import NewTaskDrawer from '@/components/NewTaskDrawer.vue';
import SettingsDialog from '@/components/SettingsDialog.vue';
import { useTaskStream } from '@/composables/useTaskStream';

const newTaskOpen = ref(false);
const settingsOpen = ref(false);

const { open: openStream, close: closeStream } = useTaskStream();

onMounted(() => {
  openStream();
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
