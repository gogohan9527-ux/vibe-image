"""SQLite storage for tasks and prompt template CRUD.

Tasks live in the ``tasks`` table. Prompt templates live in the
``prompt_templates`` table; ``paths.prompts_dir`` is only used for seed JSON
files imported by the explicit init command.

Threading model: a single shared ``sqlite3.Connection`` is created with
``check_same_thread=False`` and protected by a module-level ``RLock``. All
public functions acquire that lock for the duration of their work.
Timestamps are ISO-8601 strings in UTC ("Z" suffix).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from ..errors import PromptConflictError, PromptNotFoundError, TaskNotFoundError


logger = logging.getLogger(__name__)


_SQL_DIR = Path(__file__).parent / "sql"


TASK_COLUMNS = (
    "id",
    "prompt_template_id",
    "prompt",
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
    "title",
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

    # ---------- Initialization ----------

    def init_db(self) -> list[dict]:
        """Initialize all modules. Safe to run repeatedly."""
        results = []
        for fn in [self._init_tasks_module, self._init_prompt_templates_module]:
            try:
                result = fn()
                results.append(result)
            except Exception as exc:
                module = fn.__name__.removeprefix("_init_").removesuffix("_module")
                logger.error("%s 模块初始化异常: %s", module, exc)
                raise
        return results

    # ---------- Tasks Module ----------

    def _init_tasks_module(self) -> dict:
        """Initialize tasks table and indexes from sql/tasks.sql."""
        sql = (_SQL_DIR / "tasks.sql").read_text(encoding="utf-8")
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'"
            ).fetchone() is not None
            self._conn.executescript(sql)
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(tasks)")}
            # Migrate old column names
            if "prompt" not in cols and "prompt_text" in cols:
                self._conn.execute(
                    "ALTER TABLE tasks RENAME COLUMN prompt_text TO prompt"
                )
            if "prompt_template_id" not in cols and "prompt_id" in cols:
                self._conn.execute(
                    "ALTER TABLE tasks RENAME COLUMN prompt_id TO prompt_template_id"
                )
        status = "exists" if exists else "created"
        return {
            "module": "tasks",
            "status": status,
            "message": f"tasks 模块初始化完成 (status={status})"
        }

    # ---------- Prompt Templates Module ----------

    def _init_prompt_templates_module(self) -> dict:
        """Initialize prompt_templates table and indexes from sql/prompt_templates.sql."""
        """and seed data."""
        sql = (_SQL_DIR / "prompt_templates.sql").read_text(encoding="utf-8")
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='prompt_templates'"
            ).fetchone() is not None
            self._conn.executescript(sql)
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(prompt_templates)")}
            # Migrate old column names: name → title, content → prompt
            if "title" not in cols and "name" in cols:
                self._conn.execute(
                    "ALTER TABLE prompt_templates RENAME COLUMN name TO title"
                )
            if "prompt" not in cols and "content" in cols:
                self._conn.execute(
                    "ALTER TABLE prompt_templates RENAME COLUMN content TO prompt"
                )
        status = "exists" if exists else "created"
        imported, skipped = self.init_prompt_templates_from_files()
        return {
            "module": "prompt_templates",
            "status": status,
            "imported": imported,
            "skipped": skipped,
            "message": f"prompt_templates 模块初始化完成 (status={status}, imported={imported}, skipped={skipped})",
        }

    # ---------- Prompt Template Seed Import ----------

    def init_prompt_templates_from_files(self) -> tuple[int, int]:
        """Scan ``<project_root>/prompt/prompt_*.json`` and INSERT OR IGNORE.

        Returns ``(imported, skipped)``. Malformed JSON files are logged at
        WARN level and skipped (not raised). Already-present ids are skipped
        and never overwritten.

        JSON files may use either ``title``/``prompt`` (new) or ``name``/``content``
        (legacy) field names.
        """
        imported = 0
        skipped = 0
        for path in sorted(self.prompts_dir.glob("prompt_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Skipping %s: %s", path.name, exc)
                continue
            if not isinstance(data, dict):
                logger.warning("Skipping %s: not a JSON object", path.name)
                continue
            pid = data.get("id")
            # Support both new (title/prompt) and legacy (name/content) field names.
            title = data.get("title") or data.get("name")
            prompt = data.get("prompt") or data.get("content")
            if not (isinstance(pid, str) and pid
                    and isinstance(title, str) and title
                    and isinstance(prompt, str) and prompt):
                logger.warning(
                    "Skipping %s: missing required keys (id/title/prompt)",
                    path.name,
                )
                continue
            created_at = data.get("created_at") or utcnow_iso()
            with self._lock:
                if self._prompt_id_exists(pid):
                    skipped += 1
                    continue
                self._conn.execute(
                    "INSERT INTO prompt_templates "
                    "(id, title, prompt, created_at) VALUES (?, ?, ?, ?)",
                    (pid, title, prompt, created_at),
                )
                imported += 1
        return imported, skipped

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
            where.append("prompt LIKE ?")
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

    def update_task_title(self, task_id: str, title: str) -> dict:
        """Best-effort title overwrite from the generator's response."""
        return self.update_task_fields(task_id, title=title)

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

    # ---------- Prompts (SQLite-backed) ----------

    def _prompt_id_exists(self, prompt_id: str) -> bool:
        """Caller must hold ``self._lock``."""
        row = self._conn.execute(
            "SELECT 1 FROM prompt_templates WHERE id = ?", (prompt_id,)
        ).fetchone()
        return row is not None

    def _make_unique_prompt_id(self, base: str) -> str:
        """Caller must hold ``self._lock``. Mirrors the previous slug+suffix logic."""
        candidate = base
        suffix = 2
        while self._prompt_id_exists(candidate):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def list_prompts(self) -> List[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, title, prompt, created_at FROM prompt_templates "
                "ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_prompt(self, prompt_id: str) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, title, prompt, created_at FROM prompt_templates "
                "WHERE id = ?",
                (prompt_id,),
            ).fetchone()
        if row is None:
            raise PromptNotFoundError(f"Prompt {prompt_id} not found.")
        return _row_to_dict(row)

    def save_prompt(
        self,
        title: str,
        prompt: str,
        prompt_id: Optional[str] = None,
    ) -> dict:
        base = slugify(prompt_id or title)
        with self._lock:
            candidate = self._make_unique_prompt_id(base)
            record = {
                "id": candidate,
                "title": title,
                "prompt": prompt,
                "created_at": utcnow_iso(),
            }
            self._conn.execute(
                "INSERT INTO prompt_templates (id, title, prompt, created_at) "
                "VALUES (?, ?, ?, ?)",
                (record["id"], record["title"], record["prompt"], record["created_at"]),
            )
        return record

    def update_prompt(
        self,
        prompt_id: str,
        title: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> dict:
        if title is None and prompt is None:
            raise ValueError("At least one of title or prompt must be provided.")
        sets: List[str] = []
        params: List[object] = []
        if title is not None:
            sets.append("title = ?")
            params.append(title)
        if prompt is not None:
            sets.append("prompt = ?")
            params.append(prompt)
        params.append(prompt_id)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE prompt_templates SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            if cur.rowcount == 0:
                raise PromptNotFoundError(f"Prompt {prompt_id} not found.")
            row = self._conn.execute(
                "SELECT id, title, prompt, created_at FROM prompt_templates "
                "WHERE id = ?",
                (prompt_id,),
            ).fetchone()
        return _row_to_dict(row)

    def delete_prompt(self, prompt_id: str) -> None:
        if prompt_id == "sample":
            with self._lock:
                exists = self._prompt_id_exists(prompt_id)
            if not exists:
                raise PromptNotFoundError(f"Prompt {prompt_id} not found.")
            raise PromptConflictError("Cannot delete the bundled sample prompt.")
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM prompt_templates WHERE id = ?", (prompt_id,)
            )
            if cur.rowcount == 0:
                raise PromptNotFoundError(f"Prompt {prompt_id} not found.")

    def ensure_sample_prompt(self) -> None:
        """Insert the bundled sample template if not already present."""
        record = {
            "id": "sample",
            "title": "示例：花园里的猫",
            "prompt": "A cute cat playing in a garden",
            "created_at": "2026-05-07T00:00:00Z",
        }
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO prompt_templates "
                "(id, title, prompt, created_at) VALUES (?, ?, ?, ?)",
                (record["id"], record["title"], record["prompt"], record["created_at"]),
            )

def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}
