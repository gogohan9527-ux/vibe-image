"""SQLite storage for tasks + filesystem-backed prompt asset CRUD.

Tasks live in a single SQLite table. Prompts live as JSON files in
``paths.prompts_dir`` (one file per prompt) — they are NOT stored in SQLite.

Threading model: a single shared ``sqlite3.Connection`` is created with
``check_same_thread=False`` and protected by a module-level ``RLock``. All
public functions acquire that lock for the duration of their work.
Timestamps are ISO-8601 strings in UTC ("Z" suffix).
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from ..errors import PromptConflictError, PromptNotFoundError, TaskNotFoundError


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NULL,
    prompt_text TEXT NOT NULL,
    model TEXT NOT NULL,
    size TEXT NOT NULL,
    quality TEXT NOT NULL,
    format TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    image_path TEXT NULL,
    error_message TEXT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT NULL,
    finished_at TEXT NULL,
    priority INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
"""

TASK_COLUMNS = (
    "id",
    "prompt_id",
    "prompt_text",
    "model",
    "size",
    "quality",
    "format",
    "status",
    "progress",
    "image_path",
    "error_message",
    "created_at",
    "started_at",
    "finished_at",
    "priority",
)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str, max_len: int = 48) -> str:
    s = _SLUG_RE.sub("_", name.strip().lower()).strip("_")
    if not s:
        s = "prompt"
    return s[:max_len]


class Storage:
    def __init__(self, db_path: Path, prompts_dir: Path) -> None:
        self.db_path = Path(db_path)
        self.prompts_dir = Path(prompts_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        with self._lock:
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    # ---------- Tasks ----------

    def insert_task(self, task: dict) -> None:
        cols = ",".join(TASK_COLUMNS)
        placeholders = ",".join("?" for _ in TASK_COLUMNS)
        values = tuple(task.get(c) for c in TASK_COLUMNS)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO tasks ({cols}) VALUES ({placeholders})", values
            )

    def get_task(self, task_id: str) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise TaskNotFoundError(f"Task {task_id} not found.", task_id=task_id)
        return _row_to_dict(row)

    def list_tasks(
        self,
        statuses: Optional[Iterable[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        order: str = "created_at_desc",
    ) -> List[dict]:
        sql = "SELECT * FROM tasks"
        params: list = []
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            sql += f" WHERE status IN ({placeholders})"
            params.extend(statuses)
        if order == "created_at_asc":
            sql += " ORDER BY created_at ASC"
        else:
            sql += " ORDER BY created_at DESC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_dict(r) for r in rows]

    def search_tasks(
        self,
        query: Optional[str] = None,
        statuses: Optional[Iterable[str]] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[List[dict], int]:
        where: list[str] = []
        params: list = []
        if query:
            where.append("prompt_text LIKE ?")
            params.append(f"%{query}%")
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            where.append(f"status IN ({placeholders})")
            params.extend(statuses)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        with self._lock:
            total = self._conn.execute(
                f"SELECT COUNT(*) FROM tasks{where_sql}", params
            ).fetchone()[0]
            offset = max(0, (page - 1) * page_size)
            rows = self._conn.execute(
                f"SELECT * FROM tasks{where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*params, page_size, offset],
            ).fetchall()
        return [_row_to_dict(r) for r in rows], int(total)

    def update_task_fields(self, task_id: str, **fields: object) -> dict:
        if not fields:
            return self.get_task(task_id)
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        params = list(fields.values()) + [task_id]
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE tasks SET {set_clause} WHERE id = ?", params
            )
            if cur.rowcount == 0:
                raise TaskNotFoundError(f"Task {task_id} not found.", task_id=task_id)
        return self.get_task(task_id)

    def update_progress(self, task_id: str, progress: int) -> dict:
        progress = max(0, min(100, int(progress)))
        return self.update_task_fields(task_id, progress=progress)

    def delete_task(self, task_id: str) -> bool:
        """Delete a task row. Returns True if a row was removed, False otherwise."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            return cur.rowcount > 0

    def mark_orphaned_running_as_failed(self) -> int:
        """On startup: any task left as queued/running/cancelling becomes failed."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE tasks SET status='failed', error_message='interrupted', "
                "finished_at=? WHERE status IN ('queued','running','cancelling')",
                (utcnow_iso(),),
            )
            return cur.rowcount

    # ---------- Prompts (filesystem) ----------

    def _prompt_path(self, prompt_id: str) -> Path:
        return self.prompts_dir / f"prompt_{prompt_id}.json"

    def list_prompts(self) -> List[dict]:
        results: List[dict] = []
        for p in sorted(self.prompts_dir.glob("prompt_*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            if "id" in data and "name" in data and "content" in data:
                data.setdefault("created_at", utcnow_iso())
                results.append(data)
        results.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        return results

    def get_prompt(self, prompt_id: str) -> dict:
        path = self._prompt_path(prompt_id)
        if not path.exists():
            raise PromptNotFoundError(f"Prompt {prompt_id} not found.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PromptNotFoundError(
                f"Prompt {prompt_id} unreadable: {exc}"
            ) from exc
        return data

    def save_prompt(
        self,
        name: str,
        content: str,
        prompt_id: Optional[str] = None,
    ) -> dict:
        base = slugify(prompt_id or name)
        candidate = base
        suffix = 2
        while self._prompt_path(candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        record = {
            "id": candidate,
            "name": name,
            "content": content,
            "created_at": utcnow_iso(),
        }
        self._prompt_path(candidate).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return record

    def delete_prompt(self, prompt_id: str) -> None:
        path = self._prompt_path(prompt_id)
        if not path.exists():
            raise PromptNotFoundError(f"Prompt {prompt_id} not found.")
        if prompt_id == "sample":
            raise PromptConflictError("Cannot delete the bundled sample prompt.")
        path.unlink()

    def ensure_sample_prompt(self) -> None:
        sample = self._prompt_path("sample")
        if sample.exists():
            return
        record = {
            "id": "sample",
            "name": "示例：花园里的猫",
            "content": "A cute cat playing in a garden",
            "created_at": "2026-05-07T00:00:00Z",
        }
        sample.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}
