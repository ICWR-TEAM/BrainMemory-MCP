# BrainMemory-MCP

---

Project Start Date: 2026-07-21
Last Update Project: 2026-08-18
Project Phase: MVP + published — graph-backed dual-transport server on PyPI (v0.8.0)
Project Status: Active — installable Python MCP server (stdio default + SSE --web); memory is a SQLite knowledge graph with FTS5/BM25 + graph-augmented search, with bulk tool variants for every single-item write/read operation

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
> token overhead: `store_memories`, `recall_memories`, `update_memories`,
> `forget_memories`, `add_details`, `link_memories_bulk`,
> `unlink_memories_bulk`. Each accepts a list of per-item dicts and reports a
> per-item `status` so one bad item never aborts the whole batch. Released
> v0.8.0.

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

## AI Operating Context

Define AI responsibility, expected behavior, and operational boundaries.

- AI acts as development assistant for the BrainMemory-MCP server.
- AI must prioritize consistency and correctness over speed.
- AI must document important decisions in the Architecture Decision Log.
- AI must respect the MCP specification and SSE transport contract when adding
  or changing tools.
- AI must keep memory/persistence behavior deterministic and safe (no silent
  data loss).

## Technical Development Details

Describe:
- **Programming language:** Python 3.11+ (verified on 3.13).
- **Framework:** Official `mcp` SDK's `FastMCP`, serving tools over two
  transports: **stdio** (default; ideal for `uvx brainmemory-mcp`) and
  **HTTP + SSE** (enabled with `--web`). Web layer is ASGI (Starlette +
  Uvicorn), pulled in transitively by `mcp` plus pinned as explicit deps.
- **Infrastructure:** Runs as a stdio subprocess by default; with `--web`
  runs as a standalone HTTP server with Server-Sent Events (SSE) transport
  (SSE stream at `/sse`, message POST at `/messages/`).
- **Database:** SQLite (stdlib `sqlite3`, WAL mode) at
  `~/.brainmemory-mcp/memory.db`. Location overridable via `--data-dir` or
  `$BRAINMEMORY_HOME`. Since v0.4.0 the schema is a **knowledge graph**:
  - `memories` — nodes (id, content, category, tags, importance, timestamps).
  - `memory_details` — extra facts attached to a memory (`ON DELETE CASCADE`).
  - `memory_links` — directed connection `source_id -> target_id` with
    `relation` (default `related_to`) + `weight`; `UNIQUE(source,target,relation)`,
    both endpoints `ON DELETE CASCADE`.
  - `memories_fts` — SQLite **FTS5** full-text index over
    content/tags/category/details, kept in sync by triggers, ranked with BM25
    (`tokenize='porter unicode61'`). Present only when the SQLite build has
    FTS5; otherwise search falls back to a tokenised LIKE scorer.
  Opening a DB that lacks the newest schema (graph tables or the FTS index)
  auto-backs it up to `~/.brainmemory-mcp/backups/memory-<UTC>.db` (SQLite
  online backup API) before the new objects are added — non-destructive
  migration.
