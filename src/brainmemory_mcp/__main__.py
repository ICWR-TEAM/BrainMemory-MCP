"""Command-line entry point for BrainMemory-MCP.

Usage:
    brainmemory-mcp --host 0.0.0.0 --port 8765
    python3 -m brainmemory_mcp
"""

from __future__ import annotations

import argparse
import os

from . import __version__
from .memory import DATA_DIR_ENV, default_data_dir
from .server import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brainmemory-mcp",
        description=(
            "BrainMemory-MCP — Cognitive memory tools for AI agents, served over "
            "the Model Context Protocol using HTTP + SSE."
        ),
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("BRAINMEMORY_HOST", "127.0.0.1"),
        help="Host/interface to bind (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BRAINMEMORY_PORT", "8765")),
        help="TCP port to listen on (default: 8765).",
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
        run(host=args.host, port=args.port, data_dir=args.data_dir)
    except KeyboardInterrupt:  # pragma: no cover - interactive shutdown
        print("\nBrainMemory-MCP stopped.", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
