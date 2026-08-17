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
    - recall_memory       : fetch a memory by id, with its details + connections
    - search_memory       : find memories by text / category / tags / importance
    - list_memories       : list stored memories (most important first)
    - update_memory       : modify an existing memory
    - forget_memory       : delete a memory (its details + links cascade away)
    - add_detail          : attach an extra fact to an existing memory
    - link_memories       : connect two memories with a directed relation
    - unlink_memories     : remove connection(s) between two memories
    - recall_related      : multi-hop recall of memories connected to one memory
    - connect_memories    : shortest connection (path) between two memories
    - memory_map          : nodes + links map of the memory graph
    - summarize_memories  : summary statistics over the memory graph
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
            "recall. Search before storing to avoid duplicates."
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
    def search_memory(
        query: str = "",
        category: str | None = None,
        tags: list[str] | None = None,
        min_importance: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search memories by free text, category, tags and/or importance.

        Args:
            query: Free-text matched against content, tags, category and any
                details attached to a memory.
            category: Restrict to a single category.
            tags: Only memories containing ALL of these tags.
            min_importance: Only memories with importance >= this value (1..5).
            limit: Maximum number of results (default 20).

        Returns:
            A list of matching memories, most important & most recent first.
        """
        results = store.search(
            query=query or None,
            category=category,
            tags=tags or None,
            min_importance=min_importance,
            limit=limit,
        )
        return {
            "status": "ok",
            "count": len(results),
            "memories": [m.to_dict() for m in results],
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