- **API structure (Cognitive tools):**
  - Core memory:
    - `store_memory(content, category, tags, importance)`
    - `store_memories(items)` — bulk `store_memory`; `items` is a list of
      `{content, category?, tags?, importance?}`; per-item `status`.
    - `recall_memory(memory_id)` — returns the memory + its details + connections
    - `recall_memories(memory_ids, include_connections=False)` — bulk
      `recall_memory`; `include_connections` opts into the richer per-item
      payload (details + connections), off by default for a leaner response.
    - `search_memory(query, category, tags, min_importance, limit, expand, mode)`
      — search-engine ranking (FTS5/BM25, multi-word queries) over
      content/tags/category/details, blended with importance + recency, and
      graph-augmented via spreading activation (`expand`). Results carry
      `relevance`, `match_type`, `matched_terms`, `distance`.
    - `list_memories(limit, offset)`
    - `update_memory(memory_id, content?, category?, tags?, importance?)`
    - `update_memories(updates)` — bulk `update_memory`; `updates` is a list of
      `{memory_id, content?, category?, tags?, importance?}`.
    - `forget_memory(memory_id)` — cascades to details + links
    - `forget_memories(memory_ids)` — bulk `forget_memory`.
    - `summarize_memories()` — totals, categories, top tags, connection stats,
      most-connected memories
  - Graph memory:
    - `add_detail(memory_id, content)`
    - `add_details(items)` — bulk `add_detail`; items may target different
      memories, doubling as a multi-memory enrichment call.
    - `link_memories(from_id, to_id, relation, weight)`
    - `link_memories_bulk(links)` — bulk `link_memories`; `links` is a list of
      `{from_id, to_id, relation?, weight?}`.
    - `unlink_memories(from_id, to_id, relation?)`
    - `unlink_memories_bulk(links)` — bulk `unlink_memories`.
    - `recall_related(memory_id, depth, relation?, limit)` — multi-hop recall
    - `connect_memories(from_id, to_id, max_depth)` — shortest path
    - `memory_map(memory_id?, depth, limit)` — nodes + links map
  - Resources: `brainmemory://stats` (JSON summary), `brainmemory://graph`
    (JSON nodes + links map).
  - Bulk-tool convention: every bulk tool takes a `list[dict]` of per-item
    payloads, never raises/aborts on one bad item, and returns
    `{status: "ok", count, <verb-count>, results: [...]}` where each `results`
    entry carries its own `status` (the tool's normal per-item status value, or
    `"error"` with an `error` message for a malformed item). This keeps
    behaviour predictable for partial-failure batches.
- **Packaging:** `pyproject.toml` (PEP 621 / setuptools, `src/` layout).
  Version is single-sourced from `brainmemory_mcp.__version__` via
  `[tool.setuptools.dynamic]`. Installable via `pip install brainmemory-mcp`
  (PyPI) or `pip install .`; exposes console script `brainmemory-mcp` and
  `python3 -m brainmemory_mcp`.
- **Release/PyPI:** `.github/workflows/publish.yml` builds sdist+wheel, runs
  `twine check`, and publishes to PyPI via **Trusted Publishing** (OIDC) on a
  `v*` tag / GitHub Release. Manual `twine upload` with an API token is the
  fallback. Process documented in `docs/RELEASING.md`.
- **Deployment model:** Standalone HTTP MCP server (containerizable).
- **Coding convention:** PEP 8 + type hints; `ruff`/`black` configured
  (line-length 100).
- **Security requirement:** Still TBD — no auth/TLS yet; bind defaults to
  `127.0.0.1`. Add token auth + TLS before non-local deployment.

## Project Layout

```
pyproject.toml                 # packaging / deps / console script
README.md                      # usage & install docs
.gitignore
src/brainmemory_mcp/
    __init__.py                # package exports + version
    __main__.py                # CLI entry point (argparse: --web/--host/--port/--data-dir)
    server.py                  # FastMCP server, Cognitive + graph + bulk tools, run(web=...)
    memory.py                  # SQLite graph store: Memory/MemoryDetail/MemoryLink + MemoryStore
.github/workflows/publish.yml   # CI: build + Trusted-Publishing to PyPI
docs/RELEASING.md              # how to cut a release / publish to PyPI
docs/changelog/2026/07/21.md
docs/changelog/2026/07/29.md
docs/changelog/2026/08/17.md
docs/changelog/2026/08/18.md
NOTE.md
```

## Core Flow Project

Describe:
- **Input:** MCP tool invocations arriving from an MCP client over stdio
  (default) or HTTP/SSE (`--web`) — cognitive tool calls such as
  store/recall/search/link/traverse a memory, single-item or bulk.
- **Processing:** `FastMCP` routes each tool call to its handler in
  `server.py`, which delegates to `MemoryStore` (`memory.py`). Bulk handlers
  loop over their input list, calling the same `MemoryStore` methods as their
  singular counterparts per item, and collect a per-item result instead of
  raising on the first failure.
- **Logic:** Cognitive tools implement memory operations over a knowledge
  graph — persisting new memories (nodes), attaching details, connecting
  memories (directed weighted links), retrieving relevant memories
  (text/category/tag/importance filters), multi-hop recall (`recall_related`),
  shortest-path connection (`connect_memories`), updating, forgetting
  (cascade), and summarizing (incl. degree centrality) — each available singly
  or in bulk.
