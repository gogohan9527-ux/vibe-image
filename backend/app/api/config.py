"""Runtime configuration endpoints used by the frontend.

- ``GET /api/config/status``: returns the run mode plus a coarse
  any-provider-configured flag the UI uses to decide whether to nudge the
  user toward ``/providers``.
- ``GET /api/config/public-key``: returns the ephemeral RSA public key
  (PEM) the frontend uses to encrypt provider credentials.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..config import AppConfig
from ..core.crypto import CryptoManager
from ..core.provider_store import ProviderStore
from ..providers import PROVIDER_REGISTRY
from ..schemas import ConfigStatusResponse


router = APIRouter(prefix="/config", tags=["config"])


class PublicKeyResponse(BaseModel):
    public_key_pem: str


@router.get("/status", response_model=ConfigStatusResponse)
def get_status(request: Request) -> ConfigStatusResponse:
    config: AppConfig = request.app.state.config
    store: ProviderStore = request.app.state.provider_store
    any_configured = any(
        store.list_keys(pid) for pid in PROVIDER_REGISTRY.keys()
    )
    return ConfigStatusResponse(
        mode=config.mode, any_provider_configured=any_configured
    )


@router.get("/public-key", response_model=PublicKeyResponse)
def get_public_key(request: Request) -> PublicKeyResponse:
    crypto: CryptoManager = request.app.state.crypto
    return PublicKeyResponse(public_key_pem=crypto.public_key_pem())
