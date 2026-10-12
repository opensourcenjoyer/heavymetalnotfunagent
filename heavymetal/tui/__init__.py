"""Heavy Metal TUI package export."""

from heavymetal.tui.app import HeavyMetalApp


def launch_tui(env) -> None:
    app = HeavyMetalApp(env)
    app.run()


__all__ = ["HeavyMetalApp", "launch_tui"]
