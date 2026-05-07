<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { ElIcon, ElButton, ElEmpty, ElMessage } from 'element-plus';
import { Refresh } from '@element-plus/icons-vue';
import { useTaskStore } from '@/stores/useTaskStore';
import { storeToRefs } from 'pinia';
import TaskCard from '@/components/TaskCard.vue';
import { ApiError } from '@/api/client';

const store = useTaskStore();
const { tasks, averageDurationMs } = storeToRefs(store);

const refreshing = ref(false);

async function refresh(): Promise<void> {
  refreshing.value = true;
  try {
    await store.fetchActive();
  } catch (err) {
    if (err instanceof ApiError) {
      ElMessage.error(err.message);
    }
  } finally {
    refreshing.value = false;
  }
}

onMounted(() => {
  if (!store.loaded) void refresh();
});

const visibleTasks = computed(() => tasks.value);
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1 class="page-title">任务列表</h1>
        <p class="page-sub">查看您正在生成的、高优先级的任务</p>
      </div>
      <ElButton :loading="refreshing" circle @click="refresh">
        <ElIcon><Refresh /></ElIcon>
      </ElButton>
    </header>

    <section v-if="visibleTasks.length > 0" class="task-list">
      <TaskCard
        v-for="(task, idx) in visibleTasks"
        :key="task.id"
        :task="task"
        :index="idx + 1"
        :average-duration-ms="averageDurationMs"
      />
    </section>

    <ElEmpty v-else description="暂无进行中的任务" class="empty" />
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1080px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 12px;
}

.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: var(--vi-text);
}

.page-sub {
  margin: 4px 0 0;
  color: var(--vi-text-muted);
  font-size: 13px;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty {
  margin-top: 40px;
}
</style>
