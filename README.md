# BrainMemory-MCP

A **Model Context Protocol (MCP)** server that gives AI/LLM agents a durable
**brain memory** — the ability to store, recall, search, connect, summarize,
and forget information across sessions through standardized MCP tool calls.

Since **v0.4.0** memory is modelled internally as a small **knowledge graph**:

- **memories** are the graph **nodes** (content, category, tags, importance),
- **connections** are directed **links** between memories (e.g. `related_to`,
  `caused_by`, `part_of`),
- **details** are extra facts attached to a single memory.

This makes recall *precise* — instead of only matching words, the server can
walk the connections you build (multi-hop recall) and explain how two memories
relate (shortest path). The tool vocabulary stays "memory"-oriented (no
"entity" wording), and it is still just **SQLite** under the hood — zero extra
dependencies.

The server runs in two modes:

- **stdio** (default) — the server is launched as a subprocess by an MCP
  client (e.g. via `uvx brainmemory-mcp`).
- **web** — MCP over **HTTP + Server-Sent Events (SSE)** with `--web`, so
  remote MCP-capable clients (Claude, IDE agents, etc.) can connect over the
  network.

Memory is persisted locally under **`~/.brainmemory-mcp`** (a SQLite database).

## Cognitive Tools (15)

Since **v0.9.0** the tool surface is consolidated: **every operation takes a
list**, so acting on one memory or fifty is the same call (a single item is
just a list of one). Detail and link writes are unified into one
mixed-operation batch tool per entity. The result is full **CRUD over all
three entities** with 15 tools.

| Tool | Description |
|------|-------------|
| `store_memories` | Persist one or more memories (content, category, tags, importance). |
| `recall_memories` | Fetch one or more memories by id; opt-in `include_details` / `include_links` for the richer payload. |
| `search_memory` | Search-engine style: rank memories by relevance (BM25) for multi-word/long queries; also searches details; optional graph `expand`. |
| `list_memories` | List stored memories (most important & recent first). |
| `update_memories` | Modify one or more memories (only supplied fields change). |
| `forget_memories` | Delete one or more memories (now soft-deletes into trash for safety). |
| `edit_details` | Add / update / delete extra facts attached to memories — mixed ops in one batch. |
| `edit_links` | Create (`link`) / remove (`unlink`) directed connections — mixed ops in one batch. |
| `recall_related` | Multi-hop recall: memories connected to one memory, up to *depth* hops. |
| `connect_memories` | Shortest connection (path) between two memories. |
| `memory_map` | Return a map (nodes + links) of the memory graph. |
| `summarize_memories` | Summary statistics: totals, categories, top tags, connection stats, most-connected memories. |
| `export_graph_html` | Export the complete graph to a standalone interactive 3D HTML file at an absolute `output_path`. |
| `restore_memories` | Soft-delete trash, history, rollback, and trash purge management. |
| `transfer_memories` | Download/upload migration JSON inline across MCP servers, with optional absolute file paths and keyset pagination for large graphs. |

Every list-taking tool processes items independently and reports a per-item
`status` — one bad item never aborts the batch.

### File export and migration

File operations are exposed through the same MCP tool registry in both stdio
and HTTP/SSE modes. `export_graph_html` takes an absolute `output_path`.

For migration between machines, `transfer_memories(op="export")` returns the
portable migration object in its `data` field (download), and
`transfer_memories(op="import", data=...)` accepts that object directly
(upload). This avoids incorrectly asking a remote HTTP server to read a path
from the client's filesystem:

```json
{"op": "export"}
{"op": "import", "data": {"format": "brainmemory-export", "format_version": 1, "memories": []}, "on_conflict": "overwrite"}
```

Server-local file workflows remain supported by supplying an absolute
`output_path` on export or an absolute `input_path` on import. Relative paths
(including `./file` and `../file`) and explicit `.` / `..` path segments are
rejected. Parent directories are created for file exports.

```json
{"output_path": "/absolute/workspace/memory-graph.html"}
{"op": "export", "output_path": "/absolute/workspace/brainmemory.json"}
{"op": "import", "input_path": "/absolute/workspace/brainmemory.json", "on_conflict": "skip"}
```

#### Paginated migration for large graphs (v0.11.7+)

Two independent servers (e.g. a **local stdio** server and a **remote
HTTP/SSE** server, or vice versa) share no filesystem, so migrating between
them goes through the calling agent's context — one giant `export` can be too
big for a huge memory graph. Add `limit` (and `scope="memories"`,
`scope="links"`, or `scope="trash"`) to page through it instead:

