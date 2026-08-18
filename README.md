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

## Cognitive Tools

### Core memory

| Tool | Description |
|------|-------------|
| `store_memory` | Persist a new memory (content, category, tags, importance). |
| `recall_memory` | Fetch a memory by id, with its details and connections. |
| `search_memory` | Search-engine style: rank memories by relevance (BM25) for multi-word/long queries; also searches details; optional graph `expand`. |
| `list_memories` | List stored memories (most important & recent first). |
| `update_memory` | Modify an existing memory (only supplied fields change). |
| `forget_memory` | Delete a memory (its details and connections cascade away). |
| `summarize_memories` | Summary statistics: totals, categories, top tags, connection stats, most-connected memories. |

### Graph memory

| Tool | Description |
|------|-------------|
| `add_detail` | Attach an extra fact/observation to an existing memory. |
| `link_memories` | Connect two memories with a directed relation (+ weight). |
| `unlink_memories` | Remove connection(s) between two memories. |
| `recall_related` | Multi-hop recall: memories connected to one memory, up to *depth* hops. |
| `connect_memories` | Shortest connection (path) between two memories. |
| `memory_map` | Return a map (nodes + links) of the memory graph. |

### Bulk operations (since v0.8.0)

One call instead of many round-trips: each bulk tool takes a **list of
per-item dicts** and never aborts on a single bad item — every item gets its
own `status` (`"stored"`/`"updated"`/`"linked"`/... , `"not_found"`, or
`"error"`) in the response, alongside an overall count.

| Tool | Bulk equivalent of | Item shape |
|------|--------------------|------------|
| `store_memories` | `store_memory` | `{content, category?, tags?, importance?}` |
| `recall_memories` | `recall_memory` | list of `memory_id`s (+ `include_connections` flag) |
| `update_memories` | `update_memory` | `{memory_id, content?, category?, tags?, importance?}` |
| `forget_memories` | `forget_memory` | list of `memory_id`s |
| `add_details` | `add_detail` | `{memory_id, content}` |
| `link_memories_bulk` | `link_memories` | `{from_id, to_id, relation?, weight?}` |
| `unlink_memories_bulk` | `unlink_memories` | `{from_id, to_id, relation?}` |

Example — store three memories and link two of them, in two calls instead of
five:

```json
// store_memories
{"items": [
  {"content": "Nginx reverse proxy config lives in /etc/nginx/sites-available/app.conf", "category": "infra", "tags": ["nginx"]},
  {"content": "Certbot auto-renews SSL at 3am via cron", "category": "infra", "tags": ["ssl"]},
  {"content": "DNS for app.example.com points to 203.0.113.10 via Cloudflare", "category": "infra"}
]}

// link_memories_bulk (using the ids returned above)
{"links": [
  {"from_id": "<id-1>", "to_id": "<id-2>", "relation": "depends_on"},
  {"from_id": "<id-1>", "to_id": "<id-3>", "relation": "depends_on"}
]}
```

Two read-only resources are exposed as JSON: `brainmemory://stats` (the summary)
and `brainmemory://graph` (the nodes + links map).

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
```

Endpoints once running in web mode:

- SSE stream:      `http://<host>:<port>/sse`
- Message POST:    `http://<host>:<port>/messages/`

### Configuration

| Option | Env var | Default |
|--------|---------|---------|
| `--web` | `BRAINMEMORY_WEB` | `false` (stdio) |
| `--host` | `BRAINMEMORY_HOST` | `127.0.0.1` |
| `--port` | `BRAINMEMORY_PORT` | `8765` |
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
      "url": "http://127.0.0.1:8765/sse"
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
`forget_memory`, `unlink_memories`, or detail deletion. When an older
database is opened that lacks the newest schema (the graph tables or the FTS
index), it is **backed up automatically** to `~/.brainmemory-mcp/backups/`
before the new objects are added.

## License

MIT
