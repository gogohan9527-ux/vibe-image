import type {
  SseProgressEvent,
  SseStatusEvent,
  SseTerminalEvent,
} from '@/types/api';
import { useTaskStore } from '@/stores/useTaskStore';

let source: EventSource | null = null;

export function useTaskStream(): { open: () => void; close: () => void } {
  const store = useTaskStore();

  function parse<T>(raw: string): T | null {
    try {
      return JSON.parse(raw) as T;
    } catch {
      return null;
    }
  }

  function open(): void {
    if (source) return;
    const es = new EventSource('/api/tasks/stream/events');

    es.addEventListener('hello', () => {
      // Pull the current snapshot once we know the stream is live
      void store.fetchActive();
    });

    es.addEventListener('status', (e) => {
      const data = parse<SseStatusEvent>((e as MessageEvent<string>).data);
      if (data) store.applyStatus(data);
    });

    es.addEventListener('progress', (e) => {
      const data = parse<SseProgressEvent>((e as MessageEvent<string>).data);
      if (data) store.applyProgress(data);
    });

    es.addEventListener('terminal', (e) => {
      const data = parse<SseTerminalEvent>((e as MessageEvent<string>).data);
      if (data) store.applyTerminal(data);
    });

    es.onerror = () => {
      // Browser auto-reconnects EventSource by default. Nothing to do.
    };

    source = es;
  }

  function close(): void {
    if (source) {
      source.close();
      source = null;
    }
  }

  return { open, close };
}
