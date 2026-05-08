"""Pydantic schemas for API request/response bodies."""

from __future__ import annotations

import os
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, computed_field

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
    model: Optional[str] = None
    size: Optional[str] = None
    # Allowed values: "low" | "medium" | "high" | "auto".
    # When omitted, the server falls back to ``config.api.default_quality``.
    quality: Optional[Literal["low", "medium", "high", "auto"]] = None
    format: Optional[str] = None
    n: int = Field(default=1, ge=1, le=50)
    priority: bool = False


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

    @computed_field  # type: ignore[misc]
    @property
    def image_url(self) -> Optional[str]:
        if not self.image_path:
            return None
        return f"/images/{os.path.basename(self.image_path)}"


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


# ---------- Errors ----------

class ErrorResponse(BaseModel):
    code: str
    message: str
    # Optional extra fields are added dynamically in the global handler.
