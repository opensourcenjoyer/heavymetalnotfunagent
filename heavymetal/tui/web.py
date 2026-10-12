"""Web mode runner using textual-serve: runs the Textual TUI in a web browser."""

from __future__ import annotations

import shlex
import sys

from textual_serve.server import Server


def run_web(host: str = "localhost", port: int = 8000) -> None:
    # Launches heavymetal in TUI mode through textual-serve's WebSocket bridge
    cmd = f"{shlex.quote(sys.executable)} -m heavymetal.main --tui"
    server = Server(
        command=cmd,
        host=host,
        port=port,
        title="Heavy Metal Agent - Web Terminal",
    )
    print(f"⚡ Heavy Metal Agent Web UI running at: http://{host}:{port}")
    server.serve()
