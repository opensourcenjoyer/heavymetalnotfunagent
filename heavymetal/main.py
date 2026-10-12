import argparse
import asyncio


def run() -> None:
    p = argparse.ArgumentParser(prog="heavymetal", description="Lightweight AI agent for Solana memecoins")
    p.add_argument("--tui", action="store_true", help="launch fullscreen Textual TUI dashboard")
    p.add_argument("--web", action="store_true", help="launch browser Web UI via textual-serve")
    p.add_argument("--host", default="localhost", help="web host (default localhost)")
    p.add_argument("--port", type=int, default=8000, help="web port (default 8000)")
    p.add_argument("--devnet", action="store_true", help="use the saved devnet node (no trading; airdrop available)")
    p.add_argument("--rpc", help="use a saved node name or an RPC URL for this run")
    p.add_argument("--resume", action="store_true", help="continue the latest session")
    p.add_argument("-p", "--prompt", help="run one instruction non-interactively and exit")
    a = p.parse_args()

    # Web mode
    if a.web:
        from heavymetal.tui.web import run_web

        try:
            run_web(host=a.host, port=a.port)
        except KeyboardInterrupt:
            pass
        return

    # Fullscreen Textual TUI mode if explicitly requested
    if a.tui:
        from heavymetal.app import bootstrap
        from heavymetal.tui import launch_tui

        try:
            env = asyncio.run(bootstrap("devnet" if a.devnet else None, a.rpc, a.resume))
            launch_tui(env)
        except KeyboardInterrupt:
            pass
        return

    # Default: terminal REPL
    from heavymetal.app import main

    try:
        asyncio.run(main("devnet" if a.devnet else None, a.rpc, a.resume, a.prompt))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
