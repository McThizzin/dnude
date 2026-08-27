"""Textual TUI dashboard.

Replaces the old tkinter/customtkinter GUI. Key architectural change from
v1 (per spec section 5): `self.after()` doesn't exist in Textual. Threaded
work goes in an `@work(thread=True)` method, and UI updates from that
thread go through `self.app.call_from_thread(...)`.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
)

from strip.core.config import load_default_tags
from strip.core.engine import discover_files, process_single_file
from strip.core.settings import load_theme, save_theme


class StripApp(App):
    """strip's interactive TUI."""

    TITLE = "strip"

    CSS = """
    #main {
        height: 1fr;
    }
    #input-panel {
        width: 1fr;
        border: round $primary;
        padding: 1 2;
    }
    #log-panel {
        width: 2fr;
        border: round $primary;
        padding: 1 2;
    }
    #convert-btn {
        margin-top: 1;
        width: 100%;
    }
    Input {
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("question_mark", "help", "Help"),
        ("escape", "clear_field", "Clear field"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="main"):
            with Vertical(id="input-panel"):
                yield Label("Files/Paths (glob or dir OK):")
                yield Input(placeholder="./docs/**/*.pdf", id="paths-input")
                yield Label("Output Dir:")
                yield Input(value="./output", id="output-input")
                yield Label("Tags (comma-sep):")
                yield Input(placeholder=", ".join(load_default_tags()), id="tags-input")
                yield Checkbox("Split PDF pages", id="split-checkbox")
                yield Button("Convert", id="convert-btn", variant="success")
                yield ProgressBar(id="progress", total=100)
            with Vertical(id="log-panel"):
                yield Label("Live Log")
                yield RichLog(id="log", wrap=True, highlight=True, markup=True)
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        """Restore the last-chosen theme (Textual otherwise resets to
        default on every launch since theme isn't persisted natively)."""
        self.theme = load_theme(default=self.theme)

    def watch_theme(self, old_theme: str, new_theme: str) -> None:
        """Called whenever the theme changes (including via the command
        palette's built-in theme switcher). Runs alongside Textual's own
        internal theme-application watcher, not instead of it."""
        save_theme(new_theme)

    def action_clear_field(self) -> None:
        focused = self.focused
        if isinstance(focused, Input):
            focused.value = ""

    def action_help(self) -> None:
        log = self.query_one("#log", RichLog)
        log.write(
            "[bold]Keys:[/bold] Tab/Shift+Tab move focus · Enter converts · "
            "Escape clears field · q quits"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "convert-btn":
            self.start_conversion()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.start_conversion()

    def start_conversion(self) -> None:
        paths_raw = self.query_one("#paths-input", Input).value.strip()
        output_dir = self.query_one("#output-input", Input).value.strip() or "./output"
        tags_raw = self.query_one("#tags-input", Input).value.strip()
        split = self.query_one("#split-checkbox", Checkbox).value

        log = self.query_one("#log", RichLog)

        if not paths_raw:
            log.write("[bold red]Enter at least one file, directory, or glob first.[/bold red]")
            return

        paths = [p.strip() for p in paths_raw.split(",") if p.strip()]
        files = discover_files(paths)

        if not files:
            log.write("[bold red]No matching .pdf, .docx, or .xml files found.[/bold red]")
            return

        active_tags = (
            [t.strip() for t in tags_raw.split(",") if t.strip()]
            if tags_raw
            else load_default_tags()
        )

        log.clear()
        log.write(f"Found {len(files)} file(s). Converting to [bold]{output_dir}[/bold]...")

        progress = self.query_one("#progress", ProgressBar)
        progress.update(total=len(files), progress=0)

        convert_btn = self.query_one("#convert-btn", Button)
        convert_btn.disabled = True

        self.run_conversion(files, output_dir, active_tags, split)

    @work(thread=True)
    def run_conversion(
        self, files: list, output_dir: str, active_tags: list[str], split: bool
    ) -> None:
        """Runs in a real OS thread; the ThreadPoolExecutor lives in here.

        UI updates must go through call_from_thread — this is the
        Textual equivalent of v1's `self.after(0, ...)`.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        max_workers = min(8, os.cpu_count() or 4)
        completed = 0
        total = len(files)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    process_single_file, f, output_dir, active_tags, timestamp, split
                ): f
                for f in files
            }
            for future in as_completed(futures):
                result = future.result()
                completed += 1

                if result.success:
                    line = f"[green]✅[/green] {result.filename} ({result.word_count} words)"
                else:
                    line = f"[red]❌[/red] {result.filename} — {result.error}"

                self.app.call_from_thread(self._append_log, line)
                self.app.call_from_thread(self._update_progress, completed)

        self.app.call_from_thread(self._conversion_done, total)

    def _append_log(self, line: str) -> None:
        self.query_one("#log", RichLog).write(line)

    def _update_progress(self, completed: int) -> None:
        self.query_one("#progress", ProgressBar).update(progress=completed)

    def _conversion_done(self, total: int) -> None:
        log = self.query_one("#log", RichLog)
        log.write(f"[bold]Done.[/bold] Processed {total} file(s).")
        self.query_one("#convert-btn", Button).disabled = False


def main() -> None:
    StripApp().run()


if __name__ == "__main__":
    main()
