"""YAML-safe frontmatter generation using python-frontmatter.

Replaces v1's manual string concatenation (`f"tags: [{', '.join(tags)}]"`),
which breaks on tags/filenames containing colons, quotes, or commas.
"""

from __future__ import annotations

from typing import Any

import frontmatter


def create_frontmatter(
    filename: str,
    tags: list[str],
    timestamp: str,
    extra: dict[str, Any] | None = None,
) -> str:
    """Build a Markdown document consisting of only a YAML frontmatter block.

    Returns the frontmatter block (with trailing blank line) ready to be
    concatenated with the converted document body.
    """
    post = frontmatter.Post("")
    post["source"] = filename
    post["converted_date"] = timestamp
    post["tags"] = tags

    if extra:
        for key, value in extra.items():
            post[key] = value

    return frontmatter.dumps(post) + "\n"
