"""Tests for the migrate_to_oss script.

The storage backend is replaced with a MagicMock so no SDK / network is hit.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.scripts import migrate_to_oss as mod
from app.core.storage_backend import StorageError


# ---------- _looks_like_local_path ----------


@pytest.mark.parametrize(
    "image_path,expected",
    [
        ("/images/generated_abc.jpeg", True),
        ("/abs/path/foo.png", True),
        ("C:\\abs\\path\\foo.png", True),
        ("generated_abc.jpeg", True),
        ("temp/abc.png", True),
        ("https://cdn.example/x.jpeg", False),
        ("", False),
    ],
)
def test_looks_like_local_path(image_path, expected):
    assert mod._looks_like_local_path(image_path) is expected


# ---------- _resolve_local_file ----------


def test_resolve_local_file_absolute(tmp_path: Path):
    p = tmp_path / "x.jpg"
    assert mod._resolve_local_file(str(p), tmp_path / "images") == p


def test_resolve_local_file_images_prefix(tmp_path: Path):
    images = tmp_path / "images"
    assert mod._resolve_local_file("/images/foo/bar.png", images) == images / "foo" / "bar.png"


def test_resolve_local_file_relative(tmp_path: Path):
    images = tmp_path / "images"
    assert mod._resolve_local_file("generated_x.jpeg", images) == images / "generated_x.jpeg"


# ---------- _content_type_for ----------


def test_content_type_for_known_extensions(tmp_path: Path):
    assert mod._content_type_for(tmp_path / "x.jpg") == "image/jpeg"
    assert mod._content_type_for(tmp_path / "x.jpeg") == "image/jpeg"
    assert mod._content_type_for(tmp_path / "x.PNG") == "image/png"
    assert mod._content_type_for(tmp_path / "x.webp") == "image/webp"
    assert mod._content_type_for(tmp_path / "x.bin") == "application/octet-stream"


# ---------- _migrate end-to-end (with mock storage) ----------


def _make_db_with_rows(db_path: Path, rows: list[tuple[str, str]]) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, image_path TEXT)")
    conn.executemany("INSERT INTO tasks (id, image_path) VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


def _make_db_with_reference_rows(
    db_path: Path, rows: list[tuple[str, str | None, str | None]]
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE tasks ("
        "id TEXT PRIMARY KEY, image_path TEXT, "
        "input_image_path TEXT, input_image_paths TEXT)"
    )
    conn.executemany(
        "INSERT INTO tasks (id, image_path, input_image_path, input_image_paths) "
        "VALUES (?, NULL, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def _make_config(tmp_path: Path) -> SimpleNamespace:
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    db_path = tmp_path / "vibe.db"
    return SimpleNamespace(images_dir=images_dir, database_path=db_path)


def test_migrate_uploads_and_updates_db(tmp_path: Path):
    cfg = _make_config(tmp_path)
    _make_db_with_rows(
        cfg.database_path,
        [
            ("task-a", "/images/generated_a.jpeg"),
            ("task-b", "generated_b.png"),
        ],
    )
    (cfg.images_dir / "generated_a.jpeg").write_bytes(b"AAAA")
    (cfg.images_dir / "generated_b.png").write_bytes(b"BBBB")

    storage = MagicMock()
    storage.exists.return_value = False

    stats = mod._migrate(cfg, storage, dry_run=False, limit=None)

    assert stats.scanned == 2
    assert stats.migrated == 2
    assert stats.skipped_already == 0
    assert stats.failed == 0
    assert storage.save.call_count == 2

    # DB rows now hold bare keys.
    conn = sqlite3.connect(str(cfg.database_path))
    rows = dict(conn.execute("SELECT id, image_path FROM tasks"))
    conn.close()
    assert rows == {"task-a": "generated_a.jpeg", "task-b": "generated_b.png"}


def test_migrate_dry_run_does_not_call_save(tmp_path: Path):
    cfg = _make_config(tmp_path)
    _make_db_with_rows(cfg.database_path, [("t1", "generated_x.jpeg")])
    (cfg.images_dir / "generated_x.jpeg").write_bytes(b"X")

    storage = MagicMock()
    storage.exists.return_value = False

    stats = mod._migrate(cfg, storage, dry_run=True, limit=None)
    assert stats.migrated == 1
    storage.save.assert_not_called()

    conn = sqlite3.connect(str(cfg.database_path))
    (path,) = conn.execute("SELECT image_path FROM tasks WHERE id='t1'").fetchone()
    conn.close()
    # DB unchanged.
    assert path == "generated_x.jpeg"


def test_migrate_skips_missing_local_files(tmp_path: Path):
    cfg = _make_config(tmp_path)
    _make_db_with_rows(cfg.database_path, [("gone", "generated_missing.jpeg")])
    # Note: no file written on disk.
    storage = MagicMock()
    storage.exists.return_value = False

    stats = mod._migrate(cfg, storage, dry_run=False, limit=None)
    assert stats.scanned == 1
    assert stats.skipped_missing == 1
    assert stats.migrated == 0
    storage.save.assert_not_called()


def test_migrate_skips_when_already_in_oss(tmp_path: Path):
    cfg = _make_config(tmp_path)
    _make_db_with_rows(cfg.database_path, [("t1", "/images/generated_a.jpeg")])
    (cfg.images_dir / "generated_a.jpeg").write_bytes(b"A")

    storage = MagicMock()
    storage.exists.return_value = True

    stats = mod._migrate(cfg, storage, dry_run=False, limit=None)
    assert stats.skipped_already == 1
    assert stats.migrated == 0
    storage.save.assert_not_called()

    # DB updated to bare key even though no upload happened.
    conn = sqlite3.connect(str(cfg.database_path))
    (path,) = conn.execute("SELECT image_path FROM tasks WHERE id='t1'").fetchone()
    conn.close()
    assert path == "generated_a.jpeg"


def test_migrate_retries_then_records_failure(tmp_path: Path, monkeypatch):
    cfg = _make_config(tmp_path)
    _make_db_with_rows(cfg.database_path, [("t1", "generated_a.jpeg")])
    (cfg.images_dir / "generated_a.jpeg").write_bytes(b"A")

    # Make sleep a no-op so the test runs fast.
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    storage = MagicMock()
    storage.exists.return_value = False
    storage.save.side_effect = StorageError("aws", "save", "k", RuntimeError("boom"))

    stats = mod._migrate(cfg, storage, dry_run=False, limit=None)
    assert stats.failed == 1
    assert stats.migrated == 0
    assert storage.save.call_count == 3  # three attempts


def test_migrate_respects_limit(tmp_path: Path):
    cfg = _make_config(tmp_path)
    _make_db_with_rows(
        cfg.database_path,
        [
            ("a", "generated_a.jpeg"),
            ("b", "generated_b.jpeg"),
            ("c", "generated_c.jpeg"),
        ],
    )
    for name in ("generated_a.jpeg", "generated_b.jpeg", "generated_c.jpeg"):
        (cfg.images_dir / name).write_bytes(b"x")

    storage = MagicMock()
    storage.exists.return_value = False

    stats = mod._migrate(cfg, storage, dry_run=False, limit=2)
    assert stats.scanned == 2
    assert stats.migrated == 2


def test_migrate_uploads_temp_reference_paths(tmp_path: Path):
    cfg = _make_config(tmp_path)
    _make_db_with_reference_rows(
        cfg.database_path,
        [
            ("t1", "temp/ref_a.png", '["temp/ref_a.png", "temp/ref_b.webp"]'),
        ],
    )
    (cfg.images_dir / "temp").mkdir()
    (cfg.images_dir / "temp" / "ref_a.png").write_bytes(b"A")
    (cfg.images_dir / "temp" / "ref_b.webp").write_bytes(b"B")

    storage = MagicMock()
    storage.exists.return_value = False

    stats = mod._migrate(cfg, storage, dry_run=False, limit=None)

    assert stats.scanned == 1
    assert stats.migrated == 2
    saved_keys = [call.args[0] for call in storage.save.call_args_list]
    assert saved_keys == ["temp/ref_a.png", "temp/ref_b.webp"]
