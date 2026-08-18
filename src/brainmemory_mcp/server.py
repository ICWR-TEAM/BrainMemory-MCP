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

Cognitive tools:
    - store_memory        : persist a new memory (node)
    - store_memories       : persist multiple memories in one call
    - recall_memory        : fetch a memory by id, with its details + connections
    - recall_memories       : fetch multiple memories by id in one call
    - search_memory         : find memories by text / category / tags / importance
    - list_memories         : list stored memories (most important first)
    - update_memory         : modify an existing memory
    - update_memories       : modify multiple memories in one call
    - forget_memory         : delete a memory (its details + links cascade away)
    - forget_memories        : delete multiple memories in one call
    - add_detail            : attach an extra fact to an existing memory
    - add_details            : attach multiple facts in one call
    - link_memories          : connect two memories with a directed relation
    - link_memories_bulk      : connect multiple pairs of memories in one call
    - unlink_memories        : remove connection(s) between two memories
    - unlink_memories_bulk    : remove connection(s) for multiple pairs in one call
    - recall_related         : multi-hop recall of memories connected to one memory
    - connect_memories       : shortest connection (path) between two memories
    - memory_map             : nodes + links map of the memory graph
    - summarize_memories     : summary statistics over the memory graph

Bulk tools accept a list of per-item dicts and never abort on a single bad
item: each item gets its own per-item status in the response (``"ok"`` /
``"not_found"`` / ``"error"``) alongside an overall count, so one call can
replace many round-trips without losing partial progress.
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
            "(trivial) to 5 (critical). Connect related memories with "
            "`link_memories` so you can later `recall_related` (multi-hop) or "
            "`connect_memories` (shortest path) for precise, contextual "
            "recall. Search before storing to avoid duplicates. When you need "
            "to store, fetch, update, forget, link, or unlink several "
            "memories at once, prefer the `_bulk`/plural tools "
            "(`store_memories`, `recall_memories`, `update_memories`, "
            "`forget_memories`, `add_details`, `link_memories_bulk`, "
            "`unlink_memories_bulk`) over repeated single-item calls — one "
            "call, one response, less overhead."
        ),
        host=host,
        port=port,
    )

    # ----------------------------------------------------------------- tools #

    @mcp.tool()
    def store_memory(
        content: str,
        category: str = "general",
        tags: list[str] | None = None,
        importance: int = 3,
    ) -> dict[str, Any]:
        """Persist a new memory in the brain.

        Args:
            content: The information to remember (a concise, self-contained fact).
            category: A grouping label, e.g. "preferences", "facts", "tasks".
            tags: Optional keywords to make the memory easier to find later.
            importance: 1 (trivial) .. 5 (critical). Defaults to 3.

        Returns:
            The stored memory including its generated ``id``.
        """
        mem = store.store(
            content,
            category=category,
            tags=tags or [],
            importance=importance,
        )
        return {"status": "stored", "memory": mem.to_dict()}

    @mcp.tool()
    def store_memories(items: list[dict[str, Any]]) -> dict[str, Any]:
        """Persist multiple memories in one call (bulk `store_memory`).

        Use this instead of calling `store_memory` in a loop when importing or
        recording several facts at once — one round-trip instead of many.

        Args:
            items: List of memories to store. Each item is a dict with:
                ``content`` (required), ``category`` (default "general"),
                ``tags`` (optional list), ``importance`` (default 3).

        Returns:
            ``results`` has one entry per input item, in order, each with
            ``status`` ("stored" or "error") and, on success, the new ``id``.
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
            results.append({"index": idx, "status": "stored", "id": mem.id})
            stored += 1
        return {"status": "ok", "count": len(items), "stored": stored, "results": results}

    @mcp.tool()
    def recall_memory(memory_id: str) -> dict[str, Any]:
        """Recall a single memory by its id, with its details and connections.

        Args:
            memory_id: The id returned when the memory was stored.
        """
        mem = store.get(memory_id)
        if mem is None:
            return {"status": "not_found", "memory_id": memory_id}
        details = store.list_details(memory_id)
        links = store.links_of(memory_id)
        return {
            "status": "ok",
            "memory": mem.to_dict(),
            "details": [d.to_dict() for d in details],
            "connections": {
                "outgoing": [l.to_dict() for l in links["outgoing"]],
                "incoming": [l.to_dict() for l in links["incoming"]],
            },
        }

    @mcp.tool()
    def recall_memories(
        memory_ids: list[str],
        include_connections: bool = False,
    ) -> dict[str, Any]:
        """Recall multiple memories by id in one call (bulk `recall_memory`).

        Useful after a `search_memory` call to fetch several hits at once
        instead of one `recall_memory` call per id.

        Args:
            memory_ids: The ids to fetch.
            include_connections: If True, also include each memory's details
                and connections (more output per item). Defaults to False for
                a leaner response.

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
            if include_connections:
                details = store.list_details(mid)
                links = store.links_of(mid)
                entry["details"] = [d.to_dict() for d in details]
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
    def update_memory(
        memory_id: str,
        content: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        importance: int | None = None,
    ) -> dict[str, Any]:
        """Update fields of an existing memory (only provided fields change).

        Args:
            memory_id: The id of the memory to update.
            content: New content (optional).
            category: New category (optional).
            tags: Replacement tag list (optional).
            importance: New importance 1..5 (optional).
        """
        mem = store.update(
            memory_id,
            content=content,
            category=category,
            tags=tags,
            importance=importance,
        )
        if mem is None:
            return {"status": "not_found", "memory_id": memory_id}
        return {"status": "updated", "memory": mem.to_dict()}

    @mcp.tool()
    def update_memories(updates: list[dict[str, Any]]) -> dict[str, Any]:
        """Update multiple memories in one call (bulk `update_memory`).

        Handy for batch corrections, e.g. re-tagging or re-scoring importance
        across several memories at once.

        Args:
            updates: List of updates. Each item is a dict with:
                ``memory_id`` (required), and optionally ``content``,
                ``category``, ``tags``, ``importance`` (only supplied fields
                change, same semantics as `update_memory`).

        Returns:
            ``results`` has one entry per input item, in order, each with
            ``status`` ("updated", "not_found" or "error").
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
            results.append({"index": idx, "memory_id": memory_id, "status": "updated"})
            updated += 1
        return {"status": "ok", "count": len(updates), "updated": updated, "results": results}

    @mcp.tool()
    def forget_memory(memory_id: str) -> dict[str, Any]:
        """Forget (delete) a memory by its id.

        The memory's details and any connections to/from it are removed too.

        Args:
            memory_id: The id of the memory to delete.
        """
        removed = store.forget(memory_id)
        return {
            "status": "forgotten" if removed else "not_found",
            "memory_id": memory_id,
        }

    @mcp.tool()
    def forget_memories(memory_ids: list[str]) -> dict[str, Any]:
        """Forget (delete) multiple memories by id in one call (bulk `forget_memory`).

        Each memory's details and connections cascade away too. Handy for
        cleaning up duplicates or a batch of stale memories.

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
    def add_detail(memory_id: str, content: str) -> dict[str, Any]:
        """Attach an extra fact/observation to an existing memory.

        Use this to enrich a memory over time without creating a duplicate.

        Args:
            memory_id: The memory to attach the detail to.
            content: The extra fact to remember about that memory.
        """
        detail = store.add_detail(memory_id, content)
        if detail is None:
            return {"status": "not_found", "memory_id": memory_id}
        return {"status": "added", "detail": detail.to_dict()}

    @mcp.tool()
    def add_details(items: list[dict[str, Any]]) -> dict[str, Any]:
        """Attach multiple facts to memories in one call (bulk `add_detail`).

        Items may target different memories, so this doubles as a way to
        enrich several memories in one round-trip.

        Args:
            items: List of details to add. Each item is a dict with:
                ``memory_id`` (required) and ``content`` (required).

        Returns:
            ``results`` has one entry per input item, in order, each with
            ``status`` ("added", "not_found" or "error").
        """
        results: list[dict[str, Any]] = []
        added = 0
        for idx, item in enumerate(items):
            memory_id = (item or {}).get("memory_id")
            content = (item or {}).get("content")
            if not memory_id or not content or not str(content).strip():
                results.append(
                    {
                        "index": idx,
                        "status": "error",
                        "error": "memory_id and content are required",
                    }
                )
                continue
            detail = store.add_detail(memory_id, content)
            if detail is None:
                results.append(
                    {"index": idx, "memory_id": memory_id, "status": "not_found"}
                )
                continue
            results.append(
                {
                    "index": idx,
                    "memory_id": memory_id,
                    "status": "added",
                    "detail_id": detail.id,
                }
            )
            added += 1
        return {"status": "ok", "count": len(items), "added": added, "results": results}

    @mcp.tool()
    def link_memories(
        from_id: str,
        to_id: str,
        relation: str = DEFAULT_RELATION,
        weight: float = 1.0,
    ) -> dict[str, Any]:
        """Connect two memories with a directed relation.

        Building connections lets you later `recall_related` (multi-hop) and
        `connect_memories` (shortest path) for precise, contextual recall.
        Re-linking the same pair+relation updates the weight.

        Args:
            from_id: Source memory id.
            to_id: Target memory id.
            relation: The relationship, e.g. "related_to", "caused_by",
                "part_of", "depends_on". Defaults to "related_to".
            weight: Strength/confidence of the connection (default 1.0).
        """
        try:
            link = store.link(from_id, to_id, relation=relation, weight=weight)
        except ValueError as exc:
            return {"status": "error", "error": str(exc)}
        if link is None:
            return {"status": "not_found", "from_id": from_id, "to_id": to_id}
        return {"status": "linked", "connection": link.to_dict()}

    @mcp.tool()
    def link_memories_bulk(links: list[dict[str, Any]]) -> dict[str, Any]:
        """Create multiple connections between memories in one call (bulk `link_memories`).

        Ideal for building out a chunk of the knowledge graph at once, e.g.
        after storing a batch of related memories.

        Args:
            links: List of connections to create. Each item is a dict with:
                ``from_id`` (required), ``to_id`` (required), ``relation``
                (default "related_to"), ``weight`` (default 1.0).

        Returns:
            ``results`` has one entry per input item, in order, each with
            ``status`` ("linked", "not_found" or "error").
        """
        results: list[dict[str, Any]] = []
        linked = 0
        for idx, item in enumerate(links):
            from_id = (item or {}).get("from_id")
            to_id = (item or {}).get("to_id")
            if not from_id or not to_id:
                results.append(
                    {
                        "index": idx,
                        "status": "error",
                        "error": "from_id and to_id are required",
                    }
                )
                continue
            relation = item.get("relation", DEFAULT_RELATION)
            weight = item.get("weight", 1.0)
            try:
                link = store.link(from_id, to_id, relation=relation, weight=weight)
            except ValueError as exc:
                results.append(
                    {
                        "index": idx,
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
                        "from_id": from_id,
                        "to_id": to_id,
                        "status": "not_found",
                    }
                )
                continue
            results.append(
                {
                    "index": idx,
                    "from_id": from_id,
                    "to_id": to_id,
                    "relation": link.relation,
                    "status": "linked",
                }
            )
            linked += 1
        return {"status": "ok", "count": len(links), "linked": linked, "results": results}

    @mcp.tool()
    def unlink_memories(
        from_id: str,
        to_id: str,
        relation: str | None = None,
    ) -> dict[str, Any]:
        """Remove connection(s) between two memories.

        Args:
            from_id: Source memory id.
            to_id: Target memory id.
            relation: If given, only remove this relation; otherwise remove every
                connection between the two memories.
        """
        removed = store.unlink(from_id, to_id, relation=relation)
        return {
            "status": "unlinked" if removed else "not_found",
            "removed": removed,
            "from_id": from_id,
            "to_id": to_id,
        }

    @mcp.tool()
    def unlink_memories_bulk(links: list[dict[str, Any]]) -> dict[str, Any]:
        """Remove connections for multiple memory pairs in one call (bulk `unlink_memories`).

        Args:
            links: List of pairs to unlink. Each item is a dict with:
                ``from_id`` (required), ``to_id`` (required), and optional
                ``relation`` (if omitted, every connection between the pair is
                removed).

        Returns:
            ``results`` has one entry per input item, in order, each with
            ``status`` ("unlinked", "not_found" or "error") and the number of
            connections ``removed`` for that item.
        """
        results: list[dict[str, Any]] = []
        unlinked = 0
        for idx, item in enumerate(links):
            from_id = (item or {}).get("from_id")
            to_id = (item or {}).get("to_id")
            if not from_id or not to_id:
                results.append(
                    {
                        "index": idx,
                        "status": "error",
                        "error": "from_id and to_id are required",
                    }
                )
                continue
            relation = item.get("relation")
            removed = store.unlink(from_id, to_id, relation=relation)
            results.append(
                {
                    "index": idx,
                    "from_id": from_id,
                    "to_id": to_id,
                    "status": "unlinked" if removed else "not_found",
                    "removed": removed,
                }
            )
            if removed:
                unlinked += 1
        return {
            "status": "ok",
            "count": len(links),
            "unlinked": unlinked,
            "results": results,
        }

    @mcp.tool()
    def recall_related(
        memory_id: str,
        depth: int = 1,
        relation: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Recall memories connected to a memory, up to ``depth`` hops away.

        This is the precise, graph-aware recall: instead of matching words, it
        walks the connections you built with `link_memories`.

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
