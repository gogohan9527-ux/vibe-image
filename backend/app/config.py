"""Configuration loading and validation.

Loads ``config/config.yaml`` from the project root, overlays ``VIBE_*``
environment variables (per :mod:`app.config_layers`), validates with
Pydantic, and exposes a cached ``get_config()`` for the rest of the app.

As of 2026-05-09 the legacy ``api:`` section is gone — credentials and
upstream URLs live in the ProviderStore (managed at runtime via the UI).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from .config_layers import apply_env_overrides


# Project root = three levels above this file: backend/app/config.py -> repo root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
CONFIG_PATH: Path = PROJECT_ROOT / "config" / "config.yaml"


class ServerConfig(BaseModel):
    host: str
    port: int = Field(gt=0, lt=65536)
    cors_origins: List[str] = Field(default_factory=list)


class ExecutorConfig(BaseModel):
    default_concurrency: int = Field(gt=0)
    default_queue_size: int = Field(gt=0)
    max_concurrency: int = Field(gt=0)
    max_queue_size: int = Field(gt=0)


class PathsConfig(BaseModel):
    images_dir: str
    prompts_dir: str
    database_path: str


class DefaultsConfig(BaseModel):
    request_timeout_seconds: int = Field(default=120, gt=0)
    # Cap for img2img reference-image uploads; see PRD §B.4 Addendum (II).
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)


# ---------- Storage backend (2026-05-11 Addendum §D) ----------
#
# Each provider sub-model carries its own credentials + addressing. Selected
# provider's required fields are validated by ``StorageConfig`` below; non-
# selected sub-models may be left at their defaults.

class AliyunStorageConfig(BaseModel):
    endpoint: str = ""
    bucket: str = ""
    access_key_id: str = ""
    access_key_secret: str = ""
    prefix: str = ""
    public_base_url: str = ""


class TencentStorageConfig(BaseModel):
    region: str = ""
    bucket: str = ""
    secret_id: str = ""
    secret_key: str = ""
    prefix: str = ""
    public_base_url: str = ""


class CloudflareStorageConfig(BaseModel):
    account_id: str = ""
    bucket: str = ""
    access_key_id: str = ""
    access_key_secret: str = ""
    prefix: str = ""
    public_base_url: str = ""


class AwsStorageConfig(BaseModel):
    region: str = ""
    bucket: str = ""
    # access_key_id may be empty — boto3 falls back to its default credential
    # chain (env, IAM role, etc.).
    access_key_id: str = ""
    access_key_secret: str = ""
    prefix: str = ""
    public_base_url: str = ""


class MinioStorageConfig(BaseModel):
    endpoint: str = ""
    bucket: str = ""
    access_key: str = ""
    secret_key: str = ""
    secure: bool = False
    prefix: str = ""
    public_base_url: str = ""


StorageBackendName = Literal["local", "aliyun", "tencent", "cloudflare", "aws", "minio"]


class StorageConfig(BaseModel):
    backend: StorageBackendName = "local"
    aliyun: AliyunStorageConfig = Field(default_factory=AliyunStorageConfig)
    tencent: TencentStorageConfig = Field(default_factory=TencentStorageConfig)
    cloudflare: CloudflareStorageConfig = Field(default_factory=CloudflareStorageConfig)
    aws: AwsStorageConfig = Field(default_factory=AwsStorageConfig)
    minio: MinioStorageConfig = Field(default_factory=MinioStorageConfig)

    @model_validator(mode="after")
    def _validate_selected_provider(self) -> "StorageConfig":
        """Ensure the selected provider's required fields are non-empty."""
        if self.backend == "local":
            return self

        required: list[tuple[str, str]] = []  # (dotted path, value)
        if self.backend == "aliyun":
            required = [
                ("aliyun.endpoint", self.aliyun.endpoint),
                ("aliyun.bucket", self.aliyun.bucket),
                ("aliyun.access_key_id", self.aliyun.access_key_id),
                ("aliyun.access_key_secret", self.aliyun.access_key_secret),
            ]
        elif self.backend == "tencent":
            required = [
                ("tencent.region", self.tencent.region),
                ("tencent.bucket", self.tencent.bucket),
                ("tencent.secret_id", self.tencent.secret_id),
                ("tencent.secret_key", self.tencent.secret_key),
            ]
        elif self.backend == "cloudflare":
            required = [
                ("cloudflare.account_id", self.cloudflare.account_id),
                ("cloudflare.bucket", self.cloudflare.bucket),
                ("cloudflare.access_key_id", self.cloudflare.access_key_id),
                ("cloudflare.access_key_secret", self.cloudflare.access_key_secret),
            ]
        elif self.backend == "aws":
            # access_key_id allowed to be empty (boto3 default chain).
            required = [
                ("aws.region", self.aws.region),
                ("aws.bucket", self.aws.bucket),
            ]
        elif self.backend == "minio":
            required = [
                ("minio.endpoint", self.minio.endpoint),
                ("minio.bucket", self.minio.bucket),
                ("minio.access_key", self.minio.access_key),
                ("minio.secret_key", self.minio.secret_key),
            ]

        missing = [path for path, value in required if not value]
        if missing:
            raise ValueError(
                f"storage.backend={self.backend!r} requires non-empty: "
                + ", ".join(missing)
            )
        return self


class AppConfig(BaseModel):
    mode: Literal["normal", "demo"] = "normal"
    secret_key: Optional[str] = None
    server: ServerConfig
    executor: ExecutorConfig
    paths: PathsConfig
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    storage: StorageConfig = Field(default_factory=lambda: StorageConfig(backend="local"))

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
    def images_temp_dir(self) -> Path:
        """Sub-directory under ``images_dir`` for img2img reference uploads."""
        return self.images_dir / "temp"

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
            "Copy config/config.example.yaml to config/config.yaml."
        )
    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Config file is not valid YAML: {exc}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("Config file must be a YAML mapping at the top level.")

    # Drop the legacy ``api:`` section silently if present. This is a one-shot
    # migration aid — users see a UI prompt to configure providers instead.
    raw.pop("api", None)

    overlaid = apply_env_overrides(raw, os.environ)

    try:
        return AppConfig.model_validate(overlaid)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from exc


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config()


def reset_config_cache() -> None:
    """Clear the cached config (used by tests)."""
    get_config.cache_clear()
