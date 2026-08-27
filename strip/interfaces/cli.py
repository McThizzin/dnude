"""Typer CLI: `strip convert [PATHS...] [OPTIONS]`.

Exit codes (useful for scripting / agent tool-calling):
    0 = all files converted successfully
    1 = at least one file failed
    2 = no valid input files found
"""

from __future__ import annotations

import json as json_module
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from strip.core.config import load_default_tags
from strip.core.engine import SUPPORTED_EXTENSIONS, ConversionResult, discover_files, process_single_file
from strip.core.manifest import compute_hash, is_unchanged, load_manifest, record, save_manifest
from strip.core.watcher import DirectoryWatcher

app = typer.Typer(
    name="strip",
    help="Convert PDF/DOCX/XML files into frontmatter-tagged Markdown for agent consumption.",
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


@app.command()
def convert(
    paths: list[str] = typer.Argument(
        ..., help="Files, directories, or glob patterns to convert."
    ),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory."
    ),
    tags: Optional[str] = typer.Option(
        None, "--tags", "-t", help="Comma-separated tags, e.g. --tags research,urgent."
    ),
    split: bool = typer.Option(
        False, "--split", help="PDF only: write one .md per page instead of a combined file."
    ),
    workers: int = typer.Option(
        min(8, os.cpu_count() or 4), "--workers", "-w", help="Thread pool size."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would convert without writing any files."
    ),
    timestamp: Optional[str] = typer.Option(
        None, "--timestamp", help="Override converted_date (ISO format). Defaults to now."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress table/progress output; print a one-line summary."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Print a machine-readable JSON summary to stdout."
    ),
    incremental: bool = typer.Option(
        False,
        "--incremental",
        help="Skip files unchanged since the last successful run (tracked via a "
        ".strip_manifest.json in the output dir). Re-run tags/--split changes still reconvert.",
    ),
):
    """Convert PDF, DOCX, and XML files into frontmatter-tagged Markdown."""
    files = discover_files(paths)

    if not files:
        if json_output:
            print(json_module.dumps({"error": "no valid files found", "files": []}))
        else:
            err_console.print("[bold red]No valid .pdf, .docx, or .xml files found.[/bold red]")
        raise typer.Exit(code=2)

    active_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else load_default_tags()
    run_timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if dry_run:
        if json_output:
            print(json_module.dumps({
                "dry_run": True,
                "files": [str(f) for f in files],
                "output_dir": str(output),
                "tags": active_tags,
                "split": split,
            }, indent=2))
        else:
            console.print(f"[bold cyan]Dry run[/bold cyan] — {len(files)} file(s) would convert to [bold]{output}[/bold]")
            console.print(f"Tags: {', '.join(active_tags)}   Split pages: {split}")
            for f in files:
                console.print(f"  • {f}")
        raise typer.Exit(code=0)

    output.mkdir(parents=True, exist_ok=True)
    results: list[ConversionResult] = []
    skipped: list[str] = []
    manifest: dict = {}
    to_convert = files

    if incremental:
        manifest = load_manifest(output)
        to_convert = []
        for f in files:
            try:
                file_hash = compute_hash(f)
            except OSError:
                to_convert.append(f)
                continue
            if is_unchanged(manifest, f, file_hash, active_tags, split):
                skipped.append(f.name)
            else:
                to_convert.append(f)

    def _run_and_record(f: Path) -> ConversionResult:
        result = process_single_file(f, output, active_tags, run_timestamp, split)
        if incremental and result.success:
            try:
                file_hash = compute_hash(f)
                record(manifest, f, file_hash, active_tags, split, result.output_paths)
            except OSError:
                pass
        return result

    if to_convert:
        if quiet or json_output:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_run_and_record, f): f for f in to_convert}
                for future in as_completed(futures):
                    results.append(future.result())
        else:
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed}/{task.total})"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task_id = progress.add_task("Converting", total=len(to_convert))
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {executor.submit(_run_and_record, f): f for f in to_convert}
                    for future in as_completed(futures):
                        result = future.result()
                        results.append(result)
                        status = "[green]✅[/green]" if result.success else "[red]❌[/red]"
                        console.print(f"{status} {result.filename}" + (f" — {result.error}" if result.error else ""))
                        progress.advance(task_id)

    if incremental:
        save_manifest(output, manifest)

    succeeded = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    if json_output:
        print(json_module.dumps({
            "total": len(results) + len(skipped),
            "succeeded": len(succeeded),
            "failed": len(failed),
            "skipped": skipped,
            "results": [
                {
                    "filename": r.filename,
                    "success": r.success,
                    "output_paths": r.output_paths,
                    "error": r.error,
                    "word_count": r.word_count,
                }
                for r in results
            ],
        }, indent=2))
    elif quiet:
        skip_note = f", {len(skipped)} unchanged" if incremental else ""
        console.print(f"{len(succeeded)}/{len(results)} converted, {len(failed)} failed{skip_note}.")
    else:
        table = Table(title="Conversion Summary")
        table.add_column("File")
        table.add_column("Status")
        table.add_column("Words", justify="right")
        table.add_column("Output")
        for r in results:
            status = "[green]Success[/green]" if r.success else f"[red]Failed[/red]: {r.error}"
            output_display = ", ".join(Path(p).name for p in r.output_paths) if r.output_paths else "—"
            table.add_row(r.filename, status, str(r.word_count) if r.success else "—", output_display)
        for name in skipped:
            table.add_row(name, "[dim]Skipped (unchanged)[/dim]", "—", "—")
        console.print(table)
        summary = f"[bold]{len(succeeded)}/{len(results)} converted successfully.[/bold]"
        if incremental and skipped:
            summary += f" [dim]{len(skipped)} unchanged, skipped.[/dim]"
        console.print(summary)

    if failed:
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)


