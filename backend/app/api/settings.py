"""Runtime settings (concurrency / queue cap)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..config import AppConfig
from ..core.task_manager import TaskManager
from ..schemas import SettingsResponse, SettingsUpdateRequest


router = APIRouter(prefix="/settings", tags=["settings"])


def _snapshot(manager: TaskManager, config: AppConfig) -> SettingsResponse:
    return SettingsResponse(
        concurrency=manager.concurrency,
        queue_cap=manager.queue_cap,
        max_concurrency=config.executor.max_concurrency,
        max_queue_size=config.executor.max_queue_size,
    )


@router.get("", response_model=SettingsResponse)
def get_settings(request: Request) -> SettingsResponse:
    return _snapshot(request.app.state.task_manager, request.app.state.config)


@router.put("", response_model=SettingsResponse)
def update_settings(req: SettingsUpdateRequest, request: Request) -> SettingsResponse:
    manager: TaskManager = request.app.state.task_manager
    if req.concurrency is not None:
        manager.set_concurrency(req.concurrency)
    if req.queue_cap is not None:
        manager.set_queue_cap(req.queue_cap)
    return _snapshot(manager, request.app.state.config)
