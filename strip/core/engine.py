"""Orchestration: turn a single input file into one or more output .md files.

Also provides discover_files(), used by both the CLI and TUI to expand
paths/directories/globs into a concrete file list before conversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from strip.core.converters import docx_to_md, pdf_to_md, xml_to_md
from strip.core.frontmatter import create_frontmatter

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xml"}


@dataclass
class ConversionResult:
    """Structured result of converting a single input file.

    Replaces v1's bare filename-string return, so the CLI/TUI can display
    richer per-file status (success, output paths, error, size) instead of
    just a name.
    """

    filename: str
    success: bool
    output_paths: list[str] = field(default_factory=list)
    error: str | None = None
    word_count: int = 0


def discover_files(paths: list[str | Path]) -> list[Path]:
    """Expand a list of paths/directories/globs into concrete supported files.

    - A file path is kept as-is if its extension is supported.
    - A directory is scanned recursively for supported extensions.
    - A path containing `*` or `?` is treated as a glob pattern (resolved
      relative to the current working directory).

    Returns a de-duplicated, sorted list of Path objects. Unsupported or
    nonexistent paths are silently skipped — callers that need a hard
    error for "no files found" should check for an empty return list.
    """
    found: set[Path] = set()

    for raw in paths:
        raw_str = str(raw)

        if any(ch in raw_str for ch in ("*", "?", "[")):
            for match in Path().glob(raw_str):
                if match.is_file() and match.suffix.lower() in SUPPORTED_EXTENSIONS:
                    found.add(match.resolve())
            continue

        p = Path(raw_str)
        if p.is_dir():
            for ext in SUPPORTED_EXTENSIONS:
                for match in p.rglob(f"*{ext}"):
                    if match.is_file():
                        found.add(match.resolve())
        elif p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
            found.add(p.resolve())
        # else: silently skip missing/unsupported paths

    return sorted(found)


def _word_count(text: str) -> int:
    return len(text.split())


def process_single_file(
    path: str | Path,
    output_dir: str | Path,
    active_tags: list[str],
    timestamp: str,
    split: bool = False,
) -> ConversionResult:
    """Convert one supported file into frontmatter-tagged Markdown output(s).

    Creates a subfolder per input file (output/clean_name/...) to avoid
    filename collisions and keep room for future co-located assets.
    """
    path = Path(path)
    filename = path.name
    clean_name = path.stem
    folder_path = Path(output_dir) / clean_name

    try:
        suffix = path.suffix.lower()

        if suffix == ".docx":
            body = docx_to_md(str(path))
            folder_path.mkdir(parents=True, exist_ok=True)
            fm = create_frontmatter(
                filename, active_tags, timestamp, extra={"word_count": _word_count(body)}
            )
            out_path = folder_path / f"{clean_name}.md"
            out_path.write_text(fm + body, encoding="utf-8")
            return ConversionResult(
                filename=filename,
                success=True,
                output_paths=[str(out_path)],
                word_count=_word_count(body),
            )

        elif suffix == ".xml":
            xml_content = path.read_text(encoding="utf-8")
            body = xml_to_md(xml_content)
            folder_path.mkdir(parents=True, exist_ok=True)
            fm = create_frontmatter(
                filename, active_tags, timestamp, extra={"word_count": _word_count(body)}
            )
            out_path = folder_path / f"{clean_name}.md"
            out_path.write_text(fm + body, encoding="utf-8")
            return ConversionResult(
                filename=filename,
                success=True,
                output_paths=[str(out_path)],
                word_count=_word_count(body),
            )

        elif suffix == ".pdf":
            pages = pdf_to_md(str(path), split_pages=split)
            folder_path.mkdir(parents=True, exist_ok=True)
            output_paths: list[str] = []
            total_words = 0

            for page_num, content in pages:
                total_words += _word_count(content)
                source_label = filename if page_num == 0 else f"{filename} (page {page_num})"
                fm = create_frontmatter(
                    source_label,
                    active_tags,
                    timestamp,
                    extra={"word_count": _word_count(content)},
                )
                if page_num == 0:
                    out_path = folder_path / f"{clean_name}.md"
                else:
                    out_path = folder_path / f"{clean_name}_p{page_num:03d}.md"
                out_path.write_text(fm + content, encoding="utf-8")
                output_paths.append(str(out_path))

            return ConversionResult(
                filename=filename,
                success=True,
                output_paths=output_paths,
                word_count=total_words,
            )

        else:
            return ConversionResult(
                filename=filename,
                success=False,
                error=f"Unsupported file type: {filename}",
            )

    except Exception as e:
        return ConversionResult(filename=filename, success=False, error=str(e))
