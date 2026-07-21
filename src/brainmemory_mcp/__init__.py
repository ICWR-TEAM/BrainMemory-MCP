"""BrainMemory-MCP — Cognitive memory tools served over stdio or HTTP + SSE.

A Model Context Protocol (MCP) server that gives AI/LLM agents a durable
"brain memory": the ability to store, recall, search, update, summarize, and
forget information across sessions through standardized MCP tool calls.

Runs over stdio by default (ideal for ``uvx brainmemory-mcp``); use ``--web``
to serve over HTTP + SSE. Memory is persisted locally under
``~/.brainmemory-mcp``.
"""

from __future__ import annotations

__version__ = "0.3.0"

from .memory import MemoryStore, Memory, default_data_dir

__all__ = ["MemoryStore", "Memory", "default_data_dir", "__version__"]
