# BrainMemory-MCP

---

Project Start Date: 2026-07-21
Last Update Project: 2026-09-24
Project Phase: MVP + published — graph-backed dual-transport server on PyPI (v0.13.1)
Project Status: Active — installable Python MCP server (stdio default + SSE --web); optional Bearer authorization for web mode via `--key` / `BRAINMEMORY_KEY`; memory is a SQLite knowledge graph with FTS5/BM25 + graph-augmented search; 15-tool surface with full CRUD over memories/details/links, soft-delete safety net (trash/history/rollback), standalone 3D graph visualization HTML export with one absolute output file path, and transport-safe inline migration download/upload with keyset `limit`/`cursor`/`scope` pagination for large active graphs and exact trash snapshots, plus optional server-local files over stdio and HTTP/SSE.

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
> Status update (2026-08-28): Release v0.11.9 extends `transfer_memories` pagination to soft-deleted memories: new `scope="trash"` on `op="export"` (paired with `store.export_trash`/`store.import_trash`) exports/imports exact `memory_trash` snapshots (id, `deleted_at`, embedded memory/details/links) with the same keyset `limit`/`cursor` mechanics as `scope="memories"`/`scope="links"`, keyed on `(deleted_at, id)` with a new `idx_trash_deleted_id` index. `op="import"` auto-routes to trash import when the payload carries a `"trash"` key. Closes the gap where a full local<->online migration previously could not carry over what was currently in the trash.
> Status update (2026-09-24): Release v0.12.0 adds an optional `content_chars` parameter to `search_memory` and `list_memories` that truncates each returned memory's `content` to a preview of that many characters (positive int). Truncated memories gain `content_truncated: true` and `content_length` (original char count); full text remains available via `recall_memories`. Default (omitted / non-positive) returns full content unchanged — no breaking change. This stops listings/searches over very large memories (e.g. book-length content) from overrunning an agent's tool-result size budget. Purely presentation-layer (serialization) truncation via a new `server._apply_content_limit` helper; storage, ranking, and search behaviour are untouched. Zero new dependencies. 15-tool surface unchanged. See ADL 011.
> Status update (2026-09-24): Release v0.13.0 extends the optional `content_chars` preview (from v0.12.0) to every remaining read/browse tool that returns memory bodies: `recall_memories` (memory + included details), `recall_related` (root + related), `connect_memories` (path), `memory_map` (nodes), and — per-item — the `list_trash` / `history` ops of `restore_memories`. Same semantics and same `server._apply_content_limit` helper; truncated items gain `content_truncated`/`content_length`. Write tools (`store_memories`, `update_memories`) and `transfer_memories`/`export_graph_html` are intentionally NOT truncated so request echoes, migrations, and backups stay full-fidelity. No breaking changes (all params optional, default = full content). Zero new dependencies. 15-tool surface unchanged. See ADL 012.
> Status update (2026-09-24): Release v0.13.1 turns the `content_chars` preview into a movable window by adding an optional `content_offset` (0-based start char, default 0) to the same tools (`search_memory`, `list_memories`, `recall_memories` [memory + details], `recall_related`, `connect_memories`, `memory_map`, and per-item on `restore_memories` `list_trash`/`history`). `content_offset` + `content_chars` return `content[offset:offset+chars]` so callers can page through long content (e.g. offset=200, chars=200 → chars 200..399); `content_chars` alone still starts at 0. When offset>0 the returned item also carries `content_offset`. `_apply_content_limit` gained the offset arg (negative→0, offset beyond end→empty string). No breaking changes (all optional; offset defaults to 0 = prior behaviour). Zero new dependencies. 15-tool surface unchanged. See ADL 013.

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

### ADL 013 — `content_offset` movable-window preview (2026-09-24)

**Context:**
ADL 011/012 added `content_chars`, but it always previews from the *start* of a
memory's content. A user wanted to read an arbitrary slice — "start at char N,
give me M chars" — to page through very long memories (e.g. book-length
sections) without pulling the whole body, while keeping the current
"from the beginning" behaviour as the default.

**Decision:**
Extended the same helper `server._apply_content_limit(memory, max_chars,
offset=None)` with an `offset` argument, and threaded a new optional
`content_offset` parameter through every tool that already accepts
`content_chars` (`search_memory`, `list_memories`, `recall_memories` — memory
and included details, `recall_related`, `connect_memories`, `memory_map`, and
per-item on `restore_memories` `list_trash`/`history`).
- Semantics: returns `content[offset : offset+max_chars]`; with `max_chars`
  omitted the slice runs to the end from `offset`. `offset` defaults to 0
  (unchanged behaviour). Negative offset is clamped to 0; an offset past the
  end yields an empty string (still flagged).
- Flags: a windowed result carries `content_truncated: true`,
  `content_length` (original length), and — only when `offset` > 0 —
  `content_offset` (the start used), so an offset-0 preview is byte-identical
  to the pre-0.13.1 output shape.

**Consequences:**
- No breaking changes: `content_offset` is optional and defaults to 0; existing
  `content_chars`-only calls behave exactly as in v0.13.0.
- Enables client-side paging over large content in bounded slices without a new
  tool or storage change; ranking/traversal still run on full content, only the
  serialized slice is windowed.
- Zero new dependencies. 15-tool surface unchanged (parameter addition only).

### ADL 012 — Extend `content_chars` preview to all read/browse tools (2026-09-24)

