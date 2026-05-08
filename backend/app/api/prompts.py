"""Prompt asset routes (SQLite-backed via prompt_templates table)."""

from __future__ import annotations

from fastapi import APIRouter, Path, Request

from ..core.storage import Storage
from ..errors import VibeError
from ..schemas import (
    PromptCreateRequest,
    PromptItem,
    PromptListResponse,
    PromptUpdateRequest,
)


router = APIRouter(prefix="/prompts", tags=["prompts"])


class _PromptUpdateBadRequestError(VibeError):
    """Raised when PUT /prompts/{id} body has no fields to update."""

    code = "prompt_update_invalid"
    http_status = 400


@router.get("", response_model=PromptListResponse)
def list_prompts(request: Request) -> PromptListResponse:
    storage: Storage = request.app.state.storage
    items = storage.list_prompts()
    return PromptListResponse(prompts=[PromptItem(**i) for i in items])


@router.get("/{prompt_id}", response_model=PromptItem)
def get_prompt(prompt_id: str = Path(...), *, request: Request) -> PromptItem:
    storage: Storage = request.app.state.storage
    return PromptItem(**storage.get_prompt(prompt_id))


@router.post("", response_model=PromptItem, status_code=201)
def create_prompt(req: PromptCreateRequest, request: Request) -> PromptItem:
    storage: Storage = request.app.state.storage
    record = storage.save_prompt(title=req.title, prompt=req.prompt, prompt_id=req.id)
    return PromptItem(**record)


@router.put("/{prompt_id}", response_model=PromptItem)
def update_prompt(
    req: PromptUpdateRequest,
    prompt_id: str = Path(...),
    *,
    request: Request,
) -> PromptItem:
    storage: Storage = request.app.state.storage
    try:
        record = storage.update_prompt(
            prompt_id, title=req.title, prompt=req.prompt
        )
    except ValueError as exc:
        raise _PromptUpdateBadRequestError(str(exc) or "title or prompt required")
    return PromptItem(**record)


@router.delete("/{prompt_id}", status_code=204)
def delete_prompt(prompt_id: str = Path(...), *, request: Request) -> None:
    storage: Storage = request.app.state.storage
    storage.delete_prompt(prompt_id)
    return None
