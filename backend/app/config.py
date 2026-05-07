"""Configuration loading and validation.

Loads ``config/config.yaml`` from the project root, validates with Pydantic,
and exposes a cached ``get_config()`` for the rest of the app.

The api_key is never logged or surfaced in error messages.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


# Project root = three levels above this file: backend/app/config.py -> repo root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
CONFIG_PATH: Path = PROJECT_ROOT / "config" / "config.yaml"


class ApiConfig(BaseModel):
    base_url: str
    api_key: str
    default_model: str
    default_size: str
    default_quality: str
    default_format: str
    request_timeout_seconds: int = Field(gt=0)

    @field_validator("api_key")
    @classmethod
    def _api_key_not_placeholder(cls, v: str) -> str:
        if not v or v.strip() == "" or v.strip() == "REPLACE_ME":
            raise ValueError("api_key is not configured (still REPLACE_ME)")
        return v


class ServerConfig(BaseModel):
    host: str
    port: int = Field(gt=0, lt=65536)
    cors_origins: List[str] = Field(default_factory=list)


class ExecutorConfig(BaseModel):
    default_concurrency: int = Field(gt=0)
    default_queue_size: int = Field(gt=0)
    max_concurrency: int = Field(gt=0)
    max_queue_size: int = Field(gt=0)

    @field_validator("default_concurrency")
    @classmethod
    def _default_concurrency_not_negative(cls, v: int) -> int:
        return v


class PathsConfig(BaseModel):
    images_dir: str
    prompts_dir: str
    database_path: str


class AppConfig(BaseModel):
    api: ApiConfig
    server: ServerConfig
    executor: ExecutorConfig
    paths: PathsConfig

    def resolve_path(self, relative_or_absolute: str) -> Path:
        """Resolve a path from config relative to the project root."""
        p = Path(relative_or_absolute)
        if p.is_absolute():
            return p
        return (PROJECT_ROOT / p).resolve()

    @property
    def images_dir(self) -> Path:
        return self.resolve_path(self.paths.images_dir)

    @property
    def prompts_dir(self) -> Path:
        return self.resolve_path(self.paths.prompts_dir)

    @property
    def database_path(self) -> Path:
        return self.resolve_path(self.paths.database_path)


class ConfigError(RuntimeError):
    """Raised when config cannot be loaded or validated."""


def _format_validation_error(err: ValidationError) -> str:
    lines = ["Config validation failed. Missing or invalid fields:"]
    for e in err.errors():
        loc = ".".join(str(part) for part in e.get("loc", ()))
        msg = e.get("msg", "")
        # Avoid printing values that might leak secrets — only the field path + reason.
        lines.append(f"  - {loc}: {msg}")
    return "\n".join(lines)


def load_config(path: Path | None = None) -> AppConfig:
    cfg_path = path or CONFIG_PATH
    if not cfg_path.exists():
        raise ConfigError(
            f"Config file not found at {cfg_path}. "
            "Copy config/config.example.yaml to config/config.yaml and fill in api_key."
        )
    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Config file is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("Config file must be a YAML mapping at the top level.")
    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from exc


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config()


def reset_config_cache() -> None:
    """Clear the cached config (used by tests)."""
    get_config.cache_clear()
