"""
Memory.

Three categories, deliberately kept separate:

  - Permanent: key/value facts that should survive across sessions
    (known project paths, preferred editor, preferences). Small,
    structured, boring on purpose.
  - Session: the current task/plan/files-touched context. Cleared or
    replaced as a new task starts; not meant to accumulate forever.
  - History: an append-only log of tool actions, for OGGY (and you) to
    look back on. This overlaps with oggy_logging's audit log but is
    queryable structured data rather than log lines.

Backed by SQLite (stdlib `sqlite3`, no extra dependency) as instructed -
no vector DB in V1. Swap `MemoryStore` for something fancier later
without touching callers, since they only see this class's methods.

Never call `remember_permanent()` / `remember_session()` with API keys,
passwords, tokens, or other secrets - this module does not attempt to
detect or redact secrets itself the way oggy_logging does, so the
caller is responsible for keeping this store secret-free.
"""

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from config import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS permanent_memory (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS session_memory (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,
    success INTEGER NOT NULL,
    summary TEXT
);
"""


class MemoryStore:
    def __init__(self, db_path=None):
        config.ensure_dirs()
        self.db_path = str(db_path or config.MEMORY_DB_PATH)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- Permanent -------------------------------------------------------
    def remember_permanent(self, key: str, value: Any):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO permanent_memory (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value), time.time()),
            )

    def recall_permanent(self, key: str) -> Optional[Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM permanent_memory WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def all_permanent(self) -> Dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM permanent_memory").fetchall()
        return {k: json.loads(v) for k, v in rows}

    def forget_permanent(self, key: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM permanent_memory WHERE key = ?", (key,))

    # --- Session -----------------------------------------------------------
    def remember_session(self, key: str, value: Any):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO session_memory (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value), time.time()),
            )

    def recall_session(self, key: str) -> Optional[Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM session_memory WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def clear_session(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM session_memory")

    # --- Tool history --------------------------------------------------------
    def record_tool_use(self, tool_name: str, arguments: Dict[str, Any], success: bool, summary: str = ""):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO tool_history (timestamp, tool_name, arguments, success, summary) "
                "VALUES (?, ?, ?, ?, ?)",
                (time.time(), tool_name, json.dumps(arguments), int(success), summary),
            )

    def recent_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT timestamp, tool_name, arguments, success, summary "
                "FROM tool_history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "timestamp": r[0],
                "tool_name": r[1],
                "arguments": json.loads(r[2]),
                "success": bool(r[3]),
                "summary": r[4],
            }
            for r in rows
        ]


memory_store = MemoryStore()
