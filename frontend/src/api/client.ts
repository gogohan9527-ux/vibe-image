import type {
  AddKeyRequest,
  AddKeyResponse,
  CancelTaskResponse,
  ConfigStatus,
  CreatePromptRequest,
  CreateTaskRequest,
  CreateTaskResponse,
  ErrorBody,
  HistoryListResponse,
  HistoryQuery,
  ListProviderKeysResponse,
  ListProviderModelsResponse,
  ListProvidersResponse,
  ListPromptsResponse,
  ListTasksResponse,
  ProviderConfigOut,
  PromptItem,
  PublicKeyResponse,
  RefreshModelsRequest,
  RefreshModelsResponse,
  Settings,
  TaskItem,
  TempUploadResponse,
  UpdatePromptRequest,
  UpdateProviderConfigRequest,
  UpdateSettingsRequest,
} from '@/types/api';

export class ApiError extends Error {
  readonly status: number;
  readonly body: ErrorBody;

  constructor(status: number, body: ErrorBody) {
    super(body.message ?? body.code ?? `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }

  get code(): string {
    return this.body.code;
  }
}

function isErrorBody(value: unknown): value is ErrorBody {
  return typeof value === 'object' && value !== null && typeof (value as { code?: unknown }).code === 'string';
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }

  const res = await fetch(path, init);

  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  let parsed: unknown = null;
  if (text.length > 0) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
  }

  if (!res.ok) {
    if (isErrorBody(parsed)) {
      throw new ApiError(res.status, parsed);
    }
    // FastAPI 422 returns { detail: [...] } — wrap into ErrorBody shape
    if (parsed && typeof parsed === 'object' && 'detail' in (parsed as Record<string, unknown>)) {
      throw new ApiError(res.status, {
        code: 'validation_error',
        message: 'Request validation failed',
        detail: (parsed as { detail: unknown }).detail,
      });
    }
    throw new ApiError(res.status, { code: 'http_error', message: `HTTP ${res.status}` });
  }

  return parsed as T;
}

// --- Uploads (img2img reference image) ---
// Multipart upload — bypass the JSON `request<T>` wrapper because FormData
// requires the browser to set its own Content-Type with boundary.
export async function uploadTempImage(file: File): Promise<TempUploadResponse> {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/uploads/temp', { method: 'POST', body: fd });

  if (res.status === 204) {
    throw new ApiError(res.status, { code: 'http_error', message: 'Empty response' });
  }

  const text = await res.text();
  let parsed: unknown = null;
  if (text.length > 0) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
  }

  if (!res.ok) {
    if (isErrorBody(parsed)) {
      throw new ApiError(res.status, parsed);
    }
    if (parsed && typeof parsed === 'object' && 'detail' in (parsed as Record<string, unknown>)) {
      throw new ApiError(res.status, {
        code: 'validation_error',
        message: 'Request validation failed',
        detail: (parsed as { detail: unknown }).detail,
      });
    }
    throw new ApiError(res.status, { code: 'http_error', message: `HTTP ${res.status}` });
  }
  return parsed as TempUploadResponse;
}

// --- Tasks ---
export function createTask(payload: CreateTaskRequest): Promise<CreateTaskResponse> {
  return request<CreateTaskResponse>('POST', '/api/tasks', payload);
}

export function listTasks(): Promise<ListTasksResponse> {
  return request<ListTasksResponse>('GET', '/api/tasks');
}

export function getTask(taskId: string): Promise<TaskItem> {
  return request<TaskItem>('GET', `/api/tasks/${encodeURIComponent(taskId)}`);
}

export function cancelTask(taskId: string): Promise<CancelTaskResponse> {
  return request<CancelTaskResponse>('DELETE', `/api/tasks/${encodeURIComponent(taskId)}`);
}

// --- Prompts ---
export function listPrompts(): Promise<ListPromptsResponse> {
  return request<ListPromptsResponse>('GET', '/api/prompts');
}

export function createPrompt(payload: CreatePromptRequest): Promise<PromptItem> {
  return request<PromptItem>('POST', '/api/prompts', payload);
}

export function deletePrompt(promptId: string): Promise<void> {
  return request<void>('DELETE', `/api/prompts/${encodeURIComponent(promptId)}`);
}

export function updatePrompt(promptId: string, payload: UpdatePromptRequest): Promise<PromptItem> {
  return request<PromptItem>('PUT', `/api/prompts/${encodeURIComponent(promptId)}`, payload);
}

// --- Settings ---
export function getSettings(): Promise<Settings> {
  return request<Settings>('GET', '/api/settings');
}

export function putSettings(payload: UpdateSettingsRequest): Promise<Settings> {
  return request<Settings>('PUT', '/api/settings', payload);
}

// --- History ---
export function listHistory(query: HistoryQuery = {}): Promise<HistoryListResponse> {
  const params = new URLSearchParams();
  if (query.q) params.set('q', query.q);
  if (query.status) params.set('status', query.status);
  if (query.page) params.set('page', String(query.page));
  if (query.page_size) params.set('page_size', String(query.page_size));
  const qs = params.toString();
  return request<HistoryListResponse>('GET', `/api/history${qs ? `?${qs}` : ''}`);
}

export function deleteHistory(taskId: string): Promise<void> {
  return request<void>('DELETE', `/api/history/${encodeURIComponent(taskId)}`);
}

// --- Config / runtime credentials ---
export function getConfigStatus(): Promise<ConfigStatus> {
  return request<ConfigStatus>('GET', '/api/config/status');
}

export function getPublicKey(): Promise<PublicKeyResponse> {
  return request<PublicKeyResponse>('GET', '/api/config/public-key');
}

// --- Providers (2026-05-09) ---
export function listProviders(): Promise<ListProvidersResponse> {
  return request<ListProvidersResponse>('GET', '/api/providers');
}

export function updateProviderConfig(
  providerId: string,
  body: UpdateProviderConfigRequest,
): Promise<ProviderConfigOut> {
  return request<ProviderConfigOut>(
    'PUT',
    `/api/providers/${encodeURIComponent(providerId)}/config`,
    body,
  );
}

export function listProviderKeys(providerId: string): Promise<ListProviderKeysResponse> {
  return request<ListProviderKeysResponse>(
    'GET',
    `/api/providers/${encodeURIComponent(providerId)}/keys`,
  );
}

export function addProviderKey(
  providerId: string,
  body: AddKeyRequest,
): Promise<AddKeyResponse> {
  return request<AddKeyResponse>(
    'POST',
    `/api/providers/${encodeURIComponent(providerId)}/keys`,
    body,
  );
}

export function deleteProviderKey(providerId: string, keyId: string): Promise<void> {
  return request<void>(
    'DELETE',
    `/api/providers/${encodeURIComponent(providerId)}/keys/${encodeURIComponent(keyId)}`,
  );
}

export function listProviderModels(
  providerId: string,
  keyId: string,
): Promise<ListProviderModelsResponse> {
  const qs = new URLSearchParams({ key_id: keyId }).toString();
  return request<ListProviderModelsResponse>(
    'GET',
    `/api/providers/${encodeURIComponent(providerId)}/models?${qs}`,
  );
}

export function refreshProviderModels(
  providerId: string,
  body: RefreshModelsRequest,
): Promise<RefreshModelsResponse> {
  return request<RefreshModelsResponse>(
    'POST',
    `/api/providers/${encodeURIComponent(providerId)}/models/refresh`,
    body,
  );
}
