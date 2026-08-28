"""Content-hash manifest for incremental re-conversion.

Backs two features:
    - `dnude convert --incremental`: skip files whose content, tags, and
      split setting haven't changed since the last successful run.
    - `dnude watch`: on restart, skip re-converting files that were
      already handled and haven't changed since.

Agents that re-run `dnude` repeatedly over the same directory (a common
pattern for keeping a vault in sync) shouldn't pay to re-read and
re-convert documents that haven't changed. The manifest is a plain JSON
file living alongside the output, so it's inspectable and diffable like
everything else `dnude` produces.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = ".dnude_manifest.json"


def _manifest_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / MANIFEST_FILENAME


def load_manifest(output_dir: str | Path) -> dict[str, Any]:
    """Load the manifest for an output directory, or {} if absent/corrupt."""
    path = _manifest_path(output_dir)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_manifest(output_dir: str | Path, manifest: dict[str, Any]) -> None:
    """Write the manifest back to the output directory."""
    path = _manifest_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


def compute_hash(path: str | Path) -> str:
    """SHA-256 of a file's raw bytes, read in chunks so large PDFs are fine."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_unchanged(
    manifest: dict[str, Any],
    path: str | Path,
    file_hash: str,
    tags: list[str],
    split: bool,
) -> bool:
    """True if this exact (content, tags, split) combination was already
    converted successfully and recorded in the manifest.

    Changing tags or the split setting deliberately invalidates the
    cache entry — the output would differ even though the source file
    didn't change.
    """
    entry = manifest.get(str(Path(path).resolve()))
    if not entry:
        return False
    return (
        entry.get("hash") == file_hash and entry.get("tags") == tags and entry.get("split") == split
    )


def record(
    manifest: dict[str, Any],
    path: str | Path,
    file_hash: str,
    tags: list[str],
    split: bool,
    output_paths: list[str],
) -> None:
    """Record (or update) a successful conversion in the manifest, in place."""
    manifest[str(Path(path).resolve())] = {
        "hash": file_hash,
        "tags": tags,
        "split": split,
        "output_paths": output_paths,
    }
