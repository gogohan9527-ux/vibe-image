"""Test that the 2026-05-09 schema migration is idempotent and complete."""

from __future__ import annotations

from pathlib import Path

from app.core.storage import Storage


def test_init_idempotent(tmp_path: Path):
    db = tmp_path / "data" / "v.db"
    s1 = Storage(db_path=db, prompts_dir=tmp_path / "prompts")
    s1.close()
    # Second instantiation must not raise (re-init).
    s2 = Storage(db_path=db, prompts_dir=tmp_path / "prompts")
    s2.close()


def test_provider_tables_exist(tmp_path: Path):
    db = tmp_path / "data" / "v.db"
    s = Storage(db_path=db, prompts_dir=tmp_path / "prompts")
    try:
        names = {
            r["name"]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        s.close()
    assert "provider_configs" in names
    assert "provider_keys" in names
    assert "provider_models" in names


def test_tasks_has_provider_columns(tmp_path: Path):
    db = tmp_path / "data" / "v.db"
    s = Storage(db_path=db, prompts_dir=tmp_path / "prompts")
    try:
        cols = {r["name"] for r in s._conn.execute("PRAGMA table_info(tasks)")}
    finally:
        s.close()
    assert "provider_id" in cols
    assert "key_id" in cols


def test_tasks_has_input_image_path_column(tmp_path: Path):
    """2026-05-09 Addendum (II) — img2img reference image column."""
    db = tmp_path / "data" / "v.db"
    s = Storage(db_path=db, prompts_dir=tmp_path / "prompts")
    try:
        cols = {r["name"] for r in s._conn.execute("PRAGMA table_info(tasks)")}
    finally:
        s.close()
    assert "input_image_path" in cols


def test_input_image_path_migration_idempotent(tmp_path: Path):
    """Re-opening an existing db must not error on the additive ALTER."""
    db = tmp_path / "data" / "v.db"
    s1 = Storage(db_path=db, prompts_dir=tmp_path / "prompts")
    s1.close()
    s2 = Storage(db_path=db, prompts_dir=tmp_path / "prompts")
    try:
        cols = {r["name"] for r in s2._conn.execute("PRAGMA table_info(tasks)")}
    finally:
        s2.close()
    assert "input_image_path" in cols
