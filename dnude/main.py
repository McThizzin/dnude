"""Entry point router.

`dnude convert ...`  -> Typer CLI (scriptable, one-shot)
`dnude` (no args)    -> Textual TUI dashboard
"""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1:
        from dnude.interfaces.cli import app

        app()
    else:
        from dnude.interfaces.tui import DnudeApp

        DnudeApp().run()


if __name__ == "__main__":
    main()
