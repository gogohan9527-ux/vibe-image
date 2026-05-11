"""Unit tests for the local storage backend (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import StorageConfig
from app.core.storage_backend import (
    LocalBackend,
    StorageError,
    build_storage_backend,
    to_url,
)


def test_local_save_writes_file(tmp_path: Path):
    backend = LocalBackend(images_dir=tmp_path)
    backend.save("generated_abc.jpeg", b"PAYLOAD")
    assert (tmp_path / "generated_abc.jpeg").read_bytes() == b"PAYLOAD"


def test_local_save_creates_subdirectory_for_slashed_key(tmp_path: Path):
    backend = LocalBackend(images_dir=tmp_path)
    backend.save("temp/abcdef.png", b"PNGDATA", content_type="image/png")
    target = tmp_path / "temp" / "abcdef.png"
    assert target.read_bytes() == b"PNGDATA"


def test_local_url_uses_images_prefix_with_forward_slashes(tmp_path: Path):
    backend = LocalBackend(images_dir=tmp_path)
    assert backend.url("generated_xyz.jpeg") == "/images/generated_xyz.jpeg"
    assert backend.url("temp/abc.png") == "/images/temp/abc.png"


def test_local_delete_idempotent_on_missing(tmp_path: Path):
    backend = LocalBackend(images_dir=tmp_path)
    # Must not raise on a missing key.
    backend.delete("missing.jpeg")


def test_local_delete_removes_existing_file(tmp_path: Path):
    backend = LocalBackend(images_dir=tmp_path)
    backend.save("hello.txt", b"hi")
    backend.delete("hello.txt")
    assert not (tmp_path / "hello.txt").exists()
    # Second delete is still a no-op.
    backend.delete("hello.txt")


def test_local_exists_true_and_false(tmp_path: Path):
    backend = LocalBackend(images_dir=tmp_path)
    assert backend.exists("nope.jpeg") is False
    backend.save("there.jpeg", b"x")
    assert backend.exists("there.jpeg") is True


def test_build_storage_backend_local_returns_local(tmp_path: Path):
    cfg = StorageConfig(backend="local")
    backend = build_storage_backend(cfg, images_dir=tmp_path)
    assert isinstance(backend, LocalBackend)


def test_build_storage_backend_local_smoke(tmp_path: Path):
    # The factory's local branch must continue to return a LocalBackend
    # regardless of any Lane-P cloud wiring landing on the other branches.
    backend = build_storage_backend(StorageConfig(backend="local"), images_dir=tmp_path)
    assert isinstance(backend, LocalBackend)
    # And LocalBackend itself behaves correctly through the factory.
    backend.save("smoke.txt", b"hi")
    assert (tmp_path / "smoke.txt").read_bytes() == b"hi"


def test_storage_error_carries_fields():
    cause = ValueError("boom")
    err = StorageError(provider="aliyun", op="save", key="generated_x.jpeg", cause=cause)
    assert err.provider == "aliyun"
    assert err.op == "save"
    assert err.key == "generated_x.jpeg"
    assert err.cause is cause
    assert "aliyun" in str(err)
    assert "save" in str(err)


def test_storage_error_allows_none_key():
    err = StorageError(provider="aws", op="url", key=None)
    assert err.key is None
    # Should not crash str() with a missing key.
    assert "aws" in str(err)


# ---------- to_url helper (S11) ----------


def test_to_url_returns_none_for_empty(tmp_path: Path):
    backend = LocalBackend(images_dir=tmp_path)
    assert to_url(backend, None) is None
    assert to_url(backend, "") is None


def test_to_url_passes_through_http_urls(tmp_path: Path):
    backend = LocalBackend(images_dir=tmp_path)
    assert to_url(backend, "https://cdn.example/x.jpeg") == "https://cdn.example/x.jpeg"
    assert to_url(backend, "http://cdn.example/x.jpeg") == "http://cdn.example/x.jpeg"


def test_to_url_passes_through_images_relative(tmp_path: Path):
    backend = LocalBackend(images_dir=tmp_path)
    assert to_url(backend, "/images/generated_x.jpeg") == "/images/generated_x.jpeg"


def test_to_url_routes_bare_key_through_backend(tmp_path: Path):
    backend = LocalBackend(images_dir=tmp_path)
    assert to_url(backend, "generated_abc.jpeg") == "/images/generated_abc.jpeg"
    assert to_url(backend, "temp/abc.png") == "/images/temp/abc.png"
