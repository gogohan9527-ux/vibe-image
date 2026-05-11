"""Task routes: create / list / get / cancel + SSE stream."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import List, Optional

from fastapi import APIRouter, Path, Request
from fastapi.responses import StreamingResponse

from ..config import AppConfig
from ..core.provider_store import (
    ProviderNotFoundInStoreError,
    ProviderStore,
)
from ..core.storage import Storage
from ..core.storage_backend import StorageBackend, hydrate_task_item_urls
from ..core.task_manager import TaskInput, TaskManager
from ..errors import (
    InputImageNotFoundError,
    KeyNotFoundError,
    ProviderCapabilityError,
    ProviderNotConfiguredError,
    UnknownProviderError,
)
from ..providers import PROVIDER_REGISTRY
from ..schemas import (
    TaskCancelResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskItem,
    TaskListResponse,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])


_DEFAULT_SIZE = "1024x1024"
_DEFAULT_QUALITY = "low"
_DEFAULT_FORMAT = "jpeg"


def _validate_input_image_path(raw: str, config: AppConfig) -> str:
    """Validate the user-supplied ``input_image_path`` is safe + exists.

    Returns the same string unchanged on success. Raises
    ``InputImageNotFoundError`` for a missing file or a path that escapes
    ``images_dir``.
    """
    # Must reference the temp/ subtree we control. Reject anything else
    # immediately (also rejects absolute paths and Windows drive letters
    # because those can't start with "temp/").
    if not raw.startswith("temp/"):
        raise InputImageNotFoundError(input_image_path=raw)

    images_root = config.images_dir.resolve()
    target = (config.images_dir / raw).resolve()
    if not target.is_relative_to(images_root):
        raise InputImageNotFoundError(input_image_path=raw)
    if not target.is_file():
        raise InputImageNotFoundError(input_image_path=raw)
    return raw


def _resolve_task_input(
    req: TaskCreateRequest,
    provider_store: ProviderStore,
    config: AppConfig,
) -> TaskInput:
    if req.provider_id not in PROVIDER_REGISTRY:
        raise UnknownProviderError(req.provider_id)

    # Look up the provider's persisted config (base_url + defaults). If the
    # row does not exist the provider has never been configured — treat this
    # as ``provider_not_configured``.
    pcfg = provider_store.get_config(req.provider_id)
    provider = PROVIDER_REGISTRY[req.provider_id]
    base_url = pcfg.base_url if pcfg is not None else provider.default_base_url

    # Verify the key exists for this provider, then load its credentials.
    keys = {k.id for k in provider_store.list_keys(req.provider_id)}
    if not keys:
        raise ProviderNotConfiguredError(req.provider_id)
    if req.key_id not in keys:
        raise KeyNotFoundError(req.key_id)
    try:
        creds = provider_store.get_key_credentials(req.provider_id, req.key_id)
    except ProviderNotFoundInStoreError as exc:
        raise KeyNotFoundError(req.key_id) from exc

    # 2026-05-09 Addendum (II) — img2img validation. Both checks fire BEFORE
    # the task is queued so we can surface failures synchronously to the UI.
    input_image_path: Optional[str] = None
    if req.input_image_path:
        input_image_path = _validate_input_image_path(req.input_image_path, config)
        if not getattr(provider, "supports_image_input", False):
            raise ProviderCapabilityError(
                provider_id=req.provider_id, capability="image_input"
            )

    return TaskInput(
        prompt=req.prompt,
        model=req.model,
        size=req.size or _DEFAULT_SIZE,
        quality=req.quality or _DEFAULT_QUALITY,
        format=req.format or _DEFAULT_FORMAT,
        prompt_template_id=req.prompt_template_id,
        priority=req.priority,
        provider_id=req.provider_id,
        key_id=req.key_id,
        base_url=base_url,
        creds=creds,
        input_image_path=input_image_path,
    )


def _build_task_item(row: dict, backend: StorageBackend) -> TaskItem:
    return hydrate_task_item_urls(TaskItem(**row), backend)


@router.post("", response_model=TaskCreateResponse, status_code=201)
def create_tasks(req: TaskCreateRequest, request: Request) -> TaskCreateResponse:
    manager: TaskManager = request.app.state.task_manager
    storage: Storage = request.app.state.storage
    provider_store: ProviderStore = request.app.state.provider_store
    config: AppConfig = request.app.state.config
    backend: StorageBackend = request.app.state.storage_backend

    if req.save_as_template:
        storage.save_prompt(title=req.prompt[:30], prompt=req.prompt)

    rows: List[dict] = []
    base_input = _resolve_task_input(req, provider_store, config)
    for _ in range(req.n):
        row = manager.submit(base_input)
        rows.append(row)
    return TaskCreateResponse(tasks=[_build_task_item(r, backend) for r in rows])


@router.get("", response_model=TaskListResponse)
def list_tasks(request: Request) -> TaskListResponse:
    storage: Storage = request.app.state.storage
    backend: StorageBackend = request.app.state.storage_backend
    rows = storage.list_tasks(
        statuses=("queued", "running", "cancelling"), order="created_at_asc"
    )
    return TaskListResponse(tasks=[_build_task_item(r, backend) for r in rows])


@router.get("/{task_id}", response_model=TaskItem)
def get_task(task_id: str = Path(...), *, request: Request) -> TaskItem:
    storage: Storage = request.app.state.storage
    backend: StorageBackend = request.app.state.storage_backend
    row = storage.get_task(task_id)
    return _build_task_item(row, backend)


@router.delete("/{task_id}", response_model=TaskCancelResponse)
def cancel_task(task_id: str = Path(...), *, request: Request) -> TaskCancelResponse:
    manager: TaskManager = request.app.state.task_manager
    row = manager.cancel(task_id)
    return TaskCancelResponse(task_id=row["id"], status=row["status"])


# ---------- SSE ----------

@router.get("/stream/events")
async def stream_events(request: Request) -> StreamingResponse:
    """SSE stream of task events.

    NOTE: Path is ``/api/tasks/stream/events`` rather than
    ``/api/tasks/stream`` to avoid colliding with ``GET /api/tasks/{task_id}``.
    """
    manager: TaskManager = request.app.state.task_manager

    q: "queue.Queue[dict]" = queue.Queue(maxsize=1024)
    sentinel = object()
    closed = threading.Event()

    def _listener(payload: dict) -> None:
        if closed.is_set():
            return
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass  # drop on overflow

    manager.subscribe(_listener)

    async def _gen():
        loop = asyncio.get_event_loop()
        try:
            yield "event: hello\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await loop.run_in_executor(None, _get_with_timeout, q, 15.0)
                except _StreamClosed:
                    break
                if item is sentinel:
                    break
                if item is None:
                    yield ": ping\n\n"
                    continue
                event = item.get("event", "message")
                payload = json.dumps(item, ensure_ascii=False)
                yield f"event: {event}\ndata: {payload}\n\n"
        finally:
            closed.set()
            manager.unsubscribe(_listener)

    return StreamingResponse(_gen(), media_type="text/event-stream")


class _StreamClosed(Exception):
    pass


def _get_with_timeout(q: "queue.Queue[dict]", timeout: float):
    try:
        return q.get(timeout=timeout)
    except queue.Empty:
        return None  # heartbeat
