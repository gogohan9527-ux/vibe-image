"""Three-layer configuration overlay: yaml -> env -> validated AppConfig.

Pure helpers used by ``app.config.load_config``. The mapping rule matches
PRD §A.2.5: ``VIBE_<SECTION>_<KEY>`` (uppercase, single underscore between
section and key) maps to a nested ``section.key`` lower-case path. A handful
of fields use bespoke handling:

* ``VIBE_MODE`` -> top-level ``mode``
* ``VIBE_SECRET_KEY`` -> top-level ``secret_key``
* ``VIBE_SERVER_CORS_ORIGINS`` is a CSV list (split on ``,``, strip
  whitespace, drop empties).

Unknown ``VIBE_*`` env vars are silently ignored so future additions can be
rolled out without breaking existing deployments.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping


# yaml-path -> env-name. Order does not matter; we iterate the env to apply.
_ENV_TO_PATH: dict[str, tuple[str, ...]] = {
    "VIBE_MODE": ("mode",),
    "VIBE_SECRET_KEY": ("secret_key",),
    "VIBE_SERVER_HOST": ("server", "host"),
    "VIBE_SERVER_PORT": ("server", "port"),
    "VIBE_SERVER_CORS_ORIGINS": ("server", "cors_origins"),
    "VIBE_EXECUTOR_DEFAULT_CONCURRENCY": ("executor", "default_concurrency"),
    "VIBE_EXECUTOR_DEFAULT_QUEUE_SIZE": ("executor", "default_queue_size"),
    "VIBE_EXECUTOR_MAX_CONCURRENCY": ("executor", "max_concurrency"),
    "VIBE_EXECUTOR_MAX_QUEUE_SIZE": ("executor", "max_queue_size"),
    "VIBE_PATHS_IMAGES_DIR": ("paths", "images_dir"),
    "VIBE_PATHS_DATABASE_PATH": ("paths", "database_path"),
    "VIBE_PATHS_PROMPTS_DIR": ("paths", "prompts_dir"),
    "VIBE_DEFAULTS_REQUEST_TIMEOUT_SECONDS": ("defaults", "request_timeout_seconds"),
    "VIBE_DEFAULTS_MAX_UPLOAD_BYTES": ("defaults", "max_upload_bytes"),
    # --- storage (2026-05-11) ---
    "VIBE_STORAGE_BACKEND": ("storage", "backend"),
    "VIBE_STORAGE_ALIYUN_ENDPOINT": ("storage", "aliyun", "endpoint"),
    "VIBE_STORAGE_ALIYUN_BUCKET": ("storage", "aliyun", "bucket"),
    "VIBE_STORAGE_ALIYUN_ACCESS_KEY_ID": ("storage", "aliyun", "access_key_id"),
    "VIBE_STORAGE_ALIYUN_ACCESS_KEY_SECRET": ("storage", "aliyun", "access_key_secret"),
    "VIBE_STORAGE_ALIYUN_PREFIX": ("storage", "aliyun", "prefix"),
    "VIBE_STORAGE_ALIYUN_PUBLIC_BASE_URL": ("storage", "aliyun", "public_base_url"),
    "VIBE_STORAGE_TENCENT_REGION": ("storage", "tencent", "region"),
    "VIBE_STORAGE_TENCENT_BUCKET": ("storage", "tencent", "bucket"),
    "VIBE_STORAGE_TENCENT_SECRET_ID": ("storage", "tencent", "secret_id"),
    "VIBE_STORAGE_TENCENT_SECRET_KEY": ("storage", "tencent", "secret_key"),
    "VIBE_STORAGE_TENCENT_PREFIX": ("storage", "tencent", "prefix"),
    "VIBE_STORAGE_TENCENT_PUBLIC_BASE_URL": ("storage", "tencent", "public_base_url"),
    "VIBE_STORAGE_CLOUDFLARE_ACCOUNT_ID": ("storage", "cloudflare", "account_id"),
    "VIBE_STORAGE_CLOUDFLARE_BUCKET": ("storage", "cloudflare", "bucket"),
    "VIBE_STORAGE_CLOUDFLARE_ACCESS_KEY_ID": ("storage", "cloudflare", "access_key_id"),
    "VIBE_STORAGE_CLOUDFLARE_ACCESS_KEY_SECRET": ("storage", "cloudflare", "access_key_secret"),
    "VIBE_STORAGE_CLOUDFLARE_PREFIX": ("storage", "cloudflare", "prefix"),
    "VIBE_STORAGE_CLOUDFLARE_PUBLIC_BASE_URL": ("storage", "cloudflare", "public_base_url"),
    "VIBE_STORAGE_AWS_REGION": ("storage", "aws", "region"),
    "VIBE_STORAGE_AWS_BUCKET": ("storage", "aws", "bucket"),
    "VIBE_STORAGE_AWS_ACCESS_KEY_ID": ("storage", "aws", "access_key_id"),
    "VIBE_STORAGE_AWS_ACCESS_KEY_SECRET": ("storage", "aws", "access_key_secret"),
    "VIBE_STORAGE_AWS_PREFIX": ("storage", "aws", "prefix"),
    "VIBE_STORAGE_AWS_PUBLIC_BASE_URL": ("storage", "aws", "public_base_url"),
    "VIBE_STORAGE_MINIO_ENDPOINT": ("storage", "minio", "endpoint"),
    "VIBE_STORAGE_MINIO_BUCKET": ("storage", "minio", "bucket"),
    "VIBE_STORAGE_MINIO_ACCESS_KEY": ("storage", "minio", "access_key"),
    "VIBE_STORAGE_MINIO_SECRET_KEY": ("storage", "minio", "secret_key"),
    "VIBE_STORAGE_MINIO_SECURE": ("storage", "minio", "secure"),
    "VIBE_STORAGE_MINIO_PREFIX": ("storage", "minio", "prefix"),
    "VIBE_STORAGE_MINIO_PUBLIC_BASE_URL": ("storage", "minio", "public_base_url"),
}

_LIST_ENV_VARS = {"VIBE_SERVER_CORS_ORIGINS"}
_INT_ENV_VARS = {
    "VIBE_SERVER_PORT",
    "VIBE_EXECUTOR_DEFAULT_CONCURRENCY",
    "VIBE_EXECUTOR_DEFAULT_QUEUE_SIZE",
    "VIBE_EXECUTOR_MAX_CONCURRENCY",
    "VIBE_EXECUTOR_MAX_QUEUE_SIZE",
    "VIBE_DEFAULTS_REQUEST_TIMEOUT_SECONDS",
    "VIBE_DEFAULTS_MAX_UPLOAD_BYTES",
}
_BOOL_ENV_VARS = {"VIBE_STORAGE_MINIO_SECURE"}


def _set_at_path(target: dict, path: tuple[str, ...], value: Any) -> None:
    cursor: dict = target
    for key in path[:-1]:
        nxt = cursor.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[key] = nxt
        cursor = nxt
    cursor[path[-1]] = value


def _coerce(env_name: str, raw: str) -> Any:
    if env_name in _LIST_ENV_VARS:
        return [item.strip() for item in raw.split(",") if item.strip()]
    if env_name in _INT_ENV_VARS:
        try:
            return int(raw)
        except ValueError:
            # Leave as-is; pydantic will surface a clearer validation error.
            return raw
    if env_name in _BOOL_ENV_VARS:
        lowered = raw.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
        # Leave as-is; pydantic will surface a clearer validation error.
        return raw
    return raw


def apply_env_overrides(yaml_dict: dict, env: Mapping[str, str]) -> dict:
    """Return a NEW dict with env-var values overlaying yaml.

    The input dict is not mutated. Only env vars listed in the mapping are
    considered; everything else is ignored. Values are coerced where the
    target field is known to be int or list (CSV).
    """
    if not isinstance(yaml_dict, dict):
        raise TypeError("yaml_dict must be a mapping")
    result = copy.deepcopy(yaml_dict)
    for env_name, path in _ENV_TO_PATH.items():
        if env_name not in env:
            continue
        raw = env[env_name]
        # Empty string means "do not override" — keep yaml value. This lets
        # docker-compose default-empty (`${VIBE_X:-}`) be a no-op.
        if raw == "":
            continue
        _set_at_path(result, path, _coerce(env_name, raw))
    return result
