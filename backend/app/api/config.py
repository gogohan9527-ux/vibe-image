"""Runtime configuration endpoints used by the frontend.

- ``GET /api/config/status``: tells the frontend whether the server already
  has an api_key configured (via env var or yaml). When false, the frontend
  prompts the user for credentials and submits them encrypted with each task.
- ``GET /api/config/public-key``: returns the ephemeral RSA public key (PEM)
  the frontend uses to encrypt the api_key.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..config import AppConfig
from ..core.crypto import CryptoManager


router = APIRouter(prefix="/config", tags=["config"])


class ConfigStatusResponse(BaseModel):
    api_key_configured: bool
    base_url: str


class PublicKeyResponse(BaseModel):
    public_key_pem: str


@router.get("/status", response_model=ConfigStatusResponse)
def get_status(request: Request) -> ConfigStatusResponse:
    config: AppConfig = request.app.state.config
    return ConfigStatusResponse(
        api_key_configured=bool(config.api.api_key),
        base_url=config.api.base_url,
    )


@router.get("/public-key", response_model=PublicKeyResponse)
def get_public_key(request: Request) -> PublicKeyResponse:
    crypto: CryptoManager = request.app.state.crypto
    return PublicKeyResponse(public_key_pem=crypto.public_key_pem())