**Context:**
ADL 011 (v0.12.0) added the optional `content_chars` content-preview parameter
only to `search_memory` and `list_memories`. But other tools also return full
memory bodies — `recall_memories`, `recall_related`, `connect_memories`,
`memory_map`, and the `list_trash` / `history` browse ops of
`restore_memories` — so an agent triaging memories through those paths still had
no way to cap per-item content size and could blow its token/tool-result budget.

**Decision:**
Reuse the exact ADL 011 mechanism (`server._apply_content_limit`) across every
read/browse surface that emits memory bodies:
- `recall_memories`: new `content_chars` param; applied to each memory **and**
  to each included detail (details carry `content` too).
- `recall_related`: applied to `root` + every entry in `related`.
- `connect_memories`: applied to every memory on `path`.
- `memory_map`: applied to every entry in `nodes`.
- `restore_memories`: `content_chars` accepted **per-item** on `list_trash`
  (truncates each trashed row's embedded `memory`) and `history` (truncates
  each version's embedded `memory`) — kept per-item because it is a
  mixed-operation batch tool, not a single-purpose call.

Deliberately excluded (must stay full-fidelity):
- Write tools `store_memories` / `update_memories` — their output echoes the
  caller's own input; truncating it would be surprising and lossy.
- `transfer_memories` and `export_graph_html` — data migration / backup /
  visualization export where any truncation would silently corrupt the
  exported graph.

**Consequences:**
- No breaking changes: all new params are optional and default to full content;
  the extra `content_truncated` / `content_length` keys appear only on items
  actually truncated.
- One shared helper keeps behaviour identical everywhere (same flags, same
  non-mutating copy, same "truncate after ranking/traversal" ordering).
- Zero new dependencies. 15-tool surface unchanged (parameter additions only).

### ADL 011 — Optional `content_chars` content preview for `search_memory` / `list_memories` (2026-09-24)

**Context:**
`search_memory` and `list_memories` always returned each memory's **full**
`content`. `limit`/`offset` only bound the number of rows, not per-row payload
size. As already observed empirically during the v0.11.8 migration test, a
small row count can still blow past a calling agent's tool-result size budget
when individual memories hold very large content (e.g. full book-text
sections). Agents that just want to browse/triage had no way to ask for a
short preview without pulling every full body.

**Decision:**
Added an optional `content_chars: int | None = None` parameter to both
`search_memory` and `list_memories`, implemented as a single presentation-layer
helper `server._apply_content_limit(memory_dict, max_chars)`:
- When `content_chars` is a positive int and a memory's `content` is longer, the
  serialized `content` is truncated to that many characters and the memory gains
  two flags — `content_truncated: true` and `content_length` (the original,
  untruncated character count) — so the caller knows it is a preview and can
  fetch the full text with `recall_memories`.
- `None` (default) or a non-positive / non-int value returns full content
  unchanged (backward compatible).
- Truncation is non-mutating (operates on the dict copy returned to the client)
  and happens *after* ranking/scoring, so search relevance, ordering, importance
  and recency are computed on full content — only the returned text is trimmed.

**Consequences:**
- No breaking changes: omitting `content_chars` preserves the exact prior
  output shape; the two extra keys appear only on memories that were actually
  truncated.
- Applies to the read/list surface only. `recall_memories` intentionally stays
  full-fidelity (it is the "give me everything" path). `content_chars` was not
  added there to keep a clear "preview vs. full" split.
- Zero new dependencies (stdlib only). Storage, FTS5/BM25 index, and graph
  expansion are untouched. 15-tool surface unchanged (parameter addition only).

### ADL 010 — `scope="trash"` pagination for `transfer_memories` (2026-08-28)

**Context:**
ADL 009's `scope="memories"`/`scope="links"` pagination only covers the live
graph. Soft-deleted memories (`memory_trash`, from `forget_memories` /
`restore_memories`) had no migration path at all: `export_data`/`import_data`
never touch the trash table, so a full local<->online migration could not
carry over what was currently in the trash without a manual
restore-export-forget workaround on both ends (which also mutates
`deleted_at`/history in a way that isn't a faithful copy).

**Decision:**
Added a third, independent pagination target mirroring ADL 009's shape:
- `MemoryStore.export_trash(limit, cursor)` / `MemoryStore.import_trash(data, on_conflict)`:
  same keyset-cursor pattern, keyed on `(deleted_at, id)` with a new
  `idx_trash_deleted_id` index, so it scales the same way as memories/links.
- `transfer_memories(op="export", scope="trash", ...)` routes to
  `export_trash` instead of `export_data` (before scope validation, so it
  does not need to satisfy `export_data`'s `all`/`memories`/`links` check).
  `category`/`tags` are rejected for `scope="trash"` (trash rows carry no
  filterable category/tags at the transport level — they are embedded inside
  each row's frozen `payload`).
- `transfer_memories(op="import", ...)` auto-detects a trash payload (its
  `"trash"` list key) and routes to `import_trash` — no separate import op,
  keeping the tool surface unchanged.
- Trash payload preserves the exact snapshot shape `forget_memories` writes:
  `{"id", "deleted_at", "payload": {"memory", "details", "links"}}`, id
  round-trips 1:1 so a later `restore_memories(op="restore")` on the
  destination behaves identically to what it would on the source.

**Consequences:**
- No breaking changes: `scope` still defaults to `"all"` (live graph only,
  same as before this ADL and ADL 009).
- Completes the "migrate everything" story for the local<->online large-graph
  scenario ADL 009 was written for — memories, links, and trash all page the
  same way.
- Zero new dependencies.

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