- **Output:** Tool results (JSON dicts) streamed back to the client over SSE.
- **External integration:** MCP clients (LLM agents/IDEs); local SQLite store.
  (No embedding/LLM provider yet — semantic recall remains future work; the
  graph gives precise relational recall in the meantime.)

## Architecture Decision Log

Record important technical decisions.

Format:

Date: 2026-07-21
Decision: Build BrainMemory-MCP as a Python MCP server using HTTP + SSE transport.
Reason: Enables remote MCP clients to connect over the network and matches the
"cognitive tools" concept of a shared, always-available brain memory service.
Impact: Requires an ASGI/HTTP layer and SSE endpoint; clients configure a URL
rather than a stdio command.

Date: 2026-07-21
Decision: Use the official `mcp` SDK's `FastMCP` with `transport="sse"`.
Reason: Least-effort, spec-compliant way to expose typed tools over SSE without
hand-rolling the protocol; brings Starlette/Uvicorn as the ASGI layer.
Impact: Runtime deps = `mcp`, `starlette`, `uvicorn`. Endpoints are `/sse`
(stream) and `/messages/` (POST).

Date: 2026-07-21
Decision: Persist memory in local SQLite at `~/.brainmemory-mcp/memory.db`.
Reason: Zero external services, deterministic, safe, stdlib-only; matches the
NOTE.md recommendation to "start with SQLite". Directory is configurable.
Impact: No semantic/vector recall yet; search is text/tag/category/importance
based via SQL. Vector store remains a future option.

Date: 2026-07-21
Decision: Adopt `src/` layout with `pyproject.toml` (setuptools) and a console
script `brainmemory-mcp`.
Reason: Makes the tool installable via `python3 -m pip install .` and runnable
as a command or `python3 -m brainmemory_mcp`.
Impact: Standard, clean packaging; editable installs supported for dev.

Date: 2026-07-21
Decision: Support two transports — stdio (default) and HTTP+SSE via `--web`.
Reason: stdio is the least-friction path for local MCP clients that launch
the server as a subprocess (matches the requested `uvx brainmemory-mcp`
config: no port/bind, auto lifecycle). SSE stays available for remote use.
Impact: `run()` gained a `web` flag; `__main__` gained `--web`
(env `BRAINMEMORY_WEB`). In stdio mode logs go to stderr (stdout is the
protocol channel); in web mode endpoints are logged to stdout as before.

Date: 2026-07-21
Decision: Publish v0.2.0 to PyPI (v0.1.0 was SSE-only and broke `uvx`).
Reason: The first PyPI release (0.1.0) defaulted to SSE transport, so
`uvx brainmemory-mcp` in a stdio MCP client started an HTTP server and never
spoke the stdio protocol -> the server failed to load. PyPI releases are
immutable, so the stdio-default fix ships as 0.2.0.
Impact: `uvx brainmemory-mcp` now works out of the box for stdio clients.
Version bumped in `brainmemory_mcp.__version__`. Published via `twine` (API
token) after `uv build` + `twine check`.

Date: 2026-07-29
Decision: Pin the `mcp` dependency to `>=1.2.0,<2` and hotfix-release v0.3.1.
Reason: `mcp` 2.0.0 removed the `mcp.server.fastmcp` module that `server.py`
imports (`from mcp.server.fastmcp import FastMCP`). Because the dependency was
declared as `mcp>=1.2.0` (no upper bound), `uvx brainmemory-mcp` began pulling
`mcp==2.0.0` the moment it was published, breaking every fresh install with
`ModuleNotFoundError: No module named 'mcp.server.fastmcp'` — even though the
package worked the day before.
Impact: New installs resolve `mcp` in the 1.x line again and import correctly.
PyPI releases are immutable, so the fix ships as 0.3.1 (0.3.0 was already
published). No API/tool changes. A future task may migrate to the mcp 2.0 API
to lift the `<2` cap.

