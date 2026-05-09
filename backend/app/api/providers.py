"""Provider configuration / key / model management endpoints.

All routes resolve a provider via ``PROVIDER_REGISTRY``; missing ids return
``unknown_provider`` (400). Credentials are decrypted (RSA-OAEP) at the
boundary, validated against the provider's ``credential_fields``, and passed
to the store. The plaintext dict never leaves the request handler.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Path, Query, Request, Response, status
from pydantic import BaseModel

from ..config import AppConfig
from ..core.crypto import CryptoManager
from ..core.provider_store import (
    ProviderNotFoundInStoreError,
    ProviderStore,
)
from ..errors import (
    CredentialDecryptError,
    InvalidCredentialsError,
    KeyNotFoundError,
    UnknownProviderError,
    UpstreamError,
)
from ..providers import PROVIDER_REGISTRY
from ..providers.base import Provider
from ..schemas import (
    AddKeyRequest,
    CredFieldOut,
    ProviderConfigOut,
    ProviderKeyListResponse,
    ProviderKeyMeta,
    ProviderListResponse,
    ProviderModelListResponse,
    ProviderModelMeta,
    ProviderSummary,
    RefreshModelsRequest,
    UpdateProviderConfigRequest,
)


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/providers", tags=["providers"])


def _provider(provider_id: str) -> Provider:
    p = PROVIDER_REGISTRY.get(provider_id)
    if p is None:
        raise UnknownProviderError(provider_id)
    return p


def _config_out(cfg) -> Optional[ProviderConfigOut]:
    if cfg is None:
        return None
    return ProviderConfigOut(
        base_url=cfg.base_url,
        default_model=cfg.default_model,
        default_key_id=cfg.default_key_id,
    )


def _summary(p: Provider, store: ProviderStore) -> ProviderSummary:
    cfg = store.get_config(p.id)
    keys = store.list_keys(p.id)
    return ProviderSummary(
        id=p.id,
        display_name=p.display_name,
        default_base_url=p.default_base_url,
        credential_fields=[
            CredFieldOut(
                name=f.name, label=f.label, secret=f.secret, required=f.required
            )
            for f in p.credential_fields
        ],
        config=_config_out(cfg),
        key_count=len(keys),
        # Provider opts-in to img2img by setting the class attribute. Default
        # ``False`` so newly-added providers are inert until they implement
        # ``build_image_edit_request``.
        supports_image_input=bool(getattr(p, "supports_image_input", False)),
    )


def _model_meta(m) -> ProviderModelMeta:
    return ProviderModelMeta(
        id=m.model_id, display_name=m.display_name, fetched_at=m.fetched_at
    )


def _key_meta(k) -> ProviderKeyMeta:
    return ProviderKeyMeta(
        id=k.id, provider_id=k.provider_id, label=k.label, created_at=k.created_at
    )


def _resolve_base_url(p: Provider, store: ProviderStore) -> str:
    cfg = store.get_config(p.id)
    if cfg is not None and cfg.base_url:
        return cfg.base_url
    return p.default_base_url


def _refresh_models_for_key(
    p: Provider, store: ProviderStore, key_id: str, timeout: int
) -> list[ProviderModelMeta]:
    creds = store.get_key_credentials(p.id, key_id)
    base_url = _resolve_base_url(p, store)
    fetched = p.list_models(creds, base_url, timeout)
    rows = store.replace_models(
        p.id, key_id, [(m.id, m.display_name) for m in fetched]
    )
    return [_model_meta(r) for r in rows]


# ---------- routes ----------


@router.get("", response_model=ProviderListResponse)
def list_providers(request: Request) -> ProviderListResponse:
    store: ProviderStore = request.app.state.provider_store
    return ProviderListResponse(
        providers=[_summary(p, store) for p in PROVIDER_REGISTRY.values()]
    )


@router.put("/{provider_id}/config", response_model=ProviderConfigOut)
def put_config(
    req: UpdateProviderConfigRequest,
    provider_id: str = Path(...),
    *,
    request: Request,
) -> ProviderConfigOut:
    p = _provider(provider_id)
    store: ProviderStore = request.app.state.provider_store
    # First-time write: if the user hasn't supplied a base_url and the store
    # has nothing, fall back to the provider's default_base_url so the row
    # can be created.
    base_url = req.base_url
    if base_url is None and store.get_config(p.id) is None:
        base_url = p.default_base_url
    cfg = store.upsert_config(
        p.id,
        base_url=base_url,
        default_model=req.default_model,
        default_key_id=req.default_key_id,
    )
    return _config_out(cfg)  # type: ignore[return-value]


@router.get("/{provider_id}/keys", response_model=ProviderKeyListResponse)
def list_keys_route(
    provider_id: str = Path(...), *, request: Request
) -> ProviderKeyListResponse:
    p = _provider(provider_id)
    store: ProviderStore = request.app.state.provider_store
    return ProviderKeyListResponse(keys=[_key_meta(k) for k in store.list_keys(p.id)])


class AddKeyResponse(BaseModel):
    key: ProviderKeyMeta
    models: list[ProviderModelMeta]
    models_refresh_error: Optional[str] = None


@router.post(
    "/{provider_id}/keys", response_model=AddKeyResponse, status_code=201
)
def add_key_route(
    req: AddKeyRequest,
    provider_id: str = Path(...),
    *,
    request: Request,
) -> AddKeyResponse:
    p = _provider(provider_id)
    config: AppConfig = request.app.state.config
    crypto: CryptoManager = request.app.state.crypto
    store: ProviderStore = request.app.state.provider_store

    # Decrypt incoming ciphertext per field. Failures bubble up as
    # ``credential_decrypt_failed`` (400) via the global handler.
    plain = crypto.decrypt_dict(req.encrypted_credentials)

    # Validate against provider's required fields.
    missing = [
        f.name for f in p.credential_fields if f.required and not plain.get(f.name)
    ]
    if missing:
        raise InvalidCredentialsError(missing_fields=missing)

    # Normalize the dict to only declared fields (drops accidental extras).
    declared = {f.name for f in p.credential_fields}
    creds_clean = {k: v for k, v in plain.items() if k in declared}

    meta = store.add_key(p.id, req.label, creds_clean)

    # Best-effort refresh; errors are surfaced as a warning string but do
    # NOT roll back the key.
    refresh_error: Optional[str] = None
    models: list[ProviderModelMeta] = []
    try:
        models = _refresh_models_for_key(
            p, store, meta.id, config.defaults.request_timeout_seconds
        )
    except UpstreamError as exc:
        refresh_error = exc.message
        logger.warning(
            "models refresh failed after add_key for %s/%s: %s",
            p.id,
            meta.id,
            exc.message,
        )

    return AddKeyResponse(
        key=_key_meta(meta), models=models, models_refresh_error=refresh_error
    )


@router.delete("/{provider_id}/keys/{key_id}", status_code=204)
def delete_key_route(
    provider_id: str = Path(...),
    key_id: str = Path(...),
    *,
    request: Request,
) -> Response:
    p = _provider(provider_id)
    store: ProviderStore = request.app.state.provider_store
    removed = store.delete_key(p.id, key_id)
    if not removed:
        raise KeyNotFoundError(key_id, http_status=404)
    return Response(status_code=204)


@router.get("/{provider_id}/models", response_model=ProviderModelListResponse)
def get_models(
    provider_id: str = Path(...),
    key_id: str = Query(..., min_length=1),
    *,
    request: Request,
) -> ProviderModelListResponse:
    p = _provider(provider_id)
    store: ProviderStore = request.app.state.provider_store
    # Verify key exists for clearer error semantics.
    keys = {k.id for k in store.list_keys(p.id)}
    if key_id not in keys:
        raise KeyNotFoundError(key_id)
    rows = store.list_models(p.id, key_id)
    return ProviderModelListResponse(models=[_model_meta(m) for m in rows])


@router.post(
    "/{provider_id}/models/refresh", response_model=ProviderModelListResponse
)
def refresh_models(
    req: RefreshModelsRequest,
    provider_id: str = Path(...),
    *,
    request: Request,
) -> ProviderModelListResponse:
    p = _provider(provider_id)
    config: AppConfig = request.app.state.config
    store: ProviderStore = request.app.state.provider_store
    # Validate key existence.
    keys = {k.id for k in store.list_keys(p.id)}
    if req.key_id not in keys:
        raise KeyNotFoundError(req.key_id)
    try:
        models = _refresh_models_for_key(
            p, store, req.key_id, config.defaults.request_timeout_seconds
        )
    except ProviderNotFoundInStoreError as exc:
        raise KeyNotFoundError(req.key_id) from exc
    return ProviderModelListResponse(models=models)
