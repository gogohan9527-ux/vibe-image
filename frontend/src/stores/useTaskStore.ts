import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import type {
  SseProgressEvent,
  SseStatusEvent,
  SseTerminalEvent,
  TaskItem,
  TaskStatus,
} from '@/types/api';
import { listTasks } from '@/api/client';

const ACTIVE_STATUSES: ReadonlyArray<TaskStatus> = ['queued', 'running', 'cancelling'];

export const useTaskStore = defineStore('tasks', () => {
  // Active tasks keyed by id
  const tasksById = ref<Map<string, TaskItem>>(new Map());
  const loaded = ref(false);

  // Rolling window of completed-task durations (ms) for ETA estimates
  const recentDurations = ref<number[]>([]);

  function upsert(task: TaskItem): void {
    const next = new Map(tasksById.value);
    next.set(task.id, task);
    tasksById.value = next;
  }

  function remove(taskId: string): void {
    if (!tasksById.value.has(taskId)) return;
    const next = new Map(tasksById.value);
    next.delete(taskId);
    tasksById.value = next;
  }

  async function fetchActive(): Promise<void> {
    const res = await listTasks();
    const map = new Map<string, TaskItem>();
    for (const t of res.tasks) map.set(t.id, t);
    tasksById.value = map;
    loaded.value = true;
  }

  function applyStatus(ev: SseStatusEvent): void {
    const existing = tasksById.value.get(ev.task_id);
    if (!existing) {
      // We don't have the full record; refresh in the background
      void refreshTask(ev.task_id);
      return;
    }
    upsert({ ...existing, status: ev.status, progress: ev.progress });
  }

  function applyProgress(ev: SseProgressEvent): void {
    const existing = tasksById.value.get(ev.task_id);
    if (!existing) {
      void refreshTask(ev.task_id);
      return;
    }
    // Don't ever rewind progress
    const nextProgress = Math.max(existing.progress, ev.progress);
    upsert({ ...existing, status: ev.status, progress: nextProgress });
  }

  function applyTerminal(ev: SseTerminalEvent): void {
    const existing = tasksById.value.get(ev.task_id);
    const startedAt = existing?.started_at ? Date.parse(existing.started_at) : NaN;

    if (ev.status === 'succeeded') {
      // Track duration for ETA estimates
      if (!Number.isNaN(startedAt)) {
        const dur = Date.now() - startedAt;
        if (dur > 0 && dur < 10 * 60_000) {
          recentDurations.value = [...recentDurations.value.slice(-19), dur];
        }
      }
    }

    // For failed/cancelled events, the backend may emit progress=0; preserve last known progress.
    if (ev.status === 'failed' || ev.status === 'cancelled') {
      // Just remove from the active list — terminal states live in /history.
      remove(ev.task_id);
      return;
    }

    if (ev.status === 'succeeded') {
      // Brief visual confirmation, then remove (history view picks it up).
      if (existing) {
        upsert({
          ...existing,
          status: 'succeeded',
          progress: 100,
          image_path: ev.image_path ?? existing.image_path,
          image_url: ev.image_url ?? existing.image_url,
          finished_at: new Date().toISOString(),
        });
      }
      // Drop after a short delay so the success state can flash visually.
      window.setTimeout(() => remove(ev.task_id), 800);
      return;
    }

    // Unknown terminal status — remove defensively.
    remove(ev.task_id);
  }

  async function refreshTask(_taskId: string): Promise<void> {
    // Refresh active list rather than per-id (cheap & avoids 404 on race).
    try {
      await fetchActive();
    } catch {
      // ignore — SSE will catch up
    }
  }

  const tasks = computed<TaskItem[]>(() => {
    const arr = Array.from(tasksById.value.values()).filter((t) =>
      ACTIVE_STATUSES.includes(t.status) || t.status === 'succeeded',
    );
    arr.sort((a, b) => a.created_at.localeCompare(b.created_at));
    return arr;
  });

  const averageDurationMs = computed<number | null>(() => {
    if (recentDurations.value.length === 0) return null;
    const sum = recentDurations.value.reduce((acc, n) => acc + n, 0);
    return sum / recentDurations.value.length;
  });

  return {
    tasksById,
    tasks,
    loaded,
    averageDurationMs,
    fetchActive,
    upsert,
    remove,
    applyStatus,
    applyProgress,
    applyTerminal,
  };
});
