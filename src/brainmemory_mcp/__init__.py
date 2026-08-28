"""BrainMemory-MCP — Cognitive memory tools served over stdio or HTTP + SSE.

A Model Context Protocol (MCP) server that gives AI/LLM agents a durable
"brain memory": the ability to store, recall, search, connect, update,
summarize, and forget information across sessions through standardized MCP tool
calls.

Since v0.4.0 memory is modelled as a small **knowledge graph** — memories are
nodes, connections between them are directed links, and extra facts attach as
details — enabling precise, multi-hop recall while keeping a "memory"-oriented
tool vocabulary.

Since v0.5.0 search works like a small **search engine**: a SQLite FTS5 index
ranks results with BM25 (multi-word / long queries welcome), and graph
**spreading activation** pulls in connected memories so related context
surfaces. Falls back to a tokenised LIKE scorer where FTS5 is unavailable.

Since v0.9.0 the tool surface is consolidated with full CRUD over all three
entities (memories, details, links): every operation takes a list (one item or
many — same call), and detail/link writes are unified into mixed-operation
batch tools (``edit_details`` with op add/update/delete, ``edit_links`` with op
link/unlink).

Since v0.10.0 expanded to **15 tools** with 3 new capabilities:
- ``export_graph_html`` : standalone interactive 3D HTML visualization
- ``restore_memories`` : soft delete trash, version history & rollback
- ``transfer_memories`` : inline upload/download, file migration & database backup

Since v0.11.7 ``transfer_memories`` supports keyset pagination (``limit`` +
``cursor`` + ``scope="memories"|"links"``) on ``op="export"`` so very large
graphs can be migrated between two independent servers (e.g. local stdio and
a remote HTTP/SSE deployment with no shared filesystem) in bounded-size
pages instead of one giant inline payload.

Since v0.11.9 ``scope="trash"`` extends that pagination to soft-deleted
memories: exact ``memory_trash`` snapshots (id, ``deleted_at``, embedded
memory/details/links) can be exported/imported page-by-page too, so a full
migration between two servers can include what is currently in the trash,
not just the live graph.

Runs over stdio by default (ideal for ``uvx brainmemory-mcp``); use ``--web``
to serve over HTTP + SSE. Memory is persisted locally under
``~/.brainmemory-mcp``.
"""

from __future__ import annotations

__version__ = "0.11.9"

from .memory import (
    Memory,
    MemoryDetail,
    MemoryLink,
    MemoryStore,
    default_data_dir,
)

__all__ = [
    "MemoryStore",
    "Memory",
    "MemoryDetail",
    "MemoryLink",
    "default_data_dir",
    "__version__",
]