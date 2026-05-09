"""Parametric tests across SqliteProviderStore + InMemoryProviderStore."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.core.provider_store import (
    InMemoryProviderStore,
    ProviderNotFoundInStoreError,
    SqliteProviderStore,
)
from app.core.secret_box import SecretBox
from app.core.storage import Storage


@pytest.fixture
def sqlite_store(tmp_path: Path):
    db = tmp_path / "data" / "v.db"
    storage = Storage(db_path=db, prompts_dir=tmp_path / "prompts")
    box = SecretBox(key_file=tmp_path / "master.key", env={})
    store = SqliteProviderStore(conn=storage._conn, secret_box=box)
    yield store, storage
    storage.close()


@pytest.fixture
def memory_store():
    return InMemoryProviderStore()


def _all_stores(sqlite_store, memory_store):
    return [("sqlite", sqlite_store[0]), ("memory", memory_store)]


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
def test_upsert_and_get_config(kind, sqlite_store, memory_store):
    store = sqlite_store[0] if kind == "sqlite" else memory_store
    cfg = store.upsert_config("momo", base_url="https://m.invalid/v1")
    assert cfg.provider_id == "momo"
    assert cfg.base_url == "https://m.invalid/v1"
    assert cfg.default_key_id is None

    cfg2 = store.upsert_config("momo", default_model="t8-/gpt-image-2")
    assert cfg2.base_url == "https://m.invalid/v1"
    assert cfg2.default_model == "t8-/gpt-image-2"

    assert store.get_config("nonexistent") is None


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
def test_add_key_and_get_credentials(kind, sqlite_store, memory_store):
    store = sqlite_store[0] if kind == "sqlite" else memory_store
    meta = store.add_key("momo", "Default", {"api_key": "sk-test-..."})
    assert meta.label == "Default"
    assert meta.provider_id == "momo"

    creds = store.get_key_credentials("momo", meta.id)
    assert creds == {"api_key": "sk-test-..."}

    listed = store.list_keys("momo")
    assert len(listed) == 1
    assert listed[0].id == meta.id


def test_sqlite_keys_encrypted_on_disk(sqlite_store):
    store, storage = sqlite_store
    store.add_key("momo", "Default", {"api_key": "sk-test-secret-...."})
    row = storage._conn.execute(
        "SELECT encrypted_credentials FROM provider_keys"
    ).fetchone()
    assert row is not None
    blob = bytes(row["encrypted_credentials"])
    assert b"sk-test-secret" not in blob


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
def test_replace_models_and_list(kind, sqlite_store, memory_store):
    store = sqlite_store[0] if kind == "sqlite" else memory_store
    meta = store.add_key("momo", "Default", {"api_key": "sk-test-..."})

    store.replace_models("momo", meta.id, [("dall-e-3", None), ("t8-/x", "T8")])
    listed = store.list_models("momo", meta.id)
    assert {m.model_id for m in listed} == {"dall-e-3", "t8-/x"}

    # Replace again — old rows gone.
    store.replace_models("momo", meta.id, [("only-one", None)])
    listed2 = store.list_models("momo", meta.id)
    assert [m.model_id for m in listed2] == ["only-one"]


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
def test_delete_key_cascade_models(kind, sqlite_store, memory_store):
    store = sqlite_store[0] if kind == "sqlite" else memory_store
    meta = store.add_key("momo", "L", {"api_key": "sk-test-..."})
    store.replace_models("momo", meta.id, [("a", None), ("b", None)])

    assert store.delete_key("momo", meta.id) is True
    assert store.list_models("momo", meta.id) == []
    assert store.list_keys("momo") == []
    # Idempotent: delete again returns False.
    assert store.delete_key("momo", meta.id) is False


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
def test_delete_key_clears_default(kind, sqlite_store, memory_store):
    store = sqlite_store[0] if kind == "sqlite" else memory_store
    meta = store.add_key("momo", "L", {"api_key": "sk-test-..."})
    store.upsert_config("momo", base_url="https://m.invalid/v1", default_key_id=meta.id)
    store.delete_key("momo", meta.id)
    cfg = store.get_config("momo")
    assert cfg is not None
    assert cfg.default_key_id is None


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
def test_get_credentials_missing(kind, sqlite_store, memory_store):
    store = sqlite_store[0] if kind == "sqlite" else memory_store
    with pytest.raises(ProviderNotFoundInStoreError):
        store.get_key_credentials("momo", "nope")
