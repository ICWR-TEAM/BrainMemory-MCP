"""BrainMemory-MCP server.

Exposes Cognitive memory tools over the Model Context Protocol using the
HTTP + Server-Sent Events (SSE) transport. Built on the official ``mcp`` SDK
(``FastMCP``).

Cognitive tools:
    - store_memory        : persist a new memory
    - recall_memory       : fetch a single memory by id
    - search_memory       : find memories by text / category / tags / importance
    - list_memories       : list stored memories (most important first)
    - update_memory       : modify an existing memory
    - forget_memory       : delete a memory
    - summarize_memories  : summary statistics over stored memories
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .memory import MemoryStore, default_data_dir

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
            "Cognitive brain-memory for AI agents. Use these tools to persist "
            "durable memories across sessions, then recall/search them later. "
            "Store concise, self-contained facts; tag them and set an "
            "importance from 1 (trivial) to 5 (critical). Search before "
            "storing to avoid duplicates."
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
        """Recall a single memory by its id.

        Args:
            memory_id: The id returned when the memory was stored.
        """
        mem = store.get(memory_id)
        if mem is None:
            return {"status": "not_found", "memory_id": memory_id}
        return {"status": "ok", "memory": mem.to_dict()}

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
            query: Free-text matched against content, tags and category.
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

        Args:
            memory_id: The id of the memory to delete.
        """
        removed = store.forget(memory_id)
        return {
            "status": "forgotten" if removed else "not_found",
            "memory_id": memory_id,
        }

    @mcp.tool()
    def summarize_memories() -> dict[str, Any]:
        """Summarize the brain memory: totals, categories, top tags, etc."""
        return {"status": "ok", "summary": store.stats()}

    # ------------------------------------------------------------- resources #

    @mcp.resource("brainmemory://stats")
    def stats_resource() -> str:
        """Live summary statistics of the stored memories (JSON)."""
        import json

        return json.dumps(store.stats(), indent=2)

    return mcp


def run(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    data_dir: str | None = None,
) -> None:
    """Create the server and run it over the SSE transport."""
    server = create_server(host=host, port=port, data_dir=data_dir)
    resolved_dir = data_dir or str(default_data_dir())
    print(
        f"BrainMemory-MCP (SSE) listening on http://{host}:{port}/sse\n"
        f"  message endpoint : http://{host}:{port}/messages/\n"
        f"  memory directory : {resolved_dir}",
        flush=True,
    )
    server.run(transport="sse")