Date: 2026-08-17
Decision: Re-model memory as a SQLite knowledge graph (nodes/links/details)
while keeping "memory"-oriented tool names; release v0.4.0.
Reason: A flat note list can only recall by literal word match. Modelling
memories as graph nodes with directed connections enables precise, multi-hop
recall (`recall_related`) and relationship explanation (`connect_memories`).
The user explicitly required keeping the "memory" vocabulary (no "entity"
naming) and staying on SQLite with no new dependencies.
Impact: Two new tables (`memory_details`, `memory_links`) added additively;
the `memories` table is unchanged so existing data is preserved. Opening a
pre-graph DB auto-backs it up to `backups/` before adding graph tables. Six new
tools (`add_detail`, `link_memories`, `unlink_memories`, `recall_related`,
`connect_memories`, `memory_map`) plus a `brainmemory://graph` resource; the 7
original tools keep their names (richer output). Graph algorithms use plain
SQL + Python BFS (small data), so still zero external deps. Verified locally:
131 existing memories preserved, backup written.

Date: 2026-08-17
Decision: Upgrade search to an FTS5/BM25 + graph-spreading-activation engine;
release v0.5.0.
Reason: The old `LIKE '%query%'` matched the whole phrase as one substring, so
multi-word / long queries (e.g. "Burp Firefox sync") returned nothing and agents
had to degrade to single keywords. A real search needs tokenisation + relevance
ranking, and the knowledge graph should let related memories surface too.
Impact: Added a synced SQLite FTS5 index (`memories_fts`) + triggers; `search()`
now tokenises the query, ranks with BM25 (blended with importance + recency),
and — when `expand=True` — spreads through `memory_links` to include connected
memories with a decayed score. New `search_scored()` returns rich results
(`relevance`, `match_type`, `matched_terms`, `distance`); `search_memory` gained
`expand` + `mode` params. Transparent fallback to a tokenised-LIKE scorer where
FTS5 is absent. Opening a pre-FTS DB auto-backs up then backfills the index.
Still zero external deps (FTS5 is stdlib sqlite3). Verified: 131 memories
backfilled, backup written, multi-word EN/ID queries rank correctly, and a
graph-only memory surfaces solely via `expand`.

Date: 2026-08-18
Decision: Add bulk tool variants for every tool that writes or fetches a single
memory/detail/link; release v0.8.0.
Reason: Discussed token-efficiency options for agents using this server — one
of the clearest wins was letting an agent do many single-item writes/reads in
one MCP round-trip instead of N, which cuts both tool-call overhead and
repeated response boilerplate. User asked to implement bulk operations across
every applicable tool first (before other token-saving ideas like brief/field
projection or `graphify`).
Impact: 7 new tools added — `store_memories`, `recall_memories`,
`update_memories`, `forget_memories`, `add_details`, `link_memories_bulk`,
`unlink_memories_bulk` — each accepting a `list[dict]` of per-item payloads and
delegating to the same `MemoryStore` methods as the existing singular tools (no
`MemoryStore`/schema changes). Each bulk tool never aborts on one bad item:
every item gets its own `status` ("ok"-family value, `"not_found"`, or
`"error"` with a message), plus an overall count, so partial failures are
visible without losing the rest of the batch. `search_memory`,
`list_memories`, `recall_related`, `connect_memories`, and `memory_map` were
left singular — they are already "many results from one call" or operate on a
specific relationship/path, so a bulk wrapper would not add value.
`create_server()` now registers 20 tools + 2 resources (was 13 + 2). Verified
via a stdio-free smoke test: all 7 bulk tools called directly against
`FastMCP.call_tool`, including mixed success/`not_found`/`error` items in the
same batch (e.g. self-link rejected, missing id reported, empty content
rejected) without aborting the batch.

## Current State

MVP + graph model + search engine + bulk tools implemented and verified locally:
- `pip install .` builds and installs the package + console script.
- Server starts over stdio (default) and SSE (`--web`); `create_server()`
  registers 20 tools (13 singular/query + 7 bulk) + 2 resources.
- MemoryStore CRUD + FTS5/BM25 search (`search_scored`) with graph spreading
  activation + graph ops (link/detail/recall_related/connect_memories/
  memory_map) + stats verified via smoke test.
- Bulk tools (`store_memories`, `recall_memories`, `update_memories`,
  `forget_memories`, `add_details`, `link_memories_bulk`,
  `unlink_memories_bulk`) verified via smoke test: each processes a mixed
  batch (valid item, missing/not-found id, malformed item) and reports correct
  per-item status without aborting the batch.