```json
{"op": "export", "scope": "memories", "limit": 200}
```

Each call returns `has_more` / `next_cursor` at the top level; keep calling
with `cursor=<next_cursor>` until `has_more` is `false`, feeding each page's
`data` straight into `{"op": "import", "data": ...}` on the destination
server. Page through every `scope="memories"` batch **first**, then repeat
with `scope="links"` — an `import` never errors on a link whose endpoints
don't exist yet, it just skips it (reported in `links_skipped`), so
exporting links before their memories only under-imports links, it never
corrupts data. `scope="all"` (the default) stays a single unpaginated
full-graph export/import, unchanged from before; `limit`/`cursor` require a
single scope (`"memories"`, `"links"`, or `"trash"` — not `"all"`).
Pagination uses a stable keyset cursor (plain base64url text — safe to
copy/paste through any client), so it stays O(page size) per call regardless
of how large the graph is.

Row count alone does not bound payload size: a `limit` of 100 can still be
too big if some memories hold large content (e.g. full book-text sections).
Start with a modest `limit` (15-25) for graphs with long-content memories and
raise it once you have confirmed pages stay comfortably within your client's
tool-result budget.

```json
{"op": "export", "scope": "memories", "limit": 200, "cursor": "<next_cursor>"}
{"op": "export", "scope": "links", "limit": 500}
{"op": "export", "scope": "trash", "limit": 50}
```

`scope="trash"` transfers exact soft-delete snapshots separately, preserving
memory IDs, `deleted_at`, embedded details, and embedded links without a
restore/forget workaround. Import trash pages with the same `op="import"`
(the payload's own `"trash"` key routes it automatically — no separate
import op); `on_conflict="skip"` is idempotent and `"overwrite"` replaces an
existing trash snapshot. `category`/`tags` filters and `scope="all"` are not
applicable to `scope="trash"` (trash rows carry no category/tag filtering).

### Mixed-operation batches

`edit_details` — each item's `op` selects the operation:

```json
{"items": [
  {"op": "add",    "memory_id": "<id>", "content": "config lives in /etc/nginx"},
  {"op": "update", "detail_id": "<id>", "content": "corrected fact"},
  {"op": "delete", "detail_id": "<id>"}
]}
```

`edit_links` — connect/disconnect memories, mixed in one call:

```json
{"items": [
  {"op": "link",   "from_id": "<a>", "to_id": "<b>", "relation": "depends_on", "weight": 0.9},
  {"op": "link",   "from_id": "<a>", "to_id": "<c>"},
  {"op": "unlink", "from_id": "<a>", "to_id": "<d>"}
]}
```

Re-linking the same from/to/relation updates the weight (upsert). Detail ids
are returned by the `add` op and by `recall_memories(include_details=true)`.

Two read-only resources are exposed as JSON: `brainmemory://stats` (the summary)
and `brainmemory://graph` (the nodes + links map).

> **Migrating from v0.8.0 or earlier:** the singular tools (`store_memory`,
> `recall_memory`, `update_memory`, `forget_memory`, `add_detail`,
> `link_memories`, `unlink_memories`) and the v0.8.0 bulk names
> (`store_memories` kept its name; `add_details`, `link_memories_bulk`,
> `unlink_memories_bulk` were folded into `edit_details` / `edit_links`) are
> replaced by the 15 tools above. The **database is untouched** — only the
> tool names/shapes changed, not the storage or graph model.

## Search (like a search engine)

`search_memory` no longer needs a single keyword. It tokenises your query and
ranks memories by relevance, so full sentences work:

- **Full-text + BM25** — a SQLite **FTS5** index over content/tags/category/
  details (kept in sync by triggers), ranked with BM25. Multi-word / long
  queries match memories containing *any* (or, with `mode="all"`, *every*) term,
  with prefix + Porter stemming (`sync` matches `syncing`).
- **Graph spreading activation** — with `expand=True` (default), memories
  connected in the knowledge graph to a text hit are pulled in with a decayed
  score, so related context surfaces even without the query words.
- **Ranking** blends text relevance with importance and recency. Each result
  carries `relevance` (0..1), `match_type` (`text` | `related` | `list`),
  `matched_terms`, and `distance` (hops from a text hit).
