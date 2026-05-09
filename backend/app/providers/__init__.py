"""Provider registry. Imports concrete providers and exposes them by id."""

from __future__ import annotations

from .base import CredField, HttpCall, ModelInfo, ParsedResult, Provider
from .momo import MomoProvider


PROVIDER_REGISTRY: dict[str, Provider] = {
    "momo": MomoProvider(),
}


__all__ = [
    "CredField",
    "HttpCall",
    "ModelInfo",
    "ParsedResult",
    "Provider",
    "MomoProvider",
    "PROVIDER_REGISTRY",
]
