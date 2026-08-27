"""Load default tags from tags_config.json.

v2 simplification: no more `tag_map`. The config file is just
    {"default_tags": ["document"]}
If missing or unreadable, fall back to ["document"].
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_TAGS = ["document"]
CONFIG_FILENAME = "tags_config.json"


def load_default_tags(config_path: str | Path = CONFIG_FILENAME) -> list[str]:
    """Return the default tags list from config, or the built-in fallback.

    Any error (missing file, bad JSON, wrong shape) silently falls back
    to DEFAULT_TAGS rather than raising — a broken config file should
    never crash a conversion run.
    """
    path = Path(config_path)
    if not path.exists():
        return list(DEFAULT_TAGS)

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return list(DEFAULT_TAGS)

    tags = data.get("default_tags")
    if isinstance(tags, list) and all(isinstance(t, str) for t in tags):
        return tags or list(DEFAULT_TAGS)

    return list(DEFAULT_TAGS)
