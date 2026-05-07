"""History list (terminal tasks) with search + status filter + pagination."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Path as PathParam, Query, Request, Response

from ..core.storage import Storage
from ..errors import TaskNotFoundError, VibeError
from ..schemas import HistoryListResponse, TaskItem


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/history", tags=["history"])


_TERMINAL = ("succeeded", "failed", "cancelled")
_ACTIVE = ("queued", "running", "cancelling")


class _TaskActiveError(VibeError):
    """Raised when trying to delete a non-terminal task from history."""

    code = "task_active"
    http_status = 409


@router.get("", response_model=HistoryListResponse)
def list_history(
    request: Request,
    q: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> HistoryListResponse:
    storage: Storage = request.app.state.storage
    if status and status != "all":
        statuses: List[str] = [status]
    else:
        statuses = list(_TERMINAL)
    rows, total = storage.search_tasks(
        query=q, statuses=statuses, page=page, page_size=page_size
    )
    return HistoryListResponse(
        items=[TaskItem(**r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/{task_id}", status_code=204)
def delete_history(task_id: str = PathParam(...), *, request: Request) -> Response:
    """Delete a terminal task from history.

    - 404 if the task does not exist.
    - 409 ``task_active`` if the task is queued/running/cancelling — caller
      should cancel via ``DELETE /api/tasks/{task_id}`` first.
    - Otherwise: best-effort unlink the rendered image, then drop the row.
    """
    storage: Storage = request.app.state.storage
    try:
        row = storage.get_task(task_id)
    except TaskNotFoundError:
        raise TaskNotFoundError("task not found", task_id=task_id)

    if row["status"] in _ACTIVE:
        raise _TaskActiveError("cancel the task before deleting from history")

    image_path = row.get("image_path")
    if image_path:
        try:
            Path(image_path).unlink(missing_ok=True)
        except OSError as exc:
            # Don't let filesystem hiccups break the DB delete; just log.
            logger.info(
                "history delete: could not unlink %s (%s)", image_path, exc
            )

    storage.delete_task(task_id)
    return Response(status_code=204)
