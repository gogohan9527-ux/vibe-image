// Type definitions mirroring the backend API schemas.

export type TaskStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'cancelling';

export interface TaskItem {
  id: string;
  prompt_template_id: string | null;
  prompt: string;
  title?: string | null;
  model: string;
  size: string;
  quality: string;
  format: string;
  status: TaskStatus;
  progress: number;
  image_path: string | null;
  image_url: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  priority: number;
}

export interface PromptItem {
  id: string;
  title: string;
  prompt: string;
  created_at: string;
}

export interface Settings {
  concurrency: number;
  queue_cap: number;
  max_concurrency: number;
  max_queue_size: number;
}

export interface UpdatePromptRequest {
  title?: string;
  prompt?: string;
}

export interface CreateTaskRequest {
  prompt: string;
  prompt_template_id?: string | null;
  save_as_template?: boolean;
  model?: string | null;
  size?: string | null;
  quality?: 'low' | 'medium' | 'high' | 'auto' | null;
  format?: string | null;
  n?: number;
  priority?: boolean;
  encrypted_api_key?: string;
  base_url?: string;
}

export interface ConfigStatus {
  api_key_configured: boolean;
  base_url: string;
}

export interface PublicKeyResponse {
  public_key_pem: string;
}

export interface CreateTaskResponse {
  tasks: TaskItem[];
}

export interface ListTasksResponse {
  tasks: TaskItem[];
}

export interface ListPromptsResponse {
  prompts: PromptItem[];
}

export interface CreatePromptRequest {
  title: string;
  prompt: string;
  id?: string | null;
}

export interface CancelTaskResponse {
  task_id: string;
  status: TaskStatus;
}

export type HistoryStatusFilter = 'succeeded' | 'failed' | 'cancelled' | 'all';

export interface HistoryQuery {
  q?: string;
  status?: HistoryStatusFilter;
  page?: number;
  page_size?: number;
}

export interface HistoryListResponse {
  items: TaskItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface UpdateSettingsRequest {
  concurrency?: number;
  queue_cap?: number;
}

// SSE event payloads
export interface SseStatusEvent {
  task_id: string;
  status: TaskStatus;
  progress: number;
}

export interface SseProgressEvent {
  task_id: string;
  progress: number;
  status: TaskStatus;
}

export interface SseTerminalEvent {
  task_id: string;
  status: TaskStatus;
  progress: number;
  image_path?: string | null;
  image_url?: string | null;
  error_message?: string | null;
}

// Error envelope
export interface ErrorBody {
  code: string;
  message?: string;
  // Variants:
  field?: 'concurrency' | 'queue_cap';
  task_id?: string;
  status?: TaskStatus;
  queue_size?: number;
  cap?: number;
  detail?: unknown;
}
