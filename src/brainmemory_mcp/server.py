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

Since v0.9.0 the tool surface is **consolidated**: every operation takes a
list, so acting on one memory or fifty is the same call. Detail and link
writes are unified into one mixed-operation batch tool per entity
(``edit_details`` / ``edit_links``), giving full CRUD over all three entities
with just 12 tools.

Cognitive tools (12):
    - store_memories      : persist one or more memories (nodes)
    - recall_memories     : fetch one or more memories by id (+ optional
                            details / connections per memory)
    - search_memory       : ranked search (FTS5/BM25 + graph expansion)
    - list_memories       : list stored memories (most important first)
    - update_memories     : modify one or more memories
    - forget_memories     : delete one or more memories (details + links cascade)
    - edit_details        : add / update / delete attached facts (mixed batch)
    - edit_links          : link / unlink memory connections (mixed batch)
    - recall_related      : multi-hop recall of memories connected to one memory
    - connect_memories    : shortest connection (path) between two memories
    - memory_map          : nodes + links map of the memory graph
    - summarize_memories  : summary statistics over the memory graph

Every list-taking tool processes its items independently and reports a
per-item ``status`` (never aborting the whole batch on one bad item), plus an
overall ``count`` and success counter.
"""

from __future__ import annotations

import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from .memory import DEFAULT_RELATION, MemoryStore, default_data_dir

# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #


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
                results.append(
                    {"index": idx, "status": "error", "error": "content is required"}
                )
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
                results.append(
                    {"index": idx, "status": "error", "error": "memory_id is required"}
                )
                continue
            mem = store.update(
                memory_id,
                content=item.get("content"),
                category=item.get("category"),
                tags=item.get("tags"),
                importance=item.get("importance"),
            )
            if mem is None:
                results.append(
                    {"index": idx, "memory_id": memory_id, "status": "not_found"}
                )
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
        """Forget (delete) one or more memories by id.

        A single memory is just a list of one id. Each memory's details and
        any connections to/from it are removed too (cascade).

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
            results.append(
                {"memory_id": memory_id, "status": "forgotten" if ok else "not_found"}
            )
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
        result = store.recall_related(
            memory_id, depth=depth, relation=relation, limit=limit
        )
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
) -> None:
    """Create the server and run it.

    Args:
        web: When ``True``, serve over HTTP + SSE. Otherwise use stdio
            (the default), suitable for ``uvx brainmemory-mcp`` and clients
            that launch the server as a subprocess.
        host: Interface to bind in web mode.
        port: TCP port to listen on in web mode.
        data_dir: Directory to persist memories in.
    """
    server = create_server(host=host, port=port, data_dir=data_dir)
    resolved_dir = data_dir or str(default_data_dir())

    if web:
        # Web (SSE) mode: it is safe to log to stdout.
        print(
            f"BrainMemory-MCP (SSE) listening on http://{host}:{port}/sse\n"
            f"  message endpoint : http://{host}:{port}/messages/\n"
            f"  memory directory : {resolved_dir}",
            flush=True,
        )
        server.run(transport="sse")
    else:
        # stdio mode: stdout is reserved for the MCP protocol, so log to stderr.
        print(
            f"BrainMemory-MCP (stdio) ready.\n"
            f"  memory directory : {resolved_dir}",
            file=sys.stderr,
            flush=True,
        )
        server.run(transport="stdio")
