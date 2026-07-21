# BrainMemory-MCP

---

Project Start Date: 2026-07-21
Last Update Project: 2026-07-21
Project Phase: MVP Implemented — first working server
Project Status: Active — installable Python MCP server with SSE + Cognitive tools

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
- **Framework:** Official `mcp` SDK's `FastMCP`, serving tools over HTTP + SSE.
  Web layer is ASGI (Starlette + Uvicorn), pulled in transitively by `mcp`
  plus pinned as explicit deps.
- **Infrastructure:** Standalone HTTP server with Server-Sent Events (SSE)
  transport. SSE stream at `/sse`, message POST at `/messages/`.
- **Database:** SQLite (stdlib `sqlite3`, WAL mode) at
  `~/.brainmemory-mcp/memory.db`. Location overridable via `--data-dir` or
  `$BRAINMEMORY_HOME`.
- **API structure (Cognitive tools):**
  - `store_memory(content, category, tags, importance)`
  - `recall_memory(memory_id)`
  - `search_memory(query, category, tags, min_importance, limit)`
  - `list_memories(limit, offset)`
  - `update_memory(memory_id, content?, category?, tags?, importance?)`
  - `forget_memory(memory_id)`
  - `summarize_memories()`
  - Resource: `brainmemory://stats` (JSON summary).
- **Packaging:** `pyproject.toml` (PEP 621 / setuptools, `src/` layout).
  Version is single-sourced from `brainmemory_mcp.__version__` via
  `[tool.setuptools.dynamic]`. Installable via `pip install brainmemory-mcp`
  (PyPI, once published) or `pip install .`; exposes console script
  `brainmemory-mcp` and `python3 -m brainmemory_mcp`.
- **Release/PyPI:** `.github/workflows/publish.yml` builds sdist+wheel, runs
  `twine check`, and publishes to PyPI via **Trusted Publishing** (OIDC) on a
  `v*` tag / GitHub Release. Process documented in `docs/RELEASING.md`.
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
    __main__.py                # CLI entry point (argparse: --host/--port/--data-dir)
    server.py                  # FastMCP server, Cognitive tools, SSE run()
    memory.py                  # SQLite-backed MemoryStore + Memory model
.github/workflows/publish.yml   # CI: build + Trusted-Publishing to PyPI
docs/RELEASING.md              # how to cut a release / publish to PyPI
docs/changelog/2026/07/21.md
NOTE.md
```

## Core Flow Project

Describe:
- **Input:** MCP tool invocations arriving from an MCP client over HTTP/SSE
  (cognitive tool calls such as store/recall/search a memory).
- **Processing:** `FastMCP` routes each tool call to its handler in
  `server.py`, which delegates to `MemoryStore` (`memory.py`).
- **Logic:** Cognitive tools implement memory operations — persisting new
  memories, retrieving relevant memories (text/category/tag/importance filters),
  updating, forgetting, and summarizing.
- **Output:** Tool results (JSON dicts) streamed back to the client over SSE.
- **External integration:** MCP clients (LLM agents/IDEs); local SQLite store.
  (No embedding/LLM provider yet — semantic recall remains future work.)

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

## Current State

MVP implemented and verified locally:
- `pip install .` builds and installs the package + console script.
- Server starts over SSE; `/sse` returns the MCP `event: endpoint` handshake.
- MemoryStore CRUD + search + stats verified via smoke test.
- Memory persists to `~/.brainmemory-mcp` (SQLite), overridable via `--data-dir`.

## Pending Issue

List unresolved problems.

Format:

Issue: Tech stack specifics not yet chosen (Python version, MCP SDK/framework, web layer).
Priority: High
Status: Resolved — Python 3.11+, official `mcp` SDK (FastMCP) over Starlette/Uvicorn SSE.

Issue: Persistence/database for memory not defined.
Priority: High
Status: Resolved (initial) — SQLite at `~/.brainmemory-mcp/memory.db`.
Possible Solution: Evaluate a vector store for semantic recall later.

Issue: Concrete cognitive tool set and schemas undefined.
Priority: Medium
Status: Resolved (initial) — 7 tools + 1 resource implemented (see Technical Details).
Possible Solution: Extend with reasoning/summarization backed by an LLM.

Issue: Authentication/security model for the HTTP/SSE endpoint undefined.
Priority: Medium
Status: Open
Possible Solution: Add token-based auth and TLS before any non-local deployment;
default bind remains 127.0.0.1 for now.

Issue: Semantic recall (embeddings) not implemented.
Priority: Low
Status: Open
Possible Solution: Add an embedding provider + vector index alongside SQLite.

Issue: No automated tests / CI yet.
Priority: Medium
Status: Partial — a build/publish CI (`.github/workflows/publish.yml`) now runs
`python -m build` + `twine check` on push/PR. Test suite still missing.
Possible Solution: Add a pytest suite covering MemoryStore and tool handlers,
and run it in CI on every push/PR.

## Changelog Reference

Daily and version history is tracked under [`docs/changelog/`](docs/changelog/).
See `docs/changelog/[yyyy]/[mm]/[dd].md` for per-day entries. Latest:
`docs/changelog/2026/07/21.md`.
