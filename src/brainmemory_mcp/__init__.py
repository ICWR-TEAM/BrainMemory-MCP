"""BrainMemory-MCP — Cognitive memory tools served over stdio or HTTP + SSE.

A Model Context Protocol (MCP) server that gives AI/LLM agents a durable
"brain memory": the ability to store, recall, search, connect, update,
summarize, and forget information across sessions through standardized MCP tool
calls.

Since v0.4.0 memory is modelled as a small **knowledge graph** — memories are
nodes, connections between them are directed links, and extra facts attach as
details — enabling precise, multi-hop recall while keeping a "memory"-oriented
tool vocabulary.

Runs over stdio by default (ideal for ``uvx brainmemory-mcp``); use ``--web``
to serve over HTTP + SSE. Memory is persisted locally under
``~/.brainmemory-mcp``.
"""

from __future__ import annotations

__version__ = "0.4.0"

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