@app.command()
def watch(
    directory: Path = typer.Argument(..., help="Directory to monitor for new or changed files."),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory."
    ),
    tags: Optional[str] = typer.Option(
        None, "--tags", "-t", help="Comma-separated tags, e.g. --tags research,urgent."
    ),
    split: bool = typer.Option(
        False, "--split", help="PDF only: write one .md per page instead of a combined file."
    ),
    debounce: float = typer.Option(
        1.0, "--debounce", help="Seconds to wait after the last change before converting a file."
    ),
    initial: bool = typer.Option(
        True,
        "--initial/--no-initial",
        help="Convert files already in DIRECTORY on startup, before watching for new ones.",
    ),
    recursive: bool = typer.Option(
        True, "--recursive/--no-recursive", help="Watch subdirectories too."
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit one JSON object per line instead of Rich output — good for piping to an agent.",
    ),
):
    """Monitor DIRECTORY and auto-convert new or changed PDF/DOCX/XML files as they land.

    Runs until interrupted with Ctrl+C. Always uses the manifest (the same
    mechanism behind `convert --incremental`) so a restarted watch doesn't
    re-convert files it already handled and that haven't changed.
    """
    if not directory.is_dir():
        err_console.print(f"[bold red]{directory} is not a directory.[/bold red]")
        raise typer.Exit(code=2)

    active_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else load_default_tags()
    output.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(output)

    def emit(event: dict) -> None:
        if json_output:
            print(json_module.dumps(event))
            return
        if event["status"] == "converted":
            console.print(f"[green]✅[/green] {event['filename']} ({event['word_count']} words)")
        elif event["status"] == "skipped":
            console.print(f"[dim]⏭  {event['filename']} (unchanged)[/dim]")
        elif event["status"] == "failed":
            console.print(f"[red]❌[/red] {event['filename']} — {event['error']}")

    def convert_path(path_str: str) -> None:
        path = Path(path_str)
        if not path.is_file():
            return

        try:
            file_hash = compute_hash(path)
        except OSError as e:
            emit({"status": "failed", "filename": path.name, "error": str(e)})
            return

        if is_unchanged(manifest, path, file_hash, active_tags, split):
            emit({"status": "skipped", "filename": path.name})
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result = process_single_file(path, output, active_tags, timestamp, split)

        if result.success:
            record(manifest, path, file_hash, active_tags, split, result.output_paths)
            save_manifest(output, manifest)
            emit({
                "status": "converted",
                "filename": result.filename,
                "output_paths": result.output_paths,
                "word_count": result.word_count,
            })
        else:
            emit({"status": "failed", "filename": result.filename, "error": result.error})

    if initial:
        if recursive:
            existing = discover_files([str(directory)])
        else:
            existing = sorted(
                p for p in directory.iterdir()
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
            )
        if not json_output:
            console.print(f"[bold cyan]Initial scan[/bold cyan]: {len(existing)} existing file(s).")
        for f in existing:
            convert_path(str(f))

    watcher = DirectoryWatcher(directory, convert_path, debounce_seconds=debounce, recursive=recursive)

    if not json_output:
        console.print(
            f"[bold]Watching[/bold] {directory} for .pdf/.docx/.xml changes — Ctrl+C to stop."
        )

    watcher.run_forever()

    if not json_output:
        console.print("\n[bold]Stopped watching.[/bold]")
