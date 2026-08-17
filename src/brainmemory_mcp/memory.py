"""Persistence layer for BrainMemory-MCP.

Memories are stored in a local SQLite database under ``~/.brainmemory-mcp``.
The store is intentionally small, deterministic, and dependency-free (stdlib
``sqlite3`` only) so that the "brain memory" is safe and never silently loses
data.

Memory model (graph)
--------------------
Since v0.4.0 the store models memory as a small **knowledge graph**, while the
public vocabulary stays "memory"-oriented (no "entity" wording):

- ``memories``       -> the graph **nodes**. Each is a self-contained memory
  with ``content``, ``category``, ``tags`` and ``importance``.
- ``memory_details`` -> extra facts/observations attached to a single memory.
- ``memory_links``   -> directed **connections** between two memories (e.g.
  ``relation="related_to"``, ``"works_at"``, ``"caused_by"``), with a weight.

Graph algorithms (multi-hop recall, shortest path/connection, centrality) are
implemented with plain SQL + a little Python — no external dependencies.

Backward compatibility
-----------------------
The ``memories`` table keeps its original columns, so existing databases are
preserved. When an older (pre-graph) database is opened, it is **backed up
automatically** to ``<data_dir>/backups/`` before the new graph tables are
added — nothing is dropped or rewritten.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

DATA_DIR_ENV = "BRAINMEMORY_HOME"

DEFAULT_RELATION = "related_to"


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
# Models
# --------------------------------------------------------------------------- #


@dataclass
class Memory:
    """A single stored memory (a node in the memory graph)."""

    id: str
    content: str
    category: str
    tags: list[str]
    importance: int
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryDetail:
    """An extra fact/observation attached to a single memory."""

    id: str
    memory_id: str
    content: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryLink:
    """A directed connection between two memories."""

    id: str
    source_id: str
    target_id: str
    relation: str
    weight: float
    created_at: str

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


def _row_to_detail(row: sqlite3.Row) -> MemoryDetail:
    return MemoryDetail(
        id=row["id"],
        memory_id=row["memory_id"],
        content=row["content"],
        created_at=row["created_at"],
    )


def _row_to_link(row: sqlite3.Row) -> MemoryLink:
    return MemoryLink(
        id=row["id"],
        source_id=row["source_id"],
        target_id=row["target_id"],
        relation=row["relation"],
        weight=row["weight"],
        created_at=row["created_at"],
    )


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #


class MemoryStore:
    """SQLite-backed memory store modelled as a small knowledge graph.

    Thread/async note: each public method opens a short-lived connection, so the
    store is safe to use from the MCP server's request handlers.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "memory.db"
        # Populated when a legacy (pre-graph) DB is auto-migrated.
        self.last_backup_path: Path | None = None
        self._init_db()

    # -- internal ----------------------------------------------------------- #

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _legacy_needs_migration(self) -> bool:
        """True if the DB has the old ``memories`` table but no graph tables."""
        if not self.db_path.exists():
            return False
        conn = sqlite3.connect(self.db_path)
        try:
            has_memories = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memories'"
            ).fetchone()
            has_links = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_links'"
            ).fetchone()
            return bool(has_memories) and not bool(has_links)
        finally:
            conn.close()

    def _backup_db(self) -> Path:
        """Snapshot the current DB into ``<data_dir>/backups`` and return path.

        Uses SQLite's online backup API so the copy is consistent even with a
        live WAL. Never deletes the original.
        """
        backups = self.data_dir / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = backups / f"memory-{ts}.db"
        src = sqlite3.connect(self.db_path)
        dst = sqlite3.connect(dest)
        try:
            with dst:
                src.backup(dst)
        finally:
            src.close()
            dst.close()
        return dest

    def _init_db(self) -> None:
        # Back up an older (pre-graph) database before adding graph tables so a
        # user upgrading in place never risks silent data loss.
        if self._legacy_needs_migration():
            self.last_backup_path = self._backup_db()

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
                """
                CREATE TABLE IF NOT EXISTS memory_details (
                    id          TEXT PRIMARY KEY,
                    memory_id   TEXT NOT NULL
                                REFERENCES memories(id) ON DELETE CASCADE,
                    content     TEXT NOT NULL,
                    created_at  TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_links (
                    id          TEXT PRIMARY KEY,
                    source_id   TEXT NOT NULL
                                REFERENCES memories(id) ON DELETE CASCADE,
                    target_id   TEXT NOT NULL
                                REFERENCES memories(id) ON DELETE CASCADE,
                    relation    TEXT NOT NULL DEFAULT 'related_to',
                    weight      REAL NOT NULL DEFAULT 1.0,
                    created_at  TEXT NOT NULL,
                    UNIQUE(source_id, target_id, relation)
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_details_memory ON memory_details(memory_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_links_source ON memory_links(source_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_links_target ON memory_links(target_id);"
            )
            conn.commit()

    # -- memories (nodes) --------------------------------------------------- #

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
        """Search memories by free text, category, tags and/or importance.

        Free text is matched against a memory's own content/tags/category **and**
        against the content of any details attached to it.
        """
        clauses: list[str] = []
        params: list[Any] = []

        if query and query.strip():
            like = f"%{query.strip()}%"
            clauses.append(
                "(content LIKE ? OR tags LIKE ? OR category LIKE ? OR id IN "
                "(SELECT memory_id FROM memory_details WHERE content LIKE ?))"
            )
            params.extend([like, like, like, like])

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
        """Delete a memory by id (its details and links cascade away).

        Returns True if a row was removed.
        """
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

    def clear(self) -> int:
        """Delete ALL memories (details and links cascade). Returns row count."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM memories")
            conn.commit()
            return cur.rowcount

    # -- details (observations) -------------------------------------------- #

    def add_detail(self, memory_id: str, content: str) -> MemoryDetail | None:
        """Attach an extra fact/observation to an existing memory."""
        if not content or not content.strip():
            raise ValueError("detail content must not be empty")
        if self.get(memory_id) is None:
            return None
        detail = MemoryDetail(
            id=uuid.uuid4().hex,
            memory_id=memory_id,
            content=content.strip(),
            created_at=_utcnow(),
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO memory_details (id, memory_id, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (detail.id, detail.memory_id, detail.content, detail.created_at),
            )
            conn.commit()
        return detail

    def list_details(self, memory_id: str) -> list[MemoryDetail]:
        """Return all details attached to a memory (oldest first)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_details WHERE memory_id = ? ORDER BY created_at",
                (memory_id,),
            ).fetchall()
        return [_row_to_detail(r) for r in rows]

    def delete_detail(self, detail_id: str) -> bool:
        """Delete a single detail by id. Returns True if a row was removed."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM memory_details WHERE id = ?", (detail_id,)
            )
            conn.commit()
            return cur.rowcount > 0

    # -- links (connections) ----------------------------------------------- #

    def link(
        self,
        source_id: str,
        target_id: str,
        *,
        relation: str = DEFAULT_RELATION,
        weight: float = 1.0,
    ) -> MemoryLink | None:
        """Create (or update) a directed connection between two memories.

        Returns the link, ``None`` if either memory is missing, and raises
        ``ValueError`` for a self-link.
        """
        if source_id == target_id:
            raise ValueError("a memory cannot be linked to itself")
        relation = (relation or DEFAULT_RELATION).strip() or DEFAULT_RELATION
        if self.get(source_id) is None or self.get(target_id) is None:
            return None
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            weight = 1.0

        now = _utcnow()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM memory_links "
                "WHERE source_id = ? AND target_id = ? AND relation = ?",
                (source_id, target_id, relation),
            ).fetchone()
            if existing is not None:
                conn.execute(
                    "UPDATE memory_links SET weight = ? WHERE id = ?",
                    (weight, existing["id"]),
                )
                conn.commit()
                link_id = existing["id"]
                created = existing["created_at"]
            else:
                link_id = uuid.uuid4().hex
                created = now
                conn.execute(
                    "INSERT INTO memory_links "
                    "(id, source_id, target_id, relation, weight, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (link_id, source_id, target_id, relation, weight, created),
                )
                conn.commit()
        return MemoryLink(
            id=link_id,
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            weight=weight,
            created_at=created,
        )

    def unlink(
        self,
        source_id: str,
        target_id: str,
        *,
        relation: str | None = None,
    ) -> int:
        """Remove connection(s) between two memories.

        If ``relation`` is given only that relation is removed; otherwise every
        connection between the two memories is removed. Returns the count.
        """
        with self._connect() as conn:
            if relation:
                cur = conn.execute(
                    "DELETE FROM memory_links "
                    "WHERE source_id = ? AND target_id = ? AND relation = ?",
                    (source_id, target_id, relation.strip()),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM memory_links "
                    "WHERE source_id = ? AND target_id = ?",
                    (source_id, target_id),
                )
            conn.commit()
            return cur.rowcount

    def links_of(self, memory_id: str) -> dict[str, list[MemoryLink]]:
        """Return the direct connections of a memory, split by direction."""
        with self._connect() as conn:
            out_rows = conn.execute(
                "SELECT * FROM memory_links WHERE source_id = ? ORDER BY weight DESC",
                (memory_id,),
            ).fetchall()
            in_rows = conn.execute(
                "SELECT * FROM memory_links WHERE target_id = ? ORDER BY weight DESC",
                (memory_id,),
            ).fetchall()
        return {
            "outgoing": [_row_to_link(r) for r in out_rows],
            "incoming": [_row_to_link(r) for r in in_rows],
        }

    def _all_links(self, conn: sqlite3.Connection) -> list[MemoryLink]:
        rows = conn.execute("SELECT * FROM memory_links").fetchall()
        return [_row_to_link(r) for r in rows]

    # -- graph algorithms --------------------------------------------------- #

    def recall_related(
        self,
        memory_id: str,
        *,
        depth: int = 1,
        relation: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any] | None:
        """Multi-hop recall: memories connected to ``memory_id`` up to ``depth``.

        Traversal is undirected (a connection relates both memories). Returns the
        root memory plus the reachable neighbourhood and the links among it.
        """
        root = self.get(memory_id)
        if root is None:
            return None
        depth = max(1, int(depth))
        limit = max(1, int(limit))
        rel = relation.strip() if relation and relation.strip() else None

        with self._connect() as conn:
            all_links = self._all_links(conn)

            adjacency: dict[str, list[MemoryLink]] = defaultdict(list)
            for link in all_links:
                if rel and link.relation != rel:
                    continue
                adjacency[link.source_id].append(link)
                adjacency[link.target_id].append(link)

            distance: dict[str, int] = {memory_id: 0}
            queue: deque[str] = deque([memory_id])
            used_links: dict[str, MemoryLink] = {}
            while queue:
                current = queue.popleft()
                if distance[current] >= depth:
                    continue
                for link in adjacency.get(current, []):
                    other = link.target_id if link.source_id == current else link.source_id
                    if other not in distance:
                        distance[other] = distance[current] + 1
                        queue.append(other)
                    if link.source_id in distance and link.target_id in distance:
                        used_links[link.id] = link

            neighbour_ids = [mid for mid in distance if mid != memory_id][: limit]

            memories: list[dict[str, Any]] = []
            for mid in neighbour_ids:
                mem = self._get_conn(conn, mid)
                if mem is not None:
                    entry = mem.to_dict()
                    entry["distance"] = distance[mid]
                    memories.append(entry)

            memories.sort(key=lambda m: (m["distance"], -m["importance"]))
            kept = {memory_id} | {m["id"] for m in memories}
            links = [
                l.to_dict()
                for l in used_links.values()
                if l.source_id in kept and l.target_id in kept
            ]

        return {
            "root": root.to_dict(),
            "depth": depth,
            "count": len(memories),
            "related": memories,
            "links": links,
        }

    def connect_memories(
        self,
        source_id: str,
        target_id: str,
        *,
        max_depth: int = 6,
    ) -> dict[str, Any] | None:
        """Find the shortest connection (path) between two memories.

        Returns the ordered list of memories on the path and the links between
        them, or ``{"connected": False}`` if none exists within ``max_depth``.
        """
        if self.get(source_id) is None or self.get(target_id) is None:
            return None
        max_depth = max(1, int(max_depth))

        if source_id == target_id:
            root = self.get(source_id)
            return {
                "connected": True,
                "hops": 0,
                "path": [root.to_dict()] if root else [],
                "links": [],
            }

        with self._connect() as conn:
            all_links = self._all_links(conn)
            adjacency: dict[str, list[MemoryLink]] = defaultdict(list)
            for link in all_links:
                adjacency[link.source_id].append(link)
                adjacency[link.target_id].append(link)

            prev: dict[str, tuple[str, MemoryLink]] = {}
            distance: dict[str, int] = {source_id: 0}
            queue: deque[str] = deque([source_id])
            found = False
            while queue:
                current = queue.popleft()
                if current == target_id:
                    found = True
                    break
                if distance[current] >= max_depth:
                    continue
                for link in adjacency.get(current, []):
                    other = link.target_id if link.source_id == current else link.source_id
                    if other not in distance:
                        distance[other] = distance[current] + 1
                        prev[other] = (current, link)
                        queue.append(other)

            if not found:
                return {"connected": False, "path": [], "links": []}

            # Reconstruct path target -> source, then reverse.
            node_chain: list[str] = [target_id]
            link_chain: list[MemoryLink] = []
            cursor = target_id
            while cursor != source_id:
                parent, link = prev[cursor]
                link_chain.append(link)
                node_chain.append(parent)
                cursor = parent
            node_chain.reverse()
            link_chain.reverse()

            path = []
            for mid in node_chain:
                mem = self._get_conn(conn, mid)
                if mem is not None:
                    path.append(mem.to_dict())

        return {
            "connected": True,
            "hops": len(link_chain),
            "path": path,
            "links": [l.to_dict() for l in link_chain],
        }

    def memory_map(
        self,
        memory_id: str | None = None,
        *,
        depth: int = 2,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Return a map (nodes + links) of the memory graph.

        With ``memory_id`` the map is the neighbourhood around that memory up to
        ``depth`` hops; without it, the whole graph (capped at ``limit`` nodes).
        """
        limit = max(1, int(limit))
        with self._connect() as conn:
            if memory_id is not None:
                related = self.recall_related(memory_id, depth=depth, limit=limit)
                if related is None:
                    return {"nodes": [], "links": []}
                node_ids = [related["root"]["id"]] + [
                    m["id"] for m in related["related"]
                ]
                nodes = [related["root"]] + related["related"]
                links = related["links"]
                return {
                    "root": related["root"]["id"],
                    "nodes": nodes,
                    "links": links,
                    "node_count": len(nodes),
                    "link_count": len(links),
                }

            rows = conn.execute(
                "SELECT * FROM memories "
                "ORDER BY importance DESC, updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            nodes = [_row_to_memory(r).to_dict() for r in rows]
            keep = {n["id"] for n in nodes}
            links = [
                l.to_dict()
                for l in self._all_links(conn)
                if l.source_id in keep and l.target_id in keep
            ]
        return {
            "nodes": nodes,
            "links": links,
            "node_count": len(nodes),
            "link_count": len(links),
        }

    def _get_conn(self, conn: sqlite3.Connection, memory_id: str) -> Memory | None:
        row = conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return _row_to_memory(row) if row else None

    # -- summary ------------------------------------------------------------ #

    def stats(self) -> dict[str, Any]:
        """Return summary statistics about the stored memory graph."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()["c"]
            total_details = conn.execute(
                "SELECT COUNT(*) AS c FROM memory_details"
            ).fetchone()["c"]
            total_links = conn.execute(
                "SELECT COUNT(*) AS c FROM memory_links"
            ).fetchone()["c"]

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
            avg_importance = (
                round(avg_importance_row["a"], 2) if avg_importance_row["a"] else 0
            )

            all_tags: dict[str, int] = {}
            for row in conn.execute("SELECT tags FROM memories").fetchall():
                for tag in json.loads(row["tags"]) if row["tags"] else []:
                    all_tags[tag] = all_tags.get(tag, 0) + 1

            relation_types = {
                row["relation"]: row["c"]
                for row in conn.execute(
                    "SELECT relation, COUNT(*) AS c FROM memory_links "
                    "GROUP BY relation ORDER BY c DESC"
                ).fetchall()
            }

            # Degree centrality: which memories are the most connected hubs.
            degree: dict[str, int] = defaultdict(int)
            for row in conn.execute(
                "SELECT source_id, target_id FROM memory_links"
            ).fetchall():
                degree[row["source_id"]] += 1
                degree[row["target_id"]] += 1

            most_connected: list[dict[str, Any]] = []
            for mid, deg in sorted(degree.items(), key=lambda kv: kv[1], reverse=True)[:5]:
                mem = self._get_conn(conn, mid)
                if mem is not None:
                    most_connected.append(
                        {
                            "id": mid,
                            "content": mem.content[:80],
                            "connections": deg,
                        }
                    )

        return {
            "total": total,
            "total_details": total_details,
            "total_links": total_links,
            "by_category": by_category,
            "top_tags": dict(
                sorted(all_tags.items(), key=lambda kv: kv[1], reverse=True)[:10]
            ),
            "relation_types": relation_types,
            "most_connected": most_connected,
            "average_importance": avg_importance,
            "data_dir": str(self.data_dir),
            "db_path": str(self.db_path),
            "last_backup": str(self.last_backup_path) if self.last_backup_path else None,
        }
