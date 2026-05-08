<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElButton, ElIcon } from 'element-plus';
import { Plus, List, Clock, Setting, Picture, Document } from '@element-plus/icons-vue';

defineEmits<{
  (e: 'new-task'): void;
  (e: 'open-settings'): void;
}>();

const route = useRoute();
const router = useRouter();

const navItems = computed(() => [
  { key: 'tasks', label: '任务列表', path: '/', icon: List },
  { key: 'history', label: '历史记录', path: '/history', icon: Clock },
  { key: 'templates', label: '模板配置', path: '/templates', icon: Document },
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
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-logo">
        <ElIcon :size="18"><Picture /></ElIcon>
      </div>
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
</template>

<style scoped>
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
  background: linear-gradient(135deg, #4d7df9, #7da6ff);
  color: #fff;
  display: grid;
  place-items: center;
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

.settings-btn {
  margin-top: 0;
}
</style>
