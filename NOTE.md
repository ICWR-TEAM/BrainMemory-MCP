# BrainMemory-MCP

---

Project Start Date: 2026-07-21
Last Update Project: 2026-08-19
Project Phase: MVP + published — graph-backed dual-transport server on PyPI (v0.10.2)
Project Status: Active — installable Python MCP server (stdio default + SSE --web); memory is a SQLite knowledge graph with FTS5/BM25 + graph-augmented search; 15-tool surface with full CRUD over memories/details/links, soft-delete safety net (trash/history/rollback), standalone 3D graph visualization HTML export with agent-controlled output directory, and full graph data transfer/backup.

---

## Project Summary

BrainMemory-MCP is a Model Context Protocol (MCP) server that exposes a set of
**Cognitive tools** — persistent memory, recall, and reasoning helpers — to
AI/LLM clients. The concept is to give an AI agent a durable "brain memory":
the ability to store, organize, retrieve, and reason over information across
sessions through standardized MCP tool calls.

The server is built in **Python** and communicates over **HTTP with
Server-Sent Events (SSE)** as the MCP transport, so remote MCP-capable clients
(e.g. Claude, IDE agents) can connect over the network rather than only via
stdio.

Scope (initial intent):
- Provide MCP tools for cognitive/memory operations (store, recall, search,
  summarize, forget, etc.).
- Serve those tools over an HTTP + SSE endpoint.
- Persist memory in a backing store under `~/.brainmemory-mcp`.

> Status update (2026-07-21): The MVP is implemented. The repository now
> contains an installable Python package (`pip install .`) that runs the MCP
> server over SSE and persists memory in a local SQLite database.
>
> Status update (2026-08-17): Memory is now modelled as a small **knowledge
> graph** (memories = nodes, connections = directed links, details = attached
> facts) for precise multi-hop recall. Still SQLite/stdlib only. Tool vocabulary
> intentionally stays "memory"-oriented (no "entity" wording). Released v0.4.0.
>
> Status update (2026-08-17): Search upgraded to a search-engine model — a
> SQLite **FTS5** index ranked with **BM25** (multi-word / long queries, prefix
> + Porter stemming) plus **graph spreading activation** so connected memories
> surface too. Falls back to a tokenised LIKE scorer without FTS5. Released
> v0.5.0.
>
> Status update (2026-08-18): Added **bulk tool variants** for every tool that
> writes or fetches a single memory/detail/link, to cut agent round-trips and
> token overhead. Released v0.8.0.
>
> Status update (2026-08-18, later): **Consolidated the tool surface 20 -> 12**
> (breaking change, v0.9.0) and completed missing detail CRUD. Detail and link
> writes unified into mixed-operation batch tools (`edit_details`, `edit_links`).
> Released v0.9.0.
>
> Status update (2026-08-19): **Expanded tool surface 12 -> 15** (v0.10.0).
> Status update (2026-08-19): `export_graph_html` now requires a `directory` parameter so agents can choose the workspace/output folder explicitly instead of defaulting to the daemon cwd. Released v0.10.2. Follow-up v0.10.3 enforces `directory` as an absolute path (no `.` / `./` relative workspace ambiguity).
> Added `export_graph_html` (renders full graph into interactive standalone 3D
> HTML file with HUD styling and custom branding `BrainMemory MCP — 3D Knowledge
> Graph` + `By HarshXor - R&D incrustwerush.org`), `restore_memories` (mixed-op
> soft-delete safety net with `memory_trash` retention, `memory_history` version
> snapshots, history inspection, version rollback, and trash purging), and
> `transfer_memories` (full graph JSON export/import & instant online DB backup).
> Released v0.10.0.

## Mandatory Workflow

- First step for every task: always read NOTE.md before making changes.
- Check existing documentation before modifying architecture.
- Preserve existing project conventions.
- Last step for every task: always update NOTE.md and docs/changelog/[yyyy]/[mm]/[dd].md.

## Restrictions

- Do not modify core architecture without documentation.
- Do not remove existing features without confirmation.
- Do not introduce dependency without justification.
- Do not ignore existing project constraints.
- Do not commit credentials/tokens (PyPI, GitHub, etc.) into the repository or
  any file that gets pushed to GitHub. Store them only in local machine
  config that lives outside the git working tree (e.g. `~/.pypirc` for PyPI).

## Architecture Decision Log (ADL)

### ADL 008 — Expansion to 15 tools with HTML Graph Export, Soft-Delete Safety Net, and Data Transfer/Backup (2026-08-19)

**Context:**
Users and agent workflows needed (1) a standalone interactive visualization for
the full knowledge graph identical to the local `/memory-graph` skill, (2) a
safety net against destructive memory deletions or erroneous updates, and (3)
a reliable way to export/import/backup knowledge graph payloads.

**Decision:**
Expanded the server from 12 tools to 15 tools with three new tools:
1. `export_graph_html`: Renders complete knowledge graph into a standalone 3D HTML document (`three.js` + `3d-force-graph` HUD), titled `BrainMemory MCP — 3D Knowledge Graph` with byline `By HarshXor - R&D incrustwerush.org`.
2. `restore_memories`: Mixed-operation tool (`list_trash`, `restore`, `purge_trash`, `history`, `rollback`) backed by `memory_trash` and `memory_history` SQLite tables. `forget_memories` now soft-deletes into trash; `update_memories` automatically creates version snapshots before mutation.
3. `transfer_memories`: Mixed-operation tool (`export`, `import`, `backup`) for JSON transfer and online SQLite DB backup snapshots.

**Consequences:**
- Zero external Python dependencies added (`sqlite3` stdlib + template string).
- Package data updated to bundle `templates/*.html`.
- Preserved zero silent data loss principle across all CRUD operations.
