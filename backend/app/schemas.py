"""Pydantic schemas for API request/response bodies."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

TaskStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "cancelling",
]


# ---------- Tasks ----------

class TaskCreateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    prompt_template_id: Optional[str] = None
    save_as_template: bool = False
    # 2026-05-09: provider/key/model are now required. The frontend resolves
    # these via the providers API + UI before submitting a task.
    provider_id: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    size: Optional[str] = None
    # Allowed values: "low" | "medium" | "high" | "auto".
    quality: Optional[Literal["low", "medium", "high", "auto"]] = None
    format: Optional[str] = None
    n: int = Field(default=1, ge=1, le=50)
    priority: bool = False
    # 2026-05-09 Addendum (II): img2img reference image. Server-side relative
    # path returned from POST /api/uploads/temp, e.g. "temp/<sha1>.png".
    # Validated in api/tasks._resolve_task_input.
    input_image_path: Optional[str] = None


class TaskItem(BaseModel):
    id: str
    prompt_template_id: Optional[str] = None
    prompt: str
    title: Optional[str] = None
    model: str
    size: str
    quality: str
    format: str
    status: TaskStatus
    progress: int
    image_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    priority: int = 0
    # 2026-05-09: link to the provider/key that produced this task. Old rows
    # may have NULL values; the UI renders "(legacy)" in that case.
    provider_id: Optional[str] = None
    key_id: Optional[str] = None
    # 2026-05-09 Addendum (II): img2img reference image. Stored as a path
    # relative to images_dir (e.g. "temp/<sha1>.png"); legacy rows are NULL.
    input_image_path: Optional[str] = None
    # 2026-05-11 Addendum §D: client-facing URLs are hydrated by the route
    # layer (api/tasks.py, api/history.py) via storage_backend.to_url() so the
    # active storage backend (local / OSS) decides the URL shape. Computed at
    # request time, not stored.
    image_url: Optional[str] = None
    input_image_url: Optional[str] = None


class TaskCreateResponse(BaseModel):
    tasks: List[TaskItem]


class TaskListResponse(BaseModel):
    tasks: List[TaskItem]


class TaskCancelResponse(BaseModel):
    task_id: str
    status: TaskStatus


# ---------- Prompts ----------

class PromptItem(BaseModel):
    id: str
    title: str
    prompt: str
    created_at: str


class PromptListResponse(BaseModel):
    prompts: List[PromptItem]


class PromptCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1)
    id: Optional[str] = None  # if omitted, derived from title


class PromptUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    prompt: Optional[str] = Field(default=None, min_length=1)


# ---------- Settings ----------

class SettingsResponse(BaseModel):
    concurrency: int
    queue_cap: int
    max_concurrency: int
    max_queue_size: int


class SettingsUpdateRequest(BaseModel):
    concurrency: Optional[int] = Field(default=None, ge=1)
    queue_cap: Optional[int] = Field(default=None, ge=1)


# ---------- History ----------

class HistoryListResponse(BaseModel):
    items: List[TaskItem]
    total: int
    page: int
    page_size: int


# ---------- Config status ----------

class ConfigStatusResponse(BaseModel):
    mode: Literal["normal", "demo"]
    any_provider_configured: bool


# ---------- Providers ----------

class CredFieldOut(BaseModel):
    name: str
    label: str
    secret: bool = True
    required: bool = True


class ProviderConfigOut(BaseModel):
    base_url: str
    default_model: Optional[str] = None
    default_key_id: Optional[str] = None


class ProviderKeyMeta(BaseModel):
    id: str
    provider_id: str
    label: str
    created_at: str


class ProviderModelMeta(BaseModel):
    id: str
    display_name: Optional[str] = None
    fetched_at: str


class ProviderSummary(BaseModel):
    id: str
    display_name: str
    default_base_url: str
    credential_fields: List[CredFieldOut]
    config: Optional[ProviderConfigOut] = None
    key_count: int
    # 2026-05-09 Addendum (II): True iff the provider implements
    # ``build_image_edit_request`` and exposes ``supports_image_input``.
    # Frontend uses this to gate the img2img upload UI.
    supports_image_input: bool


class ProviderListResponse(BaseModel):
    providers: List[ProviderSummary]


class UpdateProviderConfigRequest(BaseModel):
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    default_key_id: Optional[str] = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "UpdateProviderConfigRequest":
        if (
            self.base_url is None
            and self.default_model is None
            and self.default_key_id is None
        ):
            raise ValueError("at least one field must be supplied")
        return self


class AddKeyRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    encrypted_credentials: Dict[str, str]


class ProviderKeyListResponse(BaseModel):
    keys: List[ProviderKeyMeta]


class ProviderModelListResponse(BaseModel):
    models: List[ProviderModelMeta]


class RefreshModelsRequest(BaseModel):
    key_id: str = Field(min_length=1)


# ---------- Uploads ----------

class TempUploadResponse(BaseModel):
    """Response of ``POST /api/uploads/temp`` — img2img reference image."""

    input_image_path: str
    url: str


# ---------- Errors ----------

class ErrorResponse(BaseModel):
    code: str
    message: str
    # Optional extra fields are added dynamically in the global handler.
