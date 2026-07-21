"""Persistence layer for BrainMemory-MCP.

Memories are stored in a local SQLite database under ``~/.brainmemory-mcp``.
The store is intentionally small, deterministic, and dependency-free (stdlib
``sqlite3`` only) so that the "brain memory" is safe and never silently loses
data.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

DATA_DIR_ENV = "BRAINMEMORY_HOME"


def default_data_dir() -> Path:
    """Return the directory where memories are persisted.

    Defaults to ``~/.brainmemory-mcp`` but can be overridden with the
    ``BRAINMEMORY_HOME`` environment variable.
    """
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".brainmemory-mcp"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #


@dataclass
class Memory:
    """A single stored memory."""

    id: str
    content: str
    category: str
    tags: list[str]
    importance: int
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _row_to_memory(row: sqlite3.Row) -> Memory:
    return Memory(
        id=row["id"],
        content=row["content"],
        category=row["category"],
        tags=json.loads(row["tags"]) if row["tags"] else [],
        importance=row["importance"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #


class MemoryStore:
    """SQLite-backed memory store.

    Thread/async note: each public method opens a short-lived connection, so the
    store is safe to use from the MCP server's request handlers.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "memory.db"
        self._init_db()

    # -- internal ----------------------------------------------------------- #

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id          TEXT PRIMARY KEY,
                    content     TEXT NOT NULL,
                    category    TEXT NOT NULL DEFAULT 'general',
                    tags        TEXT NOT NULL DEFAULT '[]',
                    importance  INTEGER NOT NULL DEFAULT 3,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);"
            )
            conn.commit()

    # -- public API --------------------------------------------------------- #

    def store(
        self,
        content: str,
        *,
        category: str = "general",
        tags: Iterable[str] | None = None,
        importance: int = 3,
    ) -> Memory:
        """Persist a new memory and return it."""
        if not content or not content.strip():
            raise ValueError("content must not be empty")
        importance = max(1, min(5, int(importance)))
        now = _utcnow()
        mem = Memory(
            id=uuid.uuid4().hex,
            content=content.strip(),
            category=(category or "general").strip() or "general",
            tags=sorted({t.strip() for t in (tags or []) if t and t.strip()}),
            importance=importance,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories
                    (id, content, category, tags, importance, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mem.id,
                    mem.content,
                    mem.category,
                    json.dumps(mem.tags),
                    mem.importance,
                    mem.created_at,
                    mem.updated_at,
                ),
            )
            conn.commit()
        return mem

    def get(self, memory_id: str) -> Memory | None:
        """Return a single memory by id, or ``None`` if it does not exist."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        return _row_to_memory(row) if row else None

    def search(
        self,
        query: str | None = None,
        *,
        category: str | None = None,
        tags: Iterable[str] | None = None,
        min_importance: int | None = None,
        limit: int = 20,
    ) -> list[Memory]:
        """Search memories by free text, category, tags and/or importance."""
        clauses: list[str] = []
        params: list[Any] = []

        if query and query.strip():
            clauses.append("(content LIKE ? OR tags LIKE ? OR category LIKE ?)")
            like = f"%{query.strip()}%"
            params.extend([like, like, like])

        if category and category.strip():
            clauses.append("category = ?")
            params.append(category.strip())

        if min_importance is not None:
            clauses.append("importance >= ?")
            params.append(max(1, min(5, int(min_importance))))

        wanted_tags = [t.strip() for t in (tags or []) if t and t.strip()]
        for tag in wanted_tags:
            clauses.append("tags LIKE ?")
            params.append(f'%"{tag}"%')

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT * FROM memories {where} "
            "ORDER BY importance DESC, updated_at DESC LIMIT ?"
        )
        params.append(max(1, int(limit)))

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_memory(r) for r in rows]

    def list_all(self, *, limit: int = 100, offset: int = 0) -> list[Memory]:
        """Return memories ordered by importance then recency."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories "
                "ORDER BY importance DESC, updated_at DESC "
                "LIMIT ? OFFSET ?",
                (max(1, int(limit)), max(0, int(offset))),
            ).fetchall()
        return [_row_to_memory(r) for r in rows]

    def update(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        category: str | None = None,
        tags: Iterable[str] | None = None,
        importance: int | None = None,
    ) -> Memory | None:
        """Update fields of an existing memory. Returns the updated memory."""
        current = self.get(memory_id)
        if current is None:
            return None

        if content is not None and content.strip():
            current.content = content.strip()
        if category is not None and category.strip():
            current.category = category.strip()
        if tags is not None:
            current.tags = sorted({t.strip() for t in tags if t and t.strip()})
        if importance is not None:
            current.importance = max(1, min(5, int(importance)))
        current.updated_at = _utcnow()

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE memories
                   SET content = ?, category = ?, tags = ?, importance = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    current.content,
                    current.category,
                    json.dumps(current.tags),
                    current.importance,
                    current.updated_at,
                    current.id,
                ),
            )
            conn.commit()
        return current

    def forget(self, memory_id: str) -> bool:
        """Delete a memory by id. Returns True if a row was removed."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

    def clear(self) -> int:
        """Delete ALL memories. Returns the number of rows removed."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM memories")
            conn.commit()
            return cur.rowcount

    def stats(self) -> dict[str, Any]:
        """Return summary statistics about the stored memories."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()["c"]
            by_category = {
                row["category"]: row["c"]
                for row in conn.execute(
                    "SELECT category, COUNT(*) AS c FROM memories "
                    "GROUP BY category ORDER BY c DESC"
                ).fetchall()
            }
            avg_importance_row = conn.execute(
                "SELECT AVG(importance) AS a FROM memories"
            ).fetchone()
            avg_importance = round(avg_importance_row["a"], 2) if avg_importance_row["a"] else 0

            all_tags: dict[str, int] = {}
            for row in conn.execute("SELECT tags FROM memories").fetchall():
                for tag in json.loads(row["tags"]) if row["tags"] else []:
                    all_tags[tag] = all_tags.get(tag, 0) + 1

        return {
            "total": total,
            "by_category": by_category,
            "top_tags": dict(
                sorted(all_tags.items(), key=lambda kv: kv[1], reverse=True)[:10]
            ),
            "average_importance": avg_importance,
            "data_dir": str(self.data_dir),
            "db_path": str(self.db_path),
        }
