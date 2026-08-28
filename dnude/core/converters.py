"""File-format converters: docx/pdf/xml -> Markdown.

- docx_to_md: unchanged from v1 (mammoth handles it well).
- xml_to_md: rewritten to be agent-aware — preserves attributes and
  tail text instead of the old flat depth-stack that dropped them.
- pdf_to_md: now accepts `split_pages` to control whether pages are
  combined into a single entry or returned individually.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import mammoth
import pdfplumber


def docx_to_md(docx_path: str) -> str:
    """Convert a .docx file to Markdown via mammoth."""
    with open(docx_path, "rb") as docx_file:
        result = mammoth.convert_to_markdown(docx_file)
        return result.value


def xml_to_md(xml_content: str) -> str:
    """Convert XML content to Markdown, preserving attributes and hierarchy.

    Agents often need attribute data (e.g. <item id="42" status="open">),
    which the old flat depth-stack parser silently discarded. This version
    walks the tree recursively (order-preserving) and renders:
      - each element as a bulleted, indented line with its tag
      - its attributes inline as a code-formatted `key="val"` list
      - its text content as a blockquote line
      - tail text (text trailing a child, before the next sibling) too
    """
    root = ET.fromstring(xml_content)
    lines: list[str] = []

    def walk(elem: ET.Element, depth: int = 0) -> None:
        indent = "  " * depth
        attrs = " ".join(f'{k}="{v}"' for k, v in elem.attrib.items())
        attr_str = f" `{attrs}`" if attrs else ""
        lines.append(f"{indent}- **{elem.tag}**{attr_str}")

        if elem.text and elem.text.strip():
            lines.append(f"{indent}  > {elem.text.strip()}")

        for child in elem:
            walk(child, depth + 1)
            if child.tail and child.tail.strip():
                lines.append(f"{indent}  > {child.tail.strip()}")

    lines.append(f"# {root.tag}")
    walk(root)
    return "\n".join(lines)


def pdf_to_md(pdf_path: str, split_pages: bool = False) -> list[tuple[int, str]]:
    """Convert a PDF to Markdown.

    Returns a list of (page_number, content) tuples.
    - split_pages=True: one entry per page (page numbers are 1-indexed),
      intended to become separate output files (good for RAG chunking).
    - split_pages=False (default): all pages concatenated into a single
      entry, returned as [(0, combined_content)] — page number 0 signals
      "this represents the whole document," not an actual page.
    """
    pages: list[tuple[int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or "*(No text found)*"
            pages.append((i + 1, f"## Page {i + 1}\n\n{text}"))

    if not pages:
        return [(0, "*(No pages found)*")]

    if not split_pages:
        combined = "\n\n---\n\n".join(content for _, content in pages)
        return [(0, combined)]

    return pages
