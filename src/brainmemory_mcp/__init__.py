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

Runs over stdio by default (ideal for ``uvx brainmemory-mcp``); use ``--web``
to serve over HTTP + SSE. Memory is persisted locally under
``~/.brainmemory-mcp``.
"""

from __future__ import annotations

__version__ = "0.5.0"

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
