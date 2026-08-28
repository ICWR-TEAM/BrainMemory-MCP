# BrainMemory-MCP

---

Project Start Date: 2026-07-21
Last Update Project: 2026-08-28
Project Phase: MVP + published — graph-backed dual-transport server on PyPI (v0.11.8)
Project Status: Active — installable Python MCP server (stdio default + SSE --web); optional Bearer authorization for web mode via `--key` / `BRAINMEMORY_KEY`; memory is a SQLite knowledge graph with FTS5/BM25 + graph-augmented search; 15-tool surface with full CRUD over memories/details/links, soft-delete safety net (trash/history/rollback), standalone 3D graph visualization HTML export with one absolute output file path, and transport-safe inline migration download/upload (now with keyset `limit`/`cursor`/`scope` pagination for large graphs) plus optional server-local files over stdio and HTTP/SSE.

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
>
> Status update (2026-08-19): Release v0.11.0 refreshed the README, kept the 15-tool surface, and bumped the package version.
>
> Status update (2026-08-20): Release v0.11.1 adds optional Bearer-key authorization for HTTP/SSE mode through `--key` or `BRAINMEMORY_KEY`. When configured, both `/sse` and `/messages/` require `Authorization: Bearer <key>`; omitted keys preserve backward-compatible unauthenticated web mode.
> Status update (2026-08-28): Release v0.11.2 makes graph HTML export use a single absolute `output_path`, and makes migration export/import file-based via absolute `output_path` / `input_path`. Relative paths and explicit `.` / `..` segments are rejected consistently; tools remain available through both stdio and HTTP/SSE.
>
> Status update (2026-08-28): Release v0.11.3 fixes cross-machine migration: export returns a downloadable inline `data` object and import accepts that object as an upload. Optional absolute paths remain supported for server-local workflows, so HTTP clients no longer need a shared filesystem with the server.
> Status update (2026-08-28): Release v0.11.7 adds keyset pagination to `transfer_memories(op="export")` — `scope` (`all`/`memories`/`links`), `limit`, `cursor` — plus `has_more`/`next_cursor`, so a very large memory graph can be migrated between two independent servers (e.g. local stdio <-> remote HTTP/SSE, no shared filesystem) in bounded-size pages instead of one giant inline payload. New `(created_at, id)` indexes keep each page O(limit). `import_data` needed no changes — it already tolerates partial payloads and skips links with missing endpoints, which is exactly what makes the "page all memories, then page all links" migration flow safe. `scope="all"` without `limit` is unchanged (full one-shot export/import, same as pre-0.11.7).
> Status update (2026-08-28): Release v0.11.8 fixes a real bug found while live-testing a local(stdio)->online(HTTP) migration with real production data: the v0.11.7 `next_cursor` embedded a raw `\x1f` control byte, which round-tripped unreliably through hand/tool-call relaying. Cursor is now base64url-encoded plain ASCII text. Also confirmed empirically during that test: a 100-row page can still exceed a calling agent's tool-result size limit when memories contain large content (e.g. full book-text sections) — callers migrating such graphs should pick a smaller `limit` (start around 15-25) rather than assuming row-count alone bounds payload size.

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

### ADL 009 — Keyset-paginated `transfer_memories` export for large-graph migration (2026-08-28)

**Context:**
A user asked how to migrate a *large* memory graph between two independent
`brainmemory-mcp` server processes with a specific topology: a **local stdio**
instance and a separate **online HTTP/SSE** instance, each with its own SQLite
database and no shared filesystem. The only bridge between the two is the
calling agent's context (export result -> import argument). The pre-0.11.7
`transfer_memories(op="export")` always dumped the entire filtered graph as
one JSON blob, which does not scale: for a sufficiently large graph it can
exceed the agent's context/tool-result budget well before hitting any MCP
protocol limit.

**Decision:**
Added optional keyset pagination to `op="export"` only (import already
tolerated partial payloads, so it needed no changes):
- New parameters `scope` (`"all"` default / `"memories"` / `"links"`),
  `limit`, `cursor`.
- Ordering/cursor is a stable `(created_at, id)` keyset (not `OFFSET`), backed
  by two new indexes (`idx_memories_created_id`, `idx_links_created_id`), so
  each page costs O(limit) regardless of total graph size — important for
  "brutal" (very large) graphs, not just the small ones tested in CI.
- `limit`/`cursor` require `scope="memories"` or `scope="links"` — a single
  cursor cannot page two unrelated tables at once. `scope="all"` remains the
  original unpaginated one-shot full-graph export/import, unchanged.
- Response gained top-level `has_more`/`next_cursor` (mirrored in
  `data.pagination`) so an agent can loop: export a memories page -> import it
  -> repeat until exhausted -> then repeat the same loop with
  `scope="links"`. Because `import_data` already silently skips links whose
  endpoints don't exist yet (`links_skipped`), doing memories-first-then-links
  is safe by construction, not something the caller has to get exactly right.

**Consequences:**
- No breaking changes: `transfer_memories(op="export")` with no `limit` (the
  common case for small/medium graphs) behaves exactly as before, same
  payload shape plus two new always-present, ignorable fields (`scope`,
  `pagination`).
- Zero new dependencies (stdlib `sqlite3` only, per NOTE.md restrictions).
- Large-graph migration cost moved from "one huge context-busting call" to
  "N bounded calls", trading round-trips for reliability — acceptable since
  `transfer_memories` is an infrequent, deliberate operation, not a hot path.

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
3. `transfer_memories`: Mixed-operation tool for inline JSON migration download/upload, optional absolute-path server-local export/import, plus online SQLite DB backup snapshots. Export always returns `data`; import accepts `data` or `input_path` (but not both). File paths reject relative or dot-segment paths.

**Consequences:**
- Cross-machine stdio-to-HTTP migration works through MCP payloads without shared filesystem access.
- Large exports remain subject to MCP client/server message-size limits; server-local paths remain available where appropriate.
- Zero external Python dependencies added (`sqlite3` stdlib + template string).
- Package data updated to bundle `templates/*.html`.
- Preserved zero silent data loss principle across all CRUD operations.