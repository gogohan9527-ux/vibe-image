"""Provider configuration / key / model storage.

Two implementations share the same Protocol:

* ``SqliteProviderStore`` persists everything; credentials are stored as
  AES-256-GCM ciphertext (``SecretBox``) in the BLOB column. Only the store
  ever holds plaintext, and only inside ``add_key`` / ``get_key_credentials``
  call frames.
* ``InMemoryProviderStore`` keeps state in three plain dicts; all data is
  lost when the process exits. Used by ``demo`` mode.

The HTTP layer always uses the meta types (no plaintext leaves the store).
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Iterable, Optional, Protocol

from pydantic import BaseModel

from .secret_box import SecretBox


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- Pydantic models ----------


class ProviderConfig(BaseModel):
    provider_id: str
    base_url: str
    default_model: Optional[str] = None
    default_key_id: Optional[str] = None
    updated_at: str


class ProviderKey(BaseModel):
    """Includes the encrypted blob — for internal use only."""

    id: str
    provider_id: str
    label: str
    encrypted_credentials: bytes
    created_at: str

    model_config = {"arbitrary_types_allowed": True}


class ProviderKeyMeta(BaseModel):
    """Safe to expose over the API (no credential bytes)."""

    id: str
    provider_id: str
    label: str
    created_at: str


class ProviderModel(BaseModel):
    provider_id: str
    key_id: str
    model_id: str
    display_name: Optional[str] = None
    fetched_at: str


class ProviderNotFoundInStoreError(LookupError):
    pass


# ---------- Protocol ----------


class ProviderStore(Protocol):
    def get_config(self, provider_id: str) -> Optional[ProviderConfig]: ...

    def upsert_config(
        self,
        provider_id: str,
        *,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        default_key_id: Optional[str] = None,
    ) -> ProviderConfig: ...

    def list_keys(self, provider_id: str) -> list[ProviderKeyMeta]: ...

    def add_key(
        self,
        provider_id: str,
        label: str,
        creds_plain: dict[str, str],
    ) -> ProviderKeyMeta: ...

    def get_key_credentials(self, provider_id: str, key_id: str) -> dict[str, str]: ...

    def delete_key(self, provider_id: str, key_id: str) -> bool: ...

    def list_models(
        self, provider_id: str, key_id: str
    ) -> list[ProviderModel]: ...

    def replace_models(
        self,
        provider_id: str,
        key_id: str,
        models: Iterable[tuple[str, Optional[str]]],
    ) -> list[ProviderModel]: ...


# ---------- Sqlite implementation ----------


def _encode_creds(creds: dict[str, str]) -> bytes:
    # Stable ordering so the same payload encodes to the same plaintext.
    import json

    return json.dumps(creds, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _decode_creds(plaintext: bytes) -> dict[str, str]:
    import json

    obj = json.loads(plaintext.decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("decoded credentials are not an object")
    return {str(k): str(v) for k, v in obj.items()}


class SqliteProviderStore:
    def __init__(self, conn: sqlite3.Connection, secret_box: SecretBox) -> None:
        self._conn = conn
        self._box = secret_box
        self._lock = threading.RLock()

    # ---------- config ----------

    def get_config(self, provider_id: str) -> Optional[ProviderConfig]:
        with self._lock:
            row = self._conn.execute(
                "SELECT provider_id, base_url, default_model, default_key_id, updated_at "
                "FROM provider_configs WHERE provider_id = ?",
                (provider_id,),
            ).fetchone()
        if row is None:
            return None
        return ProviderConfig(**dict(row))

    def upsert_config(
        self,
        provider_id: str,
        *,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        default_key_id: Optional[str] = None,
    ) -> ProviderConfig:
        with self._lock:
            existing = self.get_config(provider_id)
            now = _utcnow_iso()
            if existing is None:
                if base_url is None:
                    raise ValueError(
                        "base_url is required when creating a new provider config"
                    )
                self._conn.execute(
                    "INSERT INTO provider_configs "
                    "(provider_id, base_url, default_model, default_key_id, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (provider_id, base_url, default_model, default_key_id, now),
                )
            else:
                new_base = base_url if base_url is not None else existing.base_url
                new_model = (
                    default_model
                    if default_model is not None
                    else existing.default_model
                )
                new_key = (
                    default_key_id
                    if default_key_id is not None
                    else existing.default_key_id
                )
                self._conn.execute(
                    "UPDATE provider_configs SET base_url=?, default_model=?, "
                    "default_key_id=?, updated_at=? WHERE provider_id=?",
                    (new_base, new_model, new_key, now, provider_id),
                )
            return self.get_config(provider_id)  # type: ignore[return-value]

    # ---------- keys ----------

    def list_keys(self, provider_id: str) -> list[ProviderKeyMeta]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, provider_id, label, created_at FROM provider_keys "
                "WHERE provider_id = ? ORDER BY created_at ASC",
                (provider_id,),
            ).fetchall()
        return [ProviderKeyMeta(**dict(r)) for r in rows]

    def add_key(
        self,
        provider_id: str,
        label: str,
        creds_plain: dict[str, str],
    ) -> ProviderKeyMeta:
        kid = str(uuid.uuid4())
        blob = self._box.encrypt(_encode_creds(creds_plain))
        now = _utcnow_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO provider_keys "
                "(id, provider_id, label, encrypted_credentials, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (kid, provider_id, label, blob, now),
            )
        return ProviderKeyMeta(
            id=kid, provider_id=provider_id, label=label, created_at=now
        )

    def get_key_credentials(self, provider_id: str, key_id: str) -> dict[str, str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT encrypted_credentials FROM provider_keys "
                "WHERE id = ? AND provider_id = ?",
                (key_id, provider_id),
            ).fetchone()
        if row is None:
            raise ProviderNotFoundInStoreError(f"key {key_id} not found")
        plaintext = self._box.decrypt(bytes(row["encrypted_credentials"]))
        return _decode_creds(plaintext)

    def delete_key(self, provider_id: str, key_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM provider_keys WHERE id = ? AND provider_id = ?",
                (key_id, provider_id),
            )
            removed = cur.rowcount > 0
            # Cascade: drop cached models for this key.
            self._conn.execute(
                "DELETE FROM provider_models WHERE provider_id = ? AND key_id = ?",
                (provider_id, key_id),
            )
            # If it was the default key on the config, clear it.
            self._conn.execute(
                "UPDATE provider_configs SET default_key_id = NULL "
                "WHERE provider_id = ? AND default_key_id = ?",
                (provider_id, key_id),
            )
        return removed

    # ---------- models ----------

    def list_models(self, provider_id: str, key_id: str) -> list[ProviderModel]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT provider_id, key_id, model_id, display_name, fetched_at "
                "FROM provider_models WHERE provider_id = ? AND key_id = ? "
                "ORDER BY model_id ASC",
                (provider_id, key_id),
            ).fetchall()
        return [ProviderModel(**dict(r)) for r in rows]

    def replace_models(
        self,
        provider_id: str,
        key_id: str,
        models: Iterable[tuple[str, Optional[str]]],
    ) -> list[ProviderModel]:
        now = _utcnow_iso()
        with self._lock:
            self._conn.execute(
                "DELETE FROM provider_models WHERE provider_id = ? AND key_id = ?",
                (provider_id, key_id),
            )
            for model_id, display_name in models:
                self._conn.execute(
                    "INSERT INTO provider_models "
                    "(provider_id, key_id, model_id, display_name, fetched_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (provider_id, key_id, model_id, display_name, now),
                )
        return self.list_models(provider_id, key_id)


# ---------- In-memory implementation ----------


class InMemoryProviderStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._configs: dict[str, ProviderConfig] = {}
        # (provider_id, key_id) -> (ProviderKeyMeta, plaintext_creds)
        self._keys: dict[tuple[str, str], tuple[ProviderKeyMeta, dict[str, str]]] = {}
        # (provider_id, key_id) -> list[ProviderModel]
        self._models: dict[tuple[str, str], list[ProviderModel]] = {}

    def get_config(self, provider_id: str) -> Optional[ProviderConfig]:
        with self._lock:
            return self._configs.get(provider_id)

    def upsert_config(
        self,
        provider_id: str,
        *,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        default_key_id: Optional[str] = None,
    ) -> ProviderConfig:
        with self._lock:
            existing = self._configs.get(provider_id)
            if existing is None:
                if base_url is None:
                    raise ValueError(
                        "base_url is required when creating a new provider config"
                    )
                cfg = ProviderConfig(
                    provider_id=provider_id,
                    base_url=base_url,
                    default_model=default_model,
                    default_key_id=default_key_id,
                    updated_at=_utcnow_iso(),
                )
            else:
                cfg = ProviderConfig(
                    provider_id=provider_id,
                    base_url=base_url if base_url is not None else existing.base_url,
                    default_model=(
                        default_model
                        if default_model is not None
                        else existing.default_model
                    ),
                    default_key_id=(
                        default_key_id
                        if default_key_id is not None
                        else existing.default_key_id
                    ),
                    updated_at=_utcnow_iso(),
                )
            self._configs[provider_id] = cfg
            return cfg

    def list_keys(self, provider_id: str) -> list[ProviderKeyMeta]:
        with self._lock:
            metas = [
                meta
                for (pid, _), (meta, _) in self._keys.items()
                if pid == provider_id
            ]
        metas.sort(key=lambda m: m.created_at)
        return metas

    def add_key(
        self,
        provider_id: str,
        label: str,
        creds_plain: dict[str, str],
    ) -> ProviderKeyMeta:
        kid = str(uuid.uuid4())
        meta = ProviderKeyMeta(
            id=kid, provider_id=provider_id, label=label, created_at=_utcnow_iso()
        )
        with self._lock:
            self._keys[(provider_id, kid)] = (meta, dict(creds_plain))
        return meta

    def get_key_credentials(self, provider_id: str, key_id: str) -> dict[str, str]:
        with self._lock:
            entry = self._keys.get((provider_id, key_id))
        if entry is None:
            raise ProviderNotFoundInStoreError(f"key {key_id} not found")
        return dict(entry[1])

    def delete_key(self, provider_id: str, key_id: str) -> bool:
        with self._lock:
            removed = self._keys.pop((provider_id, key_id), None) is not None
            self._models.pop((provider_id, key_id), None)
            cfg = self._configs.get(provider_id)
            if cfg is not None and cfg.default_key_id == key_id:
                self._configs[provider_id] = cfg.model_copy(
                    update={"default_key_id": None, "updated_at": _utcnow_iso()}
                )
        return removed

    def list_models(self, provider_id: str, key_id: str) -> list[ProviderModel]:
        with self._lock:
            return list(self._models.get((provider_id, key_id), []))

    def replace_models(
        self,
        provider_id: str,
        key_id: str,
        models: Iterable[tuple[str, Optional[str]]],
    ) -> list[ProviderModel]:
        now = _utcnow_iso()
        items = [
            ProviderModel(
                provider_id=provider_id,
                key_id=key_id,
                model_id=model_id,
                display_name=display_name,
                fetched_at=now,
            )
            for model_id, display_name in models
        ]
        items.sort(key=lambda m: m.model_id)
        with self._lock:
            self._models[(provider_id, key_id)] = items
        return list(items)
