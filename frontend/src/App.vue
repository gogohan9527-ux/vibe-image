<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue';
import { ElMessage, ElIcon } from 'element-plus';
import { List, Clock, Document, Connection, Setting, Plus } from '@element-plus/icons-vue';
import { useRoute, useRouter } from 'vue-router';
import AppSidebar from '@/components/AppSidebar.vue';
import NewTaskDrawer from '@/components/NewTaskDrawer.vue';
import SettingsDialog from '@/components/SettingsDialog.vue';
import { useTaskStream } from '@/composables/useTaskStream';
import { useProviderStore } from '@/stores/useProviderStore';
import { useIsMobile } from '@/composables/useMobile';
import { isDemoDenied, saveDemoToken } from '@/composables/useDemoGuard';
import { getHealth, ApiError } from '@/api/client';
import { computed } from 'vue';

const newTaskOpen = ref(false);
const settingsOpen = ref(false);

const providers = useProviderStore();
const { open: openStream, close: closeStream } = useTaskStream();
const { isMobile } = useIsMobile();

const route = useRoute();
const router = useRouter();

const navItems = [
  { key: 'tasks', label: '任务列表', path: '/', icon: List },
  { key: 'history', label: '历史记录', path: '/history', icon: Clock },
  { key: 'templates', label: '模板配置', path: '/templates', icon: Document },
  { key: 'providers', label: '插件配置', path: '/providers', icon: Connection },
];

const activeKey = computed(() => {
  const matched = navItems.find((item) => item.path === route.path);
  return matched ? matched.key : 'tasks';
});

function go(path: string): void {
  if (route.path !== path) void router.push(path);
}

onMounted(async () => {
  const params = new URLSearchParams(window.location.search);
  const urlToken = params.get('demo_token');
  if (urlToken) {
    saveDemoToken(urlToken);
    params.delete('demo_token');
    const cleaned = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
    history.replaceState(null, '', cleaned);
  }

  try {
    await getHealth();
  } catch (e) {
    if (e instanceof ApiError && e.code === 'demo_required') return;
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

  <!-- Normal app shell -->
  <div v-else class="app-shell">
    <!-- Desktop sidebar -->
    <AppSidebar v-if="!isMobile" @new-task="newTaskOpen = true" @open-settings="settingsOpen = true" />

    <!-- Main content -->
    <main class="app-main">
      <RouterView />
    </main>

    <!-- Mobile bottom nav (flex child — reliable on iOS) -->
    <nav v-if="isMobile" class="bottom-nav">
      <button
        v-for="item in navItems"
        :key="item.key"
        type="button"
        class="bottom-nav-item"
        :class="{ active: activeKey === item.key }"
        @click="go(item.path)"
      >
        <ElIcon class="bottom-nav-icon"><component :is="item.icon" /></ElIcon>
        <span class="bottom-nav-label">{{ item.label }}</span>
      </button>

      <button type="button" class="bottom-nav-fab" @click="newTaskOpen = true">
        <ElIcon :size="22"><Plus /></ElIcon>
      </button>

      <button type="button" class="bottom-nav-item" @click="settingsOpen = true">
        <ElIcon class="bottom-nav-icon"><Setting /></ElIcon>
        <span class="bottom-nav-label">设置</span>
      </button>
    </nav>

    <NewTaskDrawer v-model:open="newTaskOpen" />
    <SettingsDialog v-model:open="settingsOpen" />
  </div>
</template>

<style scoped>
/* ── Desktop ── */
.app-shell {
  display: flex;
  flex-direction: row;
  height: 100vh;
  background: var(--vi-bg);
}

.app-main {
  flex: 1;
  overflow: auto;
  padding: 24px 28px;
  min-width: 0;
}

/* ── Mobile: column layout so bottom nav is a real flex child ── */
@media (max-width: 767px) {
  .app-shell {
    flex-direction: column;
    height: 100dvh; /* dvh accounts for mobile browser chrome */
  }

  .app-main {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 16px;
  }
}

/* ── Mobile bottom nav ── */
.bottom-nav {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  background: #fff;
  border-top: 1px solid var(--vi-border);
  height: 60px;
  padding: 0 4px;
  padding-bottom: env(safe-area-inset-bottom);
  box-shadow: 0 -2px 12px rgba(15, 23, 42, 0.06);
}

.bottom-nav-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  border: 0;
  background: transparent;
  color: var(--vi-text-muted);
  cursor: pointer;
  padding: 6px 0;
  transition: color 0.15s;
  min-width: 0;
}

.bottom-nav-item.active {
  color: var(--vi-primary);
}

.bottom-nav-icon {
  font-size: 20px;
}

.bottom-nav-label {
  font-size: 10px;
  line-height: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 56px;
}

.bottom-nav-fab {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  border: 0;
  background: var(--vi-primary);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 8px;
  box-shadow: 0 4px 14px rgba(59, 108, 245, 0.35);
  transition: background-color 0.15s, transform 0.1s;
  flex: 0 0 48px;
}

.bottom-nav-fab:active {
  transform: scale(0.93);
}

/* ── Demo denied ── */
.demo-denied-overlay {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: #f0f2f5;
  padding: 16px;
}

.demo-denied-card {
  background: #fff;
  border-radius: 12px;
  padding: 48px 56px;
  text-align: center;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.10);
  max-width: 420px;
  width: 100%;
}

@media (max-width: 767px) {
  .demo-denied-card {
    padding: 36px 24px;
  }
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
