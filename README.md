# BrainMemory-MCP

A **Model Context Protocol (MCP)** server that gives AI/LLM agents a durable
**brain memory** — the ability to store, recall, search, summarize, and forget
information across sessions through standardized MCP tool calls.

The server runs in two modes:

- **stdio** (default) — the server is launched as a subprocess by an MCP
  client (e.g. via `uvx brainmemory-mcp`).
- **web** — MCP over **HTTP + Server-Sent Events (SSE)** with `--web`, so
  remote MCP-capable clients (Claude, IDE agents, etc.) can connect over the
  network.

Memory is persisted locally under **`~/.brainmemory-mcp`** (a SQLite database).

## Cognitive Tools

| Tool | Description |
|------|-------------|
| `store_memory` | Persist a new memory (content, category, tags, importance). |
| `recall_memory` | Fetch a single memory by its id. |
| `search_memory` | Find memories by free text, category, tags and/or importance. |
| `list_memories` | List stored memories (most important & recent first). |
| `update_memory` | Modify an existing memory (only supplied fields change). |
| `forget_memory` | Delete a memory by id. |
| `summarize_memories` | Summary statistics: totals, categories, top tags. |

A read-only resource `brainmemory://stats` exposes the same summary as JSON.

## Install

From PyPI (once published):

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

Memories live in `~/.brainmemory-mcp/memory.db` (SQLite, WAL mode). Each memory
has: `id`, `content`, `category`, `tags`, `importance` (1–5), `created_at`,
`updated_at`. Nothing is ever silently deleted — removal only happens through
`forget_memory`.

## License

MIT