- Migration verified against the real DB: 131 memories preserved across two
  upgrades (graph tables, then FTS index backfilled = 131 rows), each with an
  auto-backup under `~/.brainmemory-mcp/backups/`.
- Memory persists to `~/.brainmemory-mcp` (SQLite), overridable via `--data-dir`.

## Pending Issue

List unresolved problems.

Format:

Issue: Tech stack specifics not yet chosen (Python version, MCP SDK/framework, web layer).
Priority: High
Status: Resolved — Python 3.11+, official `mcp` SDK (FastMCP) over Starlette/Uvicorn SSE.

Issue: Persistence/database for memory not defined.
Priority: High
Status: Resolved — SQLite at `~/.brainmemory-mcp/memory.db`, now modelled as a
knowledge graph (memories/details/links) since v0.4.0.
Possible Solution: Evaluate a vector store for semantic recall later.

Issue: Concrete cognitive tool set and schemas undefined.
Priority: Medium
Status: Resolved — 20 tools + 2 resources implemented (see Technical Details):
7 core memory tools + 6 graph tools + 7 bulk tools.
Possible Solution: Extend with reasoning/summarization backed by an LLM.

Issue: Authentication/security model for the HTTP/SSE endpoint undefined.
Priority: Medium
Status: Open
Possible Solution: Add token-based auth and TLS before any non-local deployment;
default bind remains 127.0.0.1 for now.

Issue: `mcp` dependency had no upper bound, so `mcp` 2.0.0 (which removed
`mcp.server.fastmcp`) broke `uvx brainmemory-mcp` on fresh installs.
Priority: High
Status: Resolved — pinned `mcp>=1.2.0,<2` and released v0.3.1 to PyPI.
Possible Solution: Longer term, migrate to the `mcp` 2.0 API and lift the cap.

Issue: Long / multi-word search queries returned nothing (whole-phrase LIKE).
Priority: High
Status: Resolved (v0.5.0) — FTS5/BM25 tokenised search + graph spreading
activation; multi-word EN/ID queries now rank relevant results in one call.

Issue: Semantic recall (embeddings) not implemented.
Priority: Low
Status: Open (partially mitigated) — the knowledge graph gives precise
relational/multi-hop recall and FTS5/BM25 gives lexical relevance ranking, but
there is still no vector/semantic similarity (synonyms/paraphrase).
Possible Solution: Add an embedding provider + vector index alongside SQLite,
or a `similar_to` link type populated from embeddings.

Issue: Graph connections must be built manually via `link_memories`; existing
memories start unconnected after migration.
Priority: Low
Status: Open
Possible Solution: Add an optional "suggest connections" step from shared
tags/category co-occurrence to bootstrap the graph (discussed conceptually as
a "graphify" tool: score candidates by tag-overlap + category match + BM25
text similarity, cap links per memory, and default to a `dry_run` preview
before writing). Not yet implemented.

Issue: Single-item tools required N round-trips for N items (store/recall/
update/forget/link/unlink/add_detail), adding token + latency overhead for
agents doing batch work.
Priority: Medium
Status: Resolved (v0.8.0) — added `store_memories`, `recall_memories`,
`update_memories`, `forget_memories`, `add_details`, `link_memories_bulk`,
`unlink_memories_bulk`; each takes a list of per-item payloads and reports
per-item status so partial failures don't abort the batch.
Possible Solution (future): Consider `brief`/`fields` projection params on
`search_memory`/`list_memories`/`recall_memories` to also shrink per-item
*output* size (separate from batching), if still needed after using the bulk
tools.

Issue: No automated tests / CI yet.
Priority: Medium
Status: Partial — a build/publish CI (`.github/workflows/publish.yml`) now runs
`python -m build` + `twine check` on push/PR. Test suite still missing.
Possible Solution: Add a pytest suite covering MemoryStore (incl. graph ops +
migration/backup) and tool handlers (incl. the new bulk tools' partial-failure
behaviour), and run it in CI on every push/PR.

## Changelog Reference

Daily and version history is tracked under [`docs/changelog/`](docs/changelog/).
See `docs/changelog/[yyyy]/[mm]/[dd].md` for per-day entries. Latest:
`docs/changelog/2026/08/18.md`.
