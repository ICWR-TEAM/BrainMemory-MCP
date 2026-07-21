"""Command-line entry point for BrainMemory-MCP.

Two run modes are supported:

    # stdio (default) — for clients that launch the server as a subprocess,
    # e.g. an MCP config of:
    #   { "command": "uvx", "args": ["brainmemory-mcp"] }
    brainmemory-mcp
    python3 -m brainmemory_mcp

    # web (HTTP + SSE) — for remote / networked MCP clients
    brainmemory-mcp --web --host 0.0.0.0 --port 8765
"""

from __future__ import annotations

import argparse
import os

from . import __version__
from .memory import DATA_DIR_ENV, default_data_dir
from .server import run


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brainmemory-mcp",
        description=(
            "BrainMemory-MCP — Cognitive memory tools for AI agents, served over "
            "the Model Context Protocol. Runs over stdio by default (ideal for "
            "`uvx brainmemory-mcp`); use --web to serve over HTTP + SSE."
        ),
    )
    parser.add_argument(
        "--web",
        action="store_true",
        default=_env_flag("BRAINMEMORY_WEB"),
        help=(
            "Serve over HTTP + Server-Sent Events (SSE) instead of stdio. "
            "Uses --host/--port. Default: stdio."
        ),
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("BRAINMEMORY_HOST", "127.0.0.1"),
        help="Host/interface to bind in --web mode (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BRAINMEMORY_PORT", "8765")),
        help="TCP port to listen on in --web mode (default: 8765).",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help=(
            "Directory to store memories in. "
            f"Overrides ${DATA_DIR_ENV}. Default: {default_data_dir()}"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run(
            web=args.web,
            host=args.host,
            port=args.port,
            data_dir=args.data_dir,
        )
    except KeyboardInterrupt:  # pragma: no cover - interactive shutdown
        print("\nBrainMemory-MCP stopped.", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