- **Fallback** — where a SQLite build lacks FTS5, search degrades to a tokenised
  `LIKE` term-coverage scorer, so it always works. `summarize_memories` reports
  the active engine (`fts5-bm25` or `like-fallback`).

Example: `search_memory("Burp Firefox proxy sync")` returns the relevant
memories ranked, plus anything linked to them — in a single call.

## Install

From PyPI:

```bash
python3 -m pip install brainmemory-mcp
```

From a local checkout:

```bash
python3 -m pip install .
```

Both install the package and a console script named `brainmemory-mcp`.

For development (editable install):

```bash
python3 -m pip install -e ".[dev]"
```

To build/publish a release, see [`docs/RELEASING.md`](docs/RELEASING.md).

## Run

### stdio mode (default)

Best for local MCP clients that launch the server themselves. Memory in
`~/.brainmemory-mcp`.

```bash
brainmemory-mcp

# Or without the console script
python3 -m brainmemory_mcp

# With a custom memory location
brainmemory-mcp --data-dir /path/to/memory
```

### Web mode (HTTP + SSE)

Enable with `--web` for remote / networked clients.

```bash
# Defaults: 127.0.0.1:8765, memory in ~/.brainmemory-mcp
brainmemory-mcp --web

# Custom host/port and memory location
brainmemory-mcp --web --host 0.0.0.0 --port 9000 --data-dir /path/to/memory

# Optional Bearer authorization (prefer the env var to avoid shell history)
BRAINMEMORY_KEY='replace-with-a-strong-secret' brainmemory-mcp --web
# Equivalent CLI form: brainmemory-mcp --web --key 'replace-with-a-strong-secret'
```

When `--key` or `BRAINMEMORY_KEY` is set, every web request must include:

```http
Authorization: Bearer replace-with-a-strong-secret
```

This protects both endpoints. Without a key, web mode remains unauthenticated
for backward compatibility. Use HTTPS through a reverse proxy when exposing the
server over a network; a Bearer key sent over plain HTTP is not encrypted.

Endpoints once running in web mode:

- SSE stream:      `http://<host>:<port>/sse`
- Message POST:    `http://<host>:<port>/messages/`

### Configuration

| Option | Env var | Default |
|--------|---------|---------|
| `--web` | `BRAINMEMORY_WEB` | `false` (stdio) |
| `--host` | `BRAINMEMORY_HOST` | `127.0.0.1` |
| `--port` | `BRAINMEMORY_PORT` | `8765` |
| `--key` | `BRAINMEMORY_KEY` | unset (authorization disabled) |
| `--data-dir` | `BRAINMEMORY_HOME` | `~/.brainmemory-mcp` |

## Connect a client

### stdio (recommended for local use)

Configure the client to launch the server as a subprocess:

```json
{
  "mcpServers": {
    "brainmemory": {
      "command": "uvx",
      "args": ["brainmemory-mcp"]
    }
  }
}
```

If installed on your `PATH`, you can use `"command": "brainmemory-mcp"` with
`"args": []` instead.

### Web (SSE)

Start the server with `--web`, then point an SSE-capable client at the `/sse`
endpoint:

```json
{
  "mcpServers": {
    "brainmemory": {
      "url": "http://127.0.0.1:8765/sse",
      "headers": {
        "Authorization": "Bearer replace-with-a-strong-secret"
      }
    }
  }
}
```

## How memory is stored

Memories live in `~/.brainmemory-mcp/memory.db` (SQLite, WAL mode) across three
tables:

- `memories` — nodes: `id`, `content`, `category`, `tags`, `importance` (1–5),
  `created_at`, `updated_at`.
- `memory_details` — extra facts attached to a memory (cascade-deleted with it).
- `memory_links` — directed connections `source_id -> target_id` with a
  `relation` and `weight` (cascade-deleted with either endpoint).

Search uses a SQLite **FTS5** full-text index (`memories_fts`, kept in sync by
triggers) ranked with BM25, augmented by graph spreading activation. Graph
operations (multi-hop `recall_related`, shortest-path `connect_memories`, degree
centrality in `summarize_memories`) are computed with plain SQL + a little
Python — no external services or vector database required.

Nothing is ever silently deleted — removal only happens through
`forget_memories` or explicit `delete` ops in `edit_details` / `edit_links`.
When an older database is opened that lacks the newest schema (the graph
tables or the FTS index), it is **backed up automatically** to
`~/.brainmemory-mcp/backups/` before the new objects are added.

## License

MIT