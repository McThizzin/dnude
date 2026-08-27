"""Entry point router.

`strip convert ...`  -> Typer CLI (scriptable, one-shot)
`strip` (no args)    -> Textual TUI dashboard
"""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1:
        from strip.interfaces.cli import app

        app()
    else:
        from strip.interfaces.tui import StripApp

        StripApp().run()


if __name__ == "__main__":
    main()
