# BrainMemory-MCP

A **Model Context Protocol (MCP)** server that gives AI/LLM agents a durable
**brain memory** — the ability to store, recall, search, summarize, and forget
information across sessions through standardized MCP tool calls.

The server speaks MCP over **HTTP + Server-Sent Events (SSE)**, so remote
MCP-capable clients (Claude, IDE agents, etc.) can connect over the network.
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

```bash
python3 -m pip install .
```

This installs the package and a console script named `brainmemory-mcp`.

For development (editable install):

```bash
python3 -m pip install -e ".[dev]"
```

## Run

```bash
# Defaults: 127.0.0.1:8765, memory in ~/.brainmemory-mcp
brainmemory-mcp

# Custom host/port and memory location
brainmemory-mcp --host 0.0.0.0 --port 9000 --data-dir /path/to/memory

# Or without the console script
python3 -m brainmemory_mcp
```

Endpoints once running:

- SSE stream:      `http://<host>:<port>/sse`
- Message POST:    `http://<host>:<port>/messages/`

### Configuration

| Option | Env var | Default |
|--------|---------|---------|
| `--host` | `BRAINMEMORY_HOST` | `127.0.0.1` |
| `--port` | `BRAINMEMORY_PORT` | `8765` |
| `--data-dir` | `BRAINMEMORY_HOME` | `~/.brainmemory-mcp` |

## Connect a client

Point any MCP client that supports SSE at the `/sse` endpoint. Example client
configuration (URL-based transport):

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
