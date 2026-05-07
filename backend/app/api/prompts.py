"""Prompt asset routes (filesystem-backed)."""

from __future__ import annotations

from fastapi import APIRouter, Path, Request

from ..core.storage import Storage
from ..schemas import (
    PromptCreateRequest,
    PromptItem,
    PromptListResponse,
)


router = APIRouter(prefix="/prompts", tags=["prompts"])


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
    record = storage.save_prompt(name=req.name, content=req.content, prompt_id=req.id)
    return PromptItem(**record)


@router.delete("/{prompt_id}", status_code=204)
def delete_prompt(prompt_id: str = Path(...), *, request: Request) -> None:
    storage: Storage = request.app.state.storage
    storage.delete_prompt(prompt_id)
    return None
