# dnude

Document ingestion engine. Converts `.pdf`, `.docx`, and `.xml` files into structured, frontmatter-tagged Markdown.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

This installs the `dnude` command via the `[project.scripts]` entry point,
plus makes `python -m dnude` work.

## Usage

### CLI — one-shot, scriptable

```bash
# Basic: convert a couple of files with tags
dnude convert report.pdf data.xml --output ./vault --tags research

# Split PDF pages
dnude convert ./papers/*.pdf -o ./pages --split --tags paper,ml

# Point it at a directory — recurses and picks up .pdf/.docx/.xml
dnude convert ./docs/ --output ./vault

# Preview what would happen without writing anything
dnude convert ./docs/ --dry-run

# Pipe-friendly: quiet one-line summary
dnude convert report.pdf -o ./out --tags draft --quiet

# Machine-readable output for agent tool-calling
dnude convert report.pdf -o ./out --json

# Skip files unchanged since last run
dnude convert ./vault/ -o ./out --incremental
```

**Flags**

| Flag | Default | Description |
|---|---|---|
| `--output, -o` | `./output` | Output directory |
| `--tags, -t` | from `tags_config.json`, else `document` | Comma-separated tags |
| `--split` | off | PDF only: one `.md` per page instead of a combined file |
| `--workers, -w` | `min(8, cpu_count)` | Thread pool size |
| `--dry-run` | off | Show what would convert, write nothing |
| `--timestamp` | now | Override `converted_date` (ISO format) |
| `--quiet, -q` | off | One-line summary instead of the table |
| `--json` | off | Machine-readable JSON summary on stdout |
| `--incremental` | off | Skip files whose content, tags, and `--split` setting are unchanged since the last run (tracked via `.dnude_manifest.json` in the output dir) |

**Exit codes**

| Code | Meaning |
|---|---|
| `0` | All files converted successfully |
| `1` | At least one file failed |
| `2` | No valid input files found |

### TUI — interactive dashboard

Run `dnude` with no arguments to drop into the Textual TUI:

```bash
dnude
```

Enter a path, glob, or comma-separated list of paths, set an output
directory and tags, optionally toggle "Split PDF pages," and hit
**Enter** or click **Convert**. The log panel streams live per-file
success/failure as the thread pool works through the batch.

| Key | Action |
|---|---|
| `Tab` / `Shift+Tab` | Cycle focus between fields |
| `Enter` | Submit the focused input, or trigger Convert |
| `Escape` | Clear the focused field |
| `?` | Show a quick keybinding reminder in the log |
| `q` | Quit |

Open the command palette (the small ⭘ icon in the header) to search
commands, including switching themes — your choice is remembered across
sessions.

### Watch — auto-convert on file drop

```bash
# Watch a folder; convert existing files first, then anything new.
dnude watch ./inbox --output ./vault --tags research

# Skip the initial pass, only react to new/changed files.
dnude watch ./inbox --no-initial

# Non-recursive, custom debounce, JSON events.
dnude watch ./inbox --no-recursive --debounce 2.0 --json
```

`watch` runs until you hit Ctrl+C. It uses the same manifest as
`--incremental`, so restarting a watch session doesn't re-convert files
it already handled and that haven't changed — only genuinely new or
modified files get processed. Writes are debounced (default 1 second)
so a file still being copied or saved doesn't get read mid-write.

| Flag | Default | Description |
|---|---|---|
| `--output, -o` | `./output` | Output directory |
| `--tags, -t` | from config, else `document` | Comma-separated tags |
| `--split` | off | PDF only: one `.md` per page |
| `--debounce` | `1.0` | Seconds of quiet before converting a changed file |
| `--initial / --no-initial` | `--initial` | Convert existing files on startup |
| `--recursive / --no-recursive` | `--recursive` | Watch subdirectories too |
| `--json` | off | One JSON object per line instead of Rich output |

## Output layout

Each input file gets its own subfolder in the output directory, named
after the file (without extension), to avoid collisions and leave room
for co-located assets later:

```
output/
├── report/
│   └── report.md          # combined PDF (default)
├── data/
│   └── data.md             # XML
└── notes/
    └── notes.md             # DOCX
```

With `--split`, a PDF gets one file per page instead:

```
output/report/
├── report_p001.md
├── report_p002.md
└── report_p003.md
```

Every output file starts with YAML frontmatter:

```yaml
---
source: report.pdf
converted_date: '2026-08-26 10:00:00'
tags:
- research
- q3
word_count: 412
---
```

## Configuration

`tags_config.json` (optional) sets the default tags used when `--tags`
isn't passed:

```json
{
  "default_tags": ["document"]
}
```

If the file is missing or malformed, `dnude` silently falls back to
`["document"]` rather than failing.

## XML conversion notes

XML is converted with a walker that preserves attributes
and hierarchy instead of flattening them away:

```xml
<order id="42" status="open">
  <customer name="Ada Lovelace">VIP</customer>
</order>
```

becomes:

```markdown
# order
- **order** `id="42" status="open"`
  - **customer** `name="Ada Lovelace"`
    > VIP
```

## Error handling

A single bad file (corrupt PDF, malformed XML, unreadable/permission-denied
file) fails independently — it's reported with an error message and the
rest of the batch keeps going. The run's exit code (`1`) reflects that a
partial failure occurred, without aborting files that succeeded.

## Development

```bash
pip install -e . pytest reportlab pyyaml python-docx
python -m pytest tests/ -v
```

## Roadmap

Refine TUI functionality.
