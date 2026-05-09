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
  // Added 2026-05-09. NULL for tasks created before the multi-provider migration.
  provider_id?: string | null;
  key_id?: string | null;
  // Added 2026-05-09 (II) — img2img. NULL for text-to-image tasks and legacy rows.
  input_image_path?: string | null;
  input_image_url?: string | null;
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
  // Required as of 2026-05-09 — replaces encrypted_api_key/base_url.
  provider_id: string;
  key_id: string;
  model: string;
  size?: string | null;
  quality?: 'low' | 'medium' | 'high' | 'auto' | null;
  format?: string | null;
  n?: number;
  priority?: boolean;
  // Added 2026-05-09 (II) — img2img reference image; "temp/<sha1>.<ext>" or null/undefined.
  input_image_path?: string | null;
}

// Rewritten 2026-05-09. Old api_key_configured/base_url fields are gone.
export interface ConfigStatus {
  mode: 'normal' | 'demo';
  any_provider_configured: boolean;
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
  provider_id?: string;
  key_id?: string;
  missing_fields?: string[];
  detail?: unknown;
}

// --- Providers (added 2026-05-09) ---

export interface CredField {
  name: string;
  label: string;
  secret: boolean;
  required: boolean;
}

export interface ProviderConfigOut {
  base_url: string;
  default_model: string | null;
  default_key_id: string | null;
}

export interface ProviderSummary {
  id: string;
  display_name: string;
  default_base_url: string;
  credential_fields: CredField[];
  config: ProviderConfigOut | null;
  key_count: number;
  // Added 2026-05-09 (II) — true if provider implements img2img.
  supports_image_input: boolean;
}

export interface TempUploadResponse {
  /** Server-side relative path, e.g. "temp/<sha1>.png". */
  input_image_path: string;
  /** Public URL for inline preview, e.g. "/images/temp/<sha1>.png". */
  url: string;
}

export interface ListProvidersResponse {
  providers: ProviderSummary[];
}

export interface ProviderKeyMeta {
  id: string;
  provider_id: string;
  label: string;
  created_at: string;
}

export interface ListProviderKeysResponse {
  keys: ProviderKeyMeta[];
}

export interface ProviderModelMeta {
  id: string;
  display_name: string | null;
  fetched_at: string;
}

export interface ListProviderModelsResponse {
  models: ProviderModelMeta[];
}

export interface AddKeyRequest {
  label: string;
  encrypted_credentials: Record<string, string>;
}

export interface AddKeyResponse {
  key: ProviderKeyMeta;
  models: ProviderModelMeta[];
  models_refresh_error: string | null;
}

export interface UpdateProviderConfigRequest {
  base_url?: string;
  default_model?: string;
  default_key_id?: string;
}

export interface RefreshModelsRequest {
  key_id: string;
}

export interface RefreshModelsResponse {
  models: ProviderModelMeta[];
}
