"""BrainMemory-MCP server.

Exposes Cognitive memory tools over the Model Context Protocol. Two transports
are supported, both built on the official ``mcp`` SDK (``FastMCP``):

- **stdio** (default): ideal for local MCP clients that launch the server as a
  subprocess, e.g. ``uvx brainmemory-mcp``.
- **HTTP + Server-Sent Events (SSE)**: enabled with ``--web`` for remote /
  networked MCP clients. Stream at ``/sse``, message POST at ``/messages/``.

Memory is modelled internally as a small **knowledge graph** (memories =
nodes, links = directed connections, details = attached facts) so recall can be
precise and multi-hop — while the tool vocabulary stays "memory"-oriented.

Since v0.10.0 the tool surface expands to **15 tools** (3 new additions):
- export_graph_html   : render full graph as standalone 3D interactive HTML
- restore_memories    : soft-delete safety net (trash, history, rollback, purge)
- transfer_memories   : export / import memories, details & links in JSON,
  with optional keyset pagination (limit/cursor/scope) for large graphs

Cognitive tools (15):
    - store_memories      : persist one or more memories (nodes)
    - recall_memories     : fetch one or more memories by id (+ optional
                            details / connections per memory)
    - search_memory       : ranked search (FTS5/BM25 + graph expansion)
    - list_memories       : list stored memories (most important first)
    - update_memories     : modify one or more memories
    - forget_memories     : soft delete one or more memories (snapshots to trash)
    - edit_details        : add / update / delete attached facts (mixed batch)
    - edit_links          : link / unlink memory connections (mixed batch)
    - recall_related      : multi-hop recall of memories connected to one memory
    - connect_memories    : shortest connection (path) between two memories
    - memory_map          : nodes + links map of the memory graph
    - summarize_memories  : summary statistics over the memory graph
    - export_graph_html   : render full graph as standalone interactive 3D HTML
    - restore_memories    : manage soft-deleted trash, history & rollback
    - transfer_memories   : inline upload/download, keyset-paginated large-graph
                            migration, file migration + backup
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .memory import DEFAULT_RELATION, MemoryStore, default_data_dir

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "memory_graph.html"


def require_absolute_file_path(value: str, *, parameter: str) -> Path:
    """Validate a user-controlled file path without resolving dot segments."""
    if not value or not str(value).strip():
        raise ValueError(f"{parameter} is required")
    raw = str(value).strip()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{parameter} must be an absolute path")
    if any(part in {".", ".."} for part in raw.replace("\\", "/").split("/")):
        raise ValueError(f"{parameter} must not contain . or .. path segments")
    return path


class BearerKeyMiddleware:
    """Require a configured Bearer key for every request to an ASGI app."""

    def __init__(self, app: Any, key: str) -> None:
        self.app = app
        self.key = key

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        scheme, separator, supplied_key = authorization.partition(" ")
        authorized = (
            separator == " "
            and scheme.lower() == "bearer"
            and secrets.compare_digest(supplied_key, self.key)
        )
        if authorized:
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return

        body = b'{"error":"unauthorized"}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def create_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    data_dir: str | None = None,
) -> FastMCP:
    """Create and configure the BrainMemory-MCP :class:`FastMCP` server."""

    store = MemoryStore(data_dir=data_dir) if data_dir else MemoryStore()

    mcp = FastMCP(
        name="BrainMemory-MCP",
        instructions=(
            "Cognitive brain-memory for AI agents, modelled as a knowledge "
            "graph. Use these tools to persist durable memories across "
            "sessions, then recall/search them later. Store concise, "
            "self-contained facts; tag them and set an importance from 1 "
            "(trivial) to 5 (critical). Every write/fetch tool takes a LIST — "
            "acting on one item or many is the same call (a single item is "
            "just a list of one). Connect related memories with `edit_links` "
            "(op:'link') so you can later `recall_related` (multi-hop) or "
            "`connect_memories` (shortest path) for precise, contextual "
            "recall; attach or fix extra facts with `edit_details`. Search "
            "before storing to avoid duplicates."
        ),
        host=host,
        port=port,
    )

    # ----------------------------------------------------------------- tools #

    @mcp.tool()
    def store_memories(items: list[dict[str, Any]]) -> dict[str, Any]:
        """Persist one or more new memories in the brain.

        A single memory is just a list of one item.

        Args:
            items: List of memories to store. Each item is a dict with:
                ``content`` (required), ``category`` (default "general"),
                ``tags`` (optional list of keywords), ``importance``
                (1 trivial .. 5 critical, default 3).

        Returns:
            ``results`` has one entry per input item, in order, each with
            ``status`` ("stored" or "error") and, on success, the stored
            ``memory`` (including its generated ``id``).
        """
        results: list[dict[str, Any]] = []
        stored = 0
        for idx, item in enumerate(items):
            content = (item or {}).get("content")
            if not content or not str(content).strip():
                results.append({"index": idx, "status": "error", "error": "content is required"})
                continue
            try:
                mem = store.store(
                    content,
                    category=item.get("category", "general"),
                    tags=item.get("tags") or [],
                    importance=item.get("importance", 3),
                )
            except ValueError as exc:
                results.append({"index": idx, "status": "error", "error": str(exc)})
                continue
            results.append({"index": idx, "status": "stored", "memory": mem.to_dict()})
            stored += 1
        return {"status": "ok", "count": len(items), "stored": stored, "results": results}

    @mcp.tool()
    def recall_memories(
        memory_ids: list[str],
        include_details: bool = False,
        include_links: bool = False,
    ) -> dict[str, Any]:
        """Recall one or more memories by id.

        A single memory is just a list of one id. By default the response is
        lean (memory fields only); opt into the richer payload per memory with
        the include flags.

        Args:
            memory_ids: The ids returned when the memories were stored.
            include_details: Also include each memory's attached details
                (each with its ``id``, usable with `edit_details`).
            include_links: Also include each memory's connections
                (outgoing + incoming links).

        Returns:
            ``memories`` has one entry per requested id, in order, each with
            ``status`` ("ok" or "not_found").
        """
        results: list[dict[str, Any]] = []
        for mid in memory_ids:
            mem = store.get(mid)
            if mem is None:
                results.append({"id": mid, "status": "not_found"})
                continue
            entry: dict[str, Any] = {"id": mid, "status": "ok", "memory": mem.to_dict()}
            if include_details:
                entry["details"] = [d.to_dict() for d in store.list_details(mid)]
            if include_links:
                links = store.links_of(mid)
                entry["connections"] = {
                    "outgoing": [l.to_dict() for l in links["outgoing"]],
                    "incoming": [l.to_dict() for l in links["incoming"]],
                }
            results.append(entry)
        found = sum(1 for r in results if r["status"] == "ok")
        return {
            "status": "ok",
            "count": len(memory_ids),
            "found": found,
            "memories": results,
        }

    @mcp.tool()
    def search_memory(
        query: str = "",
        category: str | None = None,
        tags: list[str] | None = None,
        min_importance: int | None = None,
        limit: int = 20,
        expand: bool = True,
        mode: str = "any",
    ) -> dict[str, Any]:
        """Search memories like a search engine (ranked by relevance).

        Multi-word / long queries work: results are ranked by full-text
        relevance (BM25) blended with importance and recency — you do NOT need
        to reduce a question to a single keyword. Matching also covers any
        details attached to a memory. When ``expand`` is on, memories connected
        in the knowledge graph to a text hit are pulled in too, so related
        context surfaces even if it does not contain the query words.

        Args:
            query: Natural-language query or keywords (a full sentence is fine).
            category: Restrict to a single category.
            tags: Only memories containing ALL of these tags.
            min_importance: Only memories with importance >= this value (1..5).
            limit: Maximum number of results (default 20).
            expand: Also include graph-connected memories via spreading
                activation (default True).
            mode: "any" (match any term, default) or "all" (require every term).

        Returns:
            Ranked memories; each includes ``relevance`` (0..1), ``match_type``
            ("text" | "related" | "list"), ``matched_terms`` and ``distance``
            (hops from a text hit; 0 for direct hits).
        """
        results = store.search_scored(
            query=query or None,
            category=category,
            tags=tags or None,
            min_importance=min_importance,
            limit=limit,
            expand=expand,
            mode=mode,
        )
        return {
            "status": "ok",
            "count": len(results),
            "memories": results,
        }

    @mcp.tool()
    def list_memories(limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List stored memories, most important and most recent first.

        Args:
            limit: Maximum number of memories to return (default 100).
            offset: Number of memories to skip (for pagination).
        """
        results = store.list_all(limit=limit, offset=offset)
        return {
            "status": "ok",
            "count": len(results),
            "memories": [m.to_dict() for m in results],
        }

    @mcp.tool()
    def update_memories(updates: list[dict[str, Any]]) -> dict[str, Any]:
        """Update fields of one or more existing memories.

        A single memory is just a list of one item. Only supplied fields
        change.

        Args:
            updates: List of updates. Each item is a dict with:
                ``memory_id`` (required), and optionally ``content``,
                ``category``, ``tags`` (replacement list), ``importance``
                (1..5).

        Returns:
            ``results`` has one entry per input item, in order, each with
            ``status`` ("updated", "not_found" or "error") and, on success,
            the updated ``memory``.
        """
        results: list[dict[str, Any]] = []
        updated = 0
        for idx, item in enumerate(updates):
            memory_id = (item or {}).get("memory_id")
            if not memory_id:
                results.append({"index": idx, "status": "error", "error": "memory_id is required"})
                continue
            mem = store.update(
                memory_id,
                content=item.get("content"),
                category=item.get("category"),
                tags=item.get("tags"),
                importance=item.get("importance"),
            )
            if mem is None:
                results.append({"index": idx, "memory_id": memory_id, "status": "not_found"})
                continue
            results.append(
                {
                    "index": idx,
                    "memory_id": memory_id,
                    "status": "updated",
                    "memory": mem.to_dict(),
                }
            )
            updated += 1
        return {"status": "ok", "count": len(updates), "updated": updated, "results": results}

    @mcp.tool()
    def forget_memories(memory_ids: list[str]) -> dict[str, Any]:
        """Forget (soft delete) one or more memories by id.

        A single memory is just a list of one id. Each memory, its details, and
        its links are safely snapshotted into the trash (``memory_trash``)
        before removal, allowing recovery with `restore_memories`.

        Args:
            memory_ids: The ids of the memories to delete.

        Returns:
            ``results`` has one entry per input id, in order, each with
            ``status`` ("forgotten" or "not_found").
        """
        results: list[dict[str, Any]] = []
        removed = 0
        for memory_id in memory_ids:
            ok = store.forget(memory_id)
            results.append({"memory_id": memory_id, "status": "forgotten" if ok else "not_found"})
            if ok:
                removed += 1
        return {
            "status": "ok",
            "count": len(memory_ids),
            "removed": removed,
            "results": results,
        }

    @mcp.tool()
    def edit_details(items: list[dict[str, Any]]) -> dict[str, Any]:
        """Add, update, or delete extra facts (details) attached to memories.

        One call can mix operations across different memories. Each item's
        ``op`` selects the operation:

        - ``{"op": "add",    "memory_id": <id>, "content": <fact>}`` —
          attach a new detail; the result carries its ``detail`` (with ``id``).
        - ``{"op": "update", "detail_id": <id>, "content": <new fact>}`` —
          rewrite an existing detail's content.
        - ``{"op": "delete", "detail_id": <id>}`` — remove a single detail.

        Detail ids are returned by the "add" op and by
        `recall_memories(include_details=True)`.

        Args:
            items: List of operations (see shapes above).

        Returns:
            ``results`` has one entry per input item, in order, each with
            ``status`` ("added" / "updated" / "deleted", "not_found" or
            "error").
        """
        results: list[dict[str, Any]] = []
        applied = 0
        for idx, item in enumerate(items):
            op = str((item or {}).get("op", "")).strip().lower()
            if op == "add":
                memory_id = item.get("memory_id")
                content = item.get("content")
                if not memory_id or not content or not str(content).strip():
                    results.append(
                        {
                            "index": idx,
                            "op": "add",
                            "status": "error",
                            "error": "add requires memory_id and content",
                        }
                    )
                    continue
                detail = store.add_detail(memory_id, content)
                if detail is None:
                    results.append(
                        {
                            "index": idx,
                            "op": "add",
                            "memory_id": memory_id,
                            "status": "not_found",
                        }
                    )
                    continue
                results.append(
                    {
                        "index": idx,
                        "op": "add",
                        "status": "added",
                        "detail": detail.to_dict(),
                    }
                )
                applied += 1
            elif op == "update":
                detail_id = item.get("detail_id")
                content = item.get("content")
                if not detail_id or not content or not str(content).strip():
                    results.append(
                        {
                            "index": idx,
                            "op": "update",
                            "status": "error",
                            "error": "update requires detail_id and content",
                        }
                    )
                    continue
                detail = store.update_detail(detail_id, content)
                if detail is None:
                    results.append(
                        {
                            "index": idx,
                            "op": "update",
                            "detail_id": detail_id,
                            "status": "not_found",
                        }
                    )
                    continue
                results.append(
                    {
                        "index": idx,
                        "op": "update",
                        "status": "updated",
                        "detail": detail.to_dict(),
                    }
                )
                applied += 1
            elif op == "delete":
                detail_id = item.get("detail_id")
                if not detail_id:
                    results.append(
                        {
                            "index": idx,
                            "op": "delete",
                            "status": "error",
                            "error": "delete requires detail_id",
                        }
                    )
                    continue
                ok = store.delete_detail(detail_id)
                results.append(
                    {
                        "index": idx,
                        "op": "delete",
                        "detail_id": detail_id,
                        "status": "deleted" if ok else "not_found",
                    }
                )
                if ok:
                    applied += 1
            else:
                results.append(
                    {
                        "index": idx,
                        "status": "error",
                        "error": "op must be one of: add, update, delete",
                    }
                )
        return {"status": "ok", "count": len(items), "applied": applied, "results": results}

    @mcp.tool()
    def edit_links(items: list[dict[str, Any]]) -> dict[str, Any]:
        """Create or remove directed connections (links) between memories.

        One call can mix operations. Each item's ``op`` selects the operation:

        - ``{"op": "link", "from_id": <id>, "to_id": <id>,
          "relation": <str, default "related_to">, "weight": <float, default
          1.0>}`` — connect two memories. Re-linking the same
          from/to/relation updates the weight (upsert). Relations are free
          text, e.g. "related_to", "caused_by", "part_of", "depends_on".
        - ``{"op": "unlink", "from_id": <id>, "to_id": <id>,
          "relation": <optional>}`` — remove the connection(s) between two
          memories; if ``relation`` is omitted, every connection between the
          pair is removed.

        Building connections powers `recall_related` (multi-hop),
        `connect_memories` (shortest path), `memory_map`, and the graph
        expansion in `search_memory`.

        Args:
            items: List of operations (see shapes above).

        Returns:
            ``results`` has one entry per input item, in order, each with
            ``status`` ("linked" / "unlinked", "not_found" or "error"); the
            "unlink" results include ``removed`` (number of connections
            removed).
        """
        results: list[dict[str, Any]] = []
        applied = 0
        for idx, item in enumerate(items):
            op = str((item or {}).get("op", "")).strip().lower()
            from_id = (item or {}).get("from_id")
            to_id = (item or {}).get("to_id")
            if op == "link":
                if not from_id or not to_id:
                    results.append(
                        {
                            "index": idx,
                            "op": "link",
                            "status": "error",
                            "error": "link requires from_id and to_id",
                        }
                    )
                    continue
                try:
                    link = store.link(
                        from_id,
                        to_id,
                        relation=item.get("relation", DEFAULT_RELATION),
                        weight=item.get("weight", 1.0),
                    )
                except ValueError as exc:
                    results.append(
                        {
                            "index": idx,
                            "op": "link",
                            "from_id": from_id,
                            "to_id": to_id,
                            "status": "error",
                            "error": str(exc),
                        }
                    )
                    continue
                if link is None:
                    results.append(
                        {
                            "index": idx,
                            "op": "link",
                            "from_id": from_id,
                            "to_id": to_id,
                            "status": "not_found",
                        }
                    )
                    continue
                results.append(
                    {
                        "index": idx,
                        "op": "link",
                        "status": "linked",
                        "connection": link.to_dict(),
                    }
                )
                applied += 1
            elif op == "unlink":
                if not from_id or not to_id:
                    results.append(
                        {
                            "index": idx,
                            "op": "unlink",
                            "status": "error",
                            "error": "unlink requires from_id and to_id",
                        }
                    )
                    continue
                removed = store.unlink(from_id, to_id, relation=item.get("relation"))
                results.append(
                    {
                        "index": idx,
                        "op": "unlink",
                        "from_id": from_id,
                        "to_id": to_id,
                        "status": "unlinked" if removed else "not_found",
                        "removed": removed,
                    }
                )
                if removed:
                    applied += 1
            else:
                results.append(
                    {
                        "index": idx,
                        "status": "error",
                        "error": "op must be one of: link, unlink",
                    }
                )
        return {"status": "ok", "count": len(items), "applied": applied, "results": results}

    @mcp.tool()
    def recall_related(
        memory_id: str,
        depth: int = 1,
        relation: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Recall memories connected to a memory, up to ``depth`` hops away.

        This is the precise, graph-aware recall: instead of matching words, it
        walks the connections built with `edit_links`.

        Args:
            memory_id: The memory to start from.
            depth: How many hops to traverse (1 = direct neighbours). Default 1.
            relation: Only traverse connections of this relation type (optional).
            limit: Maximum number of related memories to return (default 50).
        """
        result = store.recall_related(memory_id, depth=depth, relation=relation, limit=limit)
        if result is None:
            return {"status": "not_found", "memory_id": memory_id}
        return {"status": "ok", **result}

    @mcp.tool()
    def connect_memories(
        from_id: str,
        to_id: str,
        max_depth: int = 6,
    ) -> dict[str, Any]:
        """Find the shortest connection (path) between two memories.

        Explains *how* two memories relate by returning the chain of memories and
        links that connect them.

        Args:
            from_id: Source memory id.
            to_id: Target memory id.
            max_depth: Maximum path length to search (default 6).
        """
        result = store.connect_memories(from_id, to_id, max_depth=max_depth)
        if result is None:
            return {"status": "not_found", "from_id": from_id, "to_id": to_id}
        return {"status": "ok", **result}

    @mcp.tool()
    def memory_map(
        memory_id: str | None = None,
        depth: int = 2,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Return a map (nodes + links) of the memory graph.

        Args:
            memory_id: If given, map the neighbourhood around this memory;
                otherwise map the whole graph (capped by ``limit``).
            depth: Hops to include around ``memory_id`` (default 2).
            limit: Maximum number of nodes to include (default 100).
        """
        result = store.memory_map(memory_id, depth=depth, limit=limit)
        return {"status": "ok", **result}

    @mcp.tool()
    def summarize_memories() -> dict[str, Any]:
        """Summarize the brain memory: totals, categories, top tags, connections."""
        return {"status": "ok", "summary": store.stats()}

    # -- new tools (v0.10.0) ------------------------------------------------ #

    @mcp.tool()
    def export_graph_html(
        output_path: str,
        category: str | None = None,
        tags: list[str] | None = None,
        label_length: int = 80,
    ) -> dict[str, Any]:
        """Render the complete knowledge graph into a 3D interactive HTML file.

        Args:
            output_path: Absolute destination file path. Relative paths and paths
                containing ``.`` or ``..`` segments are rejected.
            category: Optional category filter.
            tags: Optional tags filter (all must match).
            label_length: Max characters for node labels in graph.
        """
        import json

        try:
            out_file = require_absolute_file_path(output_path, parameter="output_path")
        except ValueError as exc:
            return {"status": "error", "error": str(exc)}
        if not _TEMPLATE_PATH.exists():
            return {"status": "error", "error": f"template file missing at {_TEMPLATE_PATH}"}

        template = _TEMPLATE_PATH.read_text(encoding="utf-8")
        graph_data = store.export_graph(category=category, tags=tags, label_length=label_length)
        rendered = template.replace(
            "/*__GRAPH_DATA__*/", json.dumps(graph_data, ensure_ascii=False)
        )
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(rendered, encoding="utf-8")
        return {
            "status": "ok",
            "output_path": str(out_file),
            "nodes_count": len(graph_data["nodes"]),
            "links_count": len(graph_data["links"]),
            "bytes": len(rendered.encode("utf-8")),
        }

    @mcp.tool()
    def restore_memories(items: list[dict[str, Any]]) -> dict[str, Any]:
        """Soft delete safety net: manage trashed memories, history & rollback.

        Each item in ``items`` is a dict with an ``op`` field selecting the
        action:

        - ``{"op": "list_trash", "limit": 50}`` — list trashed (forgotten)
          memories.
        - ``{"op": "restore", "memory_id": <id>}`` — bring a trashed memory
          back, including its details and valid connections.
        - ``{"op": "purge_trash", "memory_ids": [<id>...], "older_than_days": 30}``
          — permanently remove entries from the trash (irreversible).
        - ``{"op": "history", "memory_id": <id>, "limit": 20}`` — view past
          versions of a memory.
        - ``{"op": "rollback", "memory_id": <id>, "version_id": <ver_id>}`` —
          revert a memory to a historical version.

        Args:
            items: List of mixed operations (see shapes above).

        Returns:
            ``results`` list with per-item status and results.
        """
        results: list[dict[str, Any]] = []
        applied = 0
        for idx, item in enumerate(items):
            op = str((item or {}).get("op", "")).strip().lower()
            if op == "list_trash":
                limit = item.get("limit", 50)
                trash = store.list_trash(limit=limit)
                results.append(
                    {
                        "index": idx,
                        "op": "list_trash",
                        "status": "ok",
                        "count": len(trash),
                        "trash": trash,
                    }
                )
                applied += 1
            elif op == "restore":
                mid = item.get("memory_id")
                if not mid:
                    results.append(
                        {
                            "index": idx,
                            "op": "restore",
                            "status": "error",
                            "error": "memory_id is required",
                        }
                    )
                    continue
                res = store.restore(mid)
                if res is None:
                    results.append(
                        {
                            "index": idx,
                            "op": "restore",
                            "memory_id": mid,
                            "status": "not_found",
                        }
                    )
                    continue
                results.append({"index": idx, "op": "restore", "memory_id": mid, **res})
                if res.get("status") == "restored":
                    applied += 1
            elif op == "purge_trash":
                mids = item.get("memory_ids")
                older_than = item.get("older_than_days")
                purged = store.purge_trash(memory_ids=mids, older_than_days=older_than)
                results.append(
                    {
                        "index": idx,
                        "op": "purge_trash",
                        "status": "ok",
                        "purged": purged,
                    }
                )
                applied += 1
            elif op == "history":
                mid = item.get("memory_id")
                if not mid:
                    results.append(
                        {
                            "index": idx,
                            "op": "history",
                            "status": "error",
                            "error": "memory_id is required",
                        }
                    )
                    continue
                hist = store.history_of(mid, limit=item.get("limit", 20))
                results.append(
                    {
                        "index": idx,
                        "op": "history",
                        "memory_id": mid,
                        "status": "ok",
                        "count": len(hist),
                        "history": hist,
                    }
                )
                applied += 1
            elif op == "rollback":
                mid = item.get("memory_id")
                vid = item.get("version_id")
                if not mid or not vid:
                    results.append(
                        {
                            "index": idx,
                            "op": "rollback",
                            "status": "error",
                            "error": "memory_id and version_id are required",
                        }
                    )
                    continue
                mem = store.rollback(mid, vid)
                if mem is None:
                    results.append(
                        {
                            "index": idx,
                            "op": "rollback",
                            "memory_id": mid,
                            "version_id": vid,
                            "status": "not_found",
                        }
                    )
                    continue
                results.append(
                    {
                        "index": idx,
                        "op": "rollback",
                        "memory_id": mid,
                        "status": "rolled_back",
                        "memory": mem.to_dict(),
                    }
                )
                applied += 1
            else:
                results.append(
                    {
                        "index": idx,
                        "status": "error",
                        "error": "op must be one of: list_trash, restore, purge_trash, history, rollback",
                    }
                )
        return {"status": "ok", "count": len(items), "applied": applied, "results": results}

    @mcp.tool()
    def transfer_memories(
        op: str,
        data: dict[str, Any] | None = None,
        input_path: str | None = None,
        output_path: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        on_conflict: str = "skip",
        scope: str = "all",
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Upload/download graph data or use server-local migration files.

        Inline ``data`` is transport-safe: an export can be downloaded in the
        MCP result and passed directly to an HTTP/SSE server for import. Paths
        remain available for same-host workflows and database backups.

        For large graphs moving between two independent servers that share no
        filesystem (e.g. local stdio <-> remote HTTP/SSE), a single ``export``
        can be too big for the calling agent's context. Pass ``limit`` (and
        ``scope="memories"`` or ``scope="links"``) to page through the graph
        instead: each call returns at most ``limit`` rows plus ``has_more`` /
        ``next_cursor``; keep calling with the returned ``cursor`` until
        ``has_more`` is ``false``, feeding each page's ``data`` straight into
        an ``import`` call on the destination. Page through every
        ``scope="memories"`` batch first, then ``scope="links"`` — importing
        a link before both its endpoint memories exist just skips it
        (reported in ``links_skipped``), it never corrupts data.

        Args:
            op: Operation to perform: ``export``, ``import``, or ``backup``.
            data: Migration object uploaded directly for import.
            input_path: Optional server-local absolute JSON path for import.
            output_path: Optional server-local absolute JSON path for export.
            category: Optional category filter for export.
            tags: Optional tags filter for export (all must match).
            on_conflict: Import handling: ``skip`` (default) or ``overwrite``.
            scope: Export scope: ``"all"`` (default), ``"memories"``,
                ``"links"``, or ``"trash"``. ``limit``/``cursor`` pagination
                requires a single scope (not ``"all"``).
            limit: Max rows to export in this call (enables pagination).
            cursor: Opaque cursor from a previous export's ``next_cursor``.
        """
        import json

        op_norm = str(op or "").strip().lower()
        if op_norm == "export":
            try:
                if str(scope or "all").strip().lower() == "trash":
                    if category or tags:
                        raise ValueError("category/tags filters are not supported for scope='trash'")
                    payload = store.export_trash(limit=limit, cursor=cursor)
                else:
                    payload = store.export_data(
                        category=category, tags=tags, scope=scope, limit=limit, cursor=cursor
                    )
            except ValueError as exc:
                return {"status": "error", "error": str(exc)}
            pagination = payload["pagination"]
            result: dict[str, Any] = {
                "status": "ok",
                "op": "export",
                "scope": payload["scope"],
                "counts": payload["counts"],
                "has_more": pagination["has_more"],
                "next_cursor": pagination["next_cursor"],
                "data": payload,
            }
            if output_path:
                try:
                    target = require_absolute_file_path(output_path, parameter="output_path")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(
                        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                except (ValueError, OSError) as exc:
                    return {"status": "error", "error": str(exc)}
                result.update(output_path=str(target), bytes=target.stat().st_size)
            return result
        if op_norm == "import":
            if data is not None and input_path:
                return {
                    "status": "error",
                    "error": "provide either data or input_path, not both",
                }
            source: Path | None = None
            try:
                if data is None:
                    source = require_absolute_file_path(
                        input_path or "", parameter="input_path or data"
                    )
                    data = json.loads(source.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise TypeError("data must be a migration JSON object")
                if data.get("scope") == "trash" or "trash" in data:
                    summary = store.import_trash(data, on_conflict=on_conflict)
                else:
                    summary = store.import_data(data, on_conflict=on_conflict)
            except (TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
                return {"status": "error", "error": str(exc)}
            result = {"status": "ok", "op": "import", "source": "upload", **summary}
            if source is not None:
                result.update(source="file", input_path=str(source))
            return result
        if op_norm == "backup":
            path = store.backup_now()
            return {"status": "ok", "op": "backup", "backup_path": str(path)}
        return {
            "status": "error",
            "error": "op must be one of: export, import, backup",
        }

    # ------------------------------------------------------------- resources #

    @mcp.resource("brainmemory://stats")
    def stats_resource() -> str:
        """Live summary statistics of the stored memories (JSON)."""
        import json

        return json.dumps(store.stats(), indent=2)

    @mcp.resource("brainmemory://graph")
    def graph_resource() -> str:
        """Live map of the memory graph: nodes + links (JSON)."""
        import json

        return json.dumps(store.memory_map(), indent=2)

    return mcp


def run(
    *,
    web: bool = False,
    host: str = "127.0.0.1",
    port: int = 8765,
    data_dir: str | None = None,
    key: str | None = None,
) -> None:
    """Create the server and run it.

    Args:
        web: When ``True``, serve over HTTP + SSE. Otherwise use stdio
            (the default), suitable for ``uvx brainmemory-mcp`` and clients
            that launch the server as a subprocess.
        host: Interface to bind in web mode.
        port: TCP port to listen on in web mode.
        data_dir: Directory to persist memories in.
        key: Optional Bearer key required by every request in web mode.
    """
    server = create_server(host=host, port=port, data_dir=data_dir)
    resolved_dir = data_dir or str(default_data_dir())

    if web:
        # Web (SSE) mode: it is safe to log to stdout.
        auth_status = "Bearer key required" if key else "disabled"
        print(
            f"BrainMemory-MCP (SSE) listening on http://{host}:{port}/sse\n"
            f"  message endpoint : http://{host}:{port}/messages/\n"
            f"  authorization    : {auth_status}\n"
            f"  memory directory : {resolved_dir}",
            flush=True,
        )
        if key:
            import uvicorn

            app = BearerKeyMiddleware(server.sse_app(), key)
            uvicorn.run(app, host=host, port=port, log_level="info")
        else:
            server.run(transport="sse")
    else:
        # stdio mode: stdout is reserved for the MCP protocol, so log to stderr.
        print(
            f"BrainMemory-MCP (stdio) ready.\n" f"  memory directory : {resolved_dir}",
            file=sys.stderr,
            flush=True,
        )
        server.run(transport="stdio")
