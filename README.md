# strip

A cross-platform GUI tool for converting `.docx`, `.xml`, and `.pdf` files to Markdown with YAML frontmatter tagging.

## Features

- **Batch conversion** — process multiple files at once
- **Parallel processing** — uses a thread pool (up to 8 workers) for fast conversions
- **Tagging** — apply YAML frontmatter tags via checkboxes or configurable presets
- **Formats supported**:
  - `.docx` → Markdown (via `mammoth`)
  - `.xml`  → Markdown (iterative parser, safe for deep nesting)
  - `.pdf`  → Markdown (one `.md` per page, via `pdfplumber`)
- **Output** — each source file gets its own folder with generated Markdown files

## Dependencies

- Python 3.8+
- [mammoth](https://pypi.org/project/mammoth/)
- [pdfplumber](https://pypi.org/project/pdfplumber/)
- [customtkinter](https://pypi.org/project/customtkinter/)

Install with:

```
pip install mammoth pdfplumber customtkinter
```

On Linux you may also need `python3-tk`:

```
sudo apt install python3-tk   # Debian/Ubuntu
sudo dnf install python3-tkinter   # Fedora
```

## Usage

```
python strip.py
```

1. Click **Select Files** and choose one or more `.docx` / `.xml` / `.pdf` files.
2. Check the tags to include in the YAML frontmatter.
3. Click **Start Conversion** and pick an output folder.

### Output structure

```
output/
├── document1/
│   ├── document1.md
│   └── ...
└── report/
    ├── report_p001.md
    ├── report_p002.md
    └── ...
```

Each Markdown file includes YAML frontmatter:

```yaml
---
source: report.pdf
converted_date: 2026-05-28 12:30:00
tags: [engineering, draft]
---
```

## Configuration

Edit `tags_config.json` to customize tag presets:

- `default_tags` — applied when no checkboxes are selected
- `tag_map` — maps numeric keys to tag labels (shown as checkboxes)

## Cross-platform notes

- **Font** — falls back through `Consolas` → `Courier New` → `monospace` on Linux
- **Icon** — `.ico` is used on Windows; gracefully skipped on Linux without error
