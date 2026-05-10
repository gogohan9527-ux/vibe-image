<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElButton, ElIcon } from 'element-plus';
import { Plus, List, Clock, Setting, Document, Connection } from '@element-plus/icons-vue';
import { useIsMobile } from '@/composables/useMobile';

defineEmits<{
  (e: 'new-task'): void;
  (e: 'open-settings'): void;
}>();

const route = useRoute();
const router = useRouter();
const { isMobile } = useIsMobile();

const navItems = computed(() => [
  { key: 'tasks', label: '任务列表', path: '/', icon: List },
  { key: 'history', label: '历史记录', path: '/history', icon: Clock },
  { key: 'templates', label: '模板配置', path: '/templates', icon: Document },
  { key: 'providers', label: '插件配置', path: '/providers', icon: Connection },
]);

const activeKey = computed(() => {
  const matched = navItems.value.find((item) => item.path === route.path);
  return matched ? matched.key : 'tasks';
});

function go(path: string): void {
  if (route.path !== path) {
    void router.push(path);
  }
}
</script>

<template>
  <!-- Desktop sidebar -->
  <aside v-if="!isMobile" class="sidebar">
    <div class="brand">
      <img class="brand-logo" src="/logo.png" alt="vibe-image logo" />
      <div class="brand-text">提示词生成图片</div>
    </div>

    <ElButton type="primary" class="new-task-btn" @click="$emit('new-task')">
      <ElIcon class="btn-icon"><Plus /></ElIcon>
      新建任务
    </ElButton>

    <nav class="nav">
      <button
        v-for="item in navItems"
        :key="item.key"
        type="button"
        class="nav-item"
        :class="{ active: activeKey === item.key }"
        @click="go(item.path)"
      >
        <ElIcon class="nav-icon"><component :is="item.icon" /></ElIcon>
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <div class="sidebar-spacer" />

    <button type="button" class="settings-btn" @click="$emit('open-settings')">
      <ElIcon class="nav-icon"><Setting /></ElIcon>
      <span>设置</span>
    </button>
  </aside>

  <!-- Mobile bottom nav bar -->
  <nav v-else class="bottom-nav">
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

    <!-- Center FAB for new task -->
    <button type="button" class="bottom-nav-fab" @click="$emit('new-task')">
      <ElIcon :size="22"><Plus /></ElIcon>
    </button>

    <button type="button" class="bottom-nav-item" @click="$emit('open-settings')">
      <ElIcon class="bottom-nav-icon"><Setting /></ElIcon>
      <span class="bottom-nav-label">设置</span>
    </button>
  </nav>
</template>

<style scoped>
/* ── Desktop sidebar ── */
.sidebar {
  width: 232px;
  flex-shrink: 0;
  background: #ffffff;
  border-right: 1px solid var(--vi-border);
  display: flex;
  flex-direction: column;
  padding: 22px 16px;
  gap: 16px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 6px 8px;
}

.brand-logo {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  object-fit: cover;
  display: block;
}

.brand-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--vi-text);
}

.new-task-btn {
  width: 100%;
  height: 38px;
  border-radius: 8px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-icon {
  margin-right: 6px;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.nav-item,
.settings-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: 0;
  background: transparent;
  border-radius: 8px;
  color: var(--vi-text-muted);
  font-size: 14px;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.15s, color 0.15s;
}

.nav-item:hover,
.settings-btn:hover {
  background: #f3f5fa;
  color: var(--vi-text);
}

.nav-item.active {
  background: var(--vi-primary-soft);
  color: var(--vi-primary);
  font-weight: 500;
}

.nav-icon {
  font-size: 16px;
}

.sidebar-spacer {
  flex: 1;
}

/* ── Mobile bottom nav ── */
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: #fff;
  border-top: 1px solid var(--vi-border);
  display: flex;
  align-items: center;
  height: 60px;
  padding: 0 4px;
  padding-bottom: env(safe-area-inset-bottom);
  /* Ensure it sits above Element Plus overlays */
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
</style>
