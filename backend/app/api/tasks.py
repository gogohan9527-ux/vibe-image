"""Task routes: create / list / get / cancel + SSE stream."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import List

from fastapi import APIRouter, Path, Request
from fastapi.responses import StreamingResponse

from ..config import AppConfig
from ..core.storage import Storage
from ..core.task_manager import TaskInput, TaskManager
from ..schemas import (
    TaskCancelResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskItem,
    TaskListResponse,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])


def _resolve_task_input(req: TaskCreateRequest, config: AppConfig) -> TaskInput:
    return TaskInput(
        prompt=req.prompt,
        model=req.model or config.api.default_model,
        size=req.size or config.api.default_size,
        quality=req.quality or config.api.default_quality,
        format=req.format or config.api.default_format,
        prompt_template_id=req.prompt_template_id,
        priority=req.priority,
    )


@router.post("", response_model=TaskCreateResponse, status_code=201)
def create_tasks(req: TaskCreateRequest, request: Request) -> TaskCreateResponse:
    config: AppConfig = request.app.state.config
    manager: TaskManager = request.app.state.task_manager
    storage: Storage = request.app.state.storage

    # Optionally save the prompt as a template (title auto-derived from first 30 chars).
    if req.save_as_template:
        storage.save_prompt(title=req.prompt[:30], prompt=req.prompt)

    rows: List[dict] = []
    base_input = _resolve_task_input(req, config)
    for _ in range(req.n):
        row = manager.submit(base_input)
        rows.append(row)
    return TaskCreateResponse(tasks=[TaskItem(**r) for r in rows])


@router.get("", response_model=TaskListResponse)
def list_tasks(request: Request) -> TaskListResponse:
    storage: Storage = request.app.state.storage
    rows = storage.list_tasks(
        statuses=("queued", "running", "cancelling"), order="created_at_asc"
    )
    return TaskListResponse(tasks=[TaskItem(**r) for r in rows])


@router.get("/{task_id}", response_model=TaskItem)
def get_task(task_id: str = Path(...), *, request: Request) -> TaskItem:
    storage: Storage = request.app.state.storage
    row = storage.get_task(task_id)
    return TaskItem(**row)


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
    The frontend should connect to this URL.
    """
    manager: TaskManager = request.app.state.task_manager

    q: "queue.Queue[dict]" = queue.Queue(maxsize=1024)
    sentinel = object()
    # Sync-thread listener pushes to a thread-safe Queue. The async generator
    # awaits items via run_in_executor (queue.get is blocking).
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
            # Initial hello so the client knows the stream is open.
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
                    # Heartbeat to keep proxies happy.
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
