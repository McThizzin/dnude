"""Phase 1 unit tests: feed sample inputs through the core engine, assert output.

Run with: pytest tests/test_core.py -v
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strip.core import config as config_mod
from strip.core.converters import pdf_to_md, xml_to_md
from strip.core.engine import ConversionResult, discover_files, process_single_file
from strip.core.frontmatter import create_frontmatter

SAMPLE_XML = """<?xml version="1.0"?>
<order id="42" status="open">
  <customer name="Ada Lovelace">VIP</customer>
  <items>
    <item sku="A1" qty="3">Punch cards</item>
    <item sku="B2" qty="1">Analytical engine part</item>
  </items>
</order>"""


# ---------- frontmatter.py ----------

def test_frontmatter_basic_fields():
    fm = create_frontmatter("report.pdf", ["research", "urgent"], "2026-08-26 10:00:00")
    assert "source: report.pdf" in fm
    assert "converted_date:" in fm
    assert "tags:" in fm
    assert "research" in fm and "urgent" in fm


def test_frontmatter_escapes_special_characters():
    # Old string-concat version broke on colons/quotes/commas in filenames or tags.
    tricky_filename = 'weird: file, "name".pdf'
    fm = create_frontmatter(tricky_filename, ["tag,with,comma"], "2026-08-26 10:00:00")
    # Must be valid YAML frontmatter — parse it back out.
    assert fm.startswith("---\n")
    yaml_block = fm.split("---\n")[1]
    import yaml

    parsed = yaml.safe_load(yaml_block)
    assert parsed["source"] == tricky_filename
    assert parsed["tags"] == ["tag,with,comma"]


def test_frontmatter_extra_fields():
    fm = create_frontmatter("x.docx", ["document"], "2026-08-26 10:00:00", extra={"word_count": 150})
    assert "word_count: 150" in fm


# ---------- converters.py: xml_to_md ----------

def test_xml_to_md_preserves_attributes():
    md = xml_to_md(SAMPLE_XML)
    assert 'id="42"' in md
    assert 'status="open"' in md
    assert 'sku="A1"' in md
    assert "**order**" in md
    assert "**item**" in md


def test_xml_to_md_preserves_text_content():
    md = xml_to_md(SAMPLE_XML)
    assert "Punch cards" in md
    assert "Analytical engine part" in md
    assert "VIP" in md


def test_xml_to_md_root_heading():
    md = xml_to_md(SAMPLE_XML)
    assert md.startswith("# order")


# ---------- converters.py: pdf_to_md ----------

def _make_sample_pdf(path: Path):
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    c.drawString(100, 750, "Hello from page one")
    c.showPage()
    c.drawString(100, 750, "Hello from page two")
    c.showPage()
    c.save()


@pytest.fixture
def sample_pdf(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    _make_sample_pdf(pdf_path)
    return pdf_path


def test_pdf_to_md_combined(sample_pdf):
    pages = pdf_to_md(str(sample_pdf), split_pages=False)
    assert len(pages) == 1
    page_num, content = pages[0]
    assert page_num == 0
    assert "page one" in content
    assert "page two" in content
    assert "---" in content  # page separator


def test_pdf_to_md_split(sample_pdf):
    pages = pdf_to_md(str(sample_pdf), split_pages=True)
    assert len(pages) == 2
    assert pages[0][0] == 1
    assert pages[1][0] == 2
    assert "page one" in pages[0][1]
    assert "page two" in pages[1][1]


# ---------- engine.py: process_single_file ----------

def test_process_single_file_xml(tmp_path):
    xml_path = tmp_path / "data.xml"
    xml_path.write_text(SAMPLE_XML, encoding="utf-8")
    output_dir = tmp_path / "out"

    result = process_single_file(xml_path, output_dir, ["test"], "2026-08-26 10:00:00")

    assert isinstance(result, ConversionResult)
    assert result.success
    assert len(result.output_paths) == 1
    out_file = Path(result.output_paths[0])
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "tags:" in content
    assert "word_count:" in content
    assert result.word_count > 0


def test_process_single_file_pdf_split(tmp_path, sample_pdf):
    output_dir = tmp_path / "out"
    result = process_single_file(sample_pdf, output_dir, ["test"], "2026-08-26 10:00:00", split=True)

    assert result.success
    assert len(result.output_paths) == 2
    for p in result.output_paths:
        assert Path(p).exists()


def test_process_single_file_unsupported_extension(tmp_path):
    bad_file = tmp_path / "notes.txt"
    bad_file.write_text("hi", encoding="utf-8")
    output_dir = tmp_path / "out"

    result = process_single_file(bad_file, output_dir, ["test"], "2026-08-26 10:00:00")

    assert not result.success
    assert "Unsupported" in result.error


def test_process_single_file_corrupt_xml_returns_error_not_crash(tmp_path):
    bad_xml = tmp_path / "broken.xml"
    bad_xml.write_text("<not><closed>", encoding="utf-8")
    output_dir = tmp_path / "out"

    result = process_single_file(bad_xml, output_dir, ["test"], "2026-08-26 10:00:00")

    assert not result.success
    assert result.error is not None


def test_process_single_file_empty_xml_returns_error_not_crash(tmp_path):
    empty_xml = tmp_path / "empty.xml"
    empty_xml.write_text("", encoding="utf-8")
    output_dir = tmp_path / "out"

    result = process_single_file(empty_xml, output_dir, ["test"], "2026-08-26 10:00:00")

    assert not result.success
    assert result.error is not None


def test_process_single_file_empty_root_xml_succeeds(tmp_path):
    # A root element with no children/text is valid XML, just sparse.
    xml_path = tmp_path / "emptyroot.xml"
    xml_path.write_text("<root></root>", encoding="utf-8")
    output_dir = tmp_path / "out"

    result = process_single_file(xml_path, output_dir, ["test"], "2026-08-26 10:00:00")

    assert result.success
    assert Path(result.output_paths[0]).exists()


def test_process_single_file_corrupt_pdf_returns_error_not_crash(tmp_path):
    fake_pdf = tmp_path / "corrupt.pdf"
    fake_pdf.write_text("not a real pdf", encoding="utf-8")
    output_dir = tmp_path / "out"

    result = process_single_file(fake_pdf, output_dir, ["test"], "2026-08-26 10:00:00")

    assert not result.success
    assert result.error is not None


def test_process_single_file_permission_denied_returns_error_not_crash(tmp_path):
    xml_path = tmp_path / "locked.xml"
    xml_path.write_text(SAMPLE_XML, encoding="utf-8")
    xml_path.chmod(0o000)
    output_dir = tmp_path / "out"

    try:
        result = process_single_file(xml_path, output_dir, ["test"], "2026-08-26 10:00:00")
        # If running as root (e.g. in a container), permission bits are
        # ignored and the read succeeds — that's an environment property,
        # not a code bug, so only assert the failure path when it's real.
        if not result.success:
            assert result.error is not None
    finally:
        xml_path.chmod(0o644)


def test_batch_one_bad_file_does_not_block_others(tmp_path):
    good = tmp_path / "good.xml"
    good.write_text(SAMPLE_XML, encoding="utf-8")
    bad = tmp_path / "bad.xml"
    bad.write_text("", encoding="utf-8")
    output_dir = tmp_path / "out"

    good_result = process_single_file(good, output_dir, ["test"], "2026-08-26 10:00:00")
    bad_result = process_single_file(bad, output_dir, ["test"], "2026-08-26 10:00:00")

    assert good_result.success
    assert not bad_result.success


# ---------- engine.py: discover_files ----------

def test_discover_files_directory_recursive(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.pdf").write_text("x")
    (tmp_path / "sub" / "b.xml").write_text("x")
    (tmp_path / "ignore.txt").write_text("x")

    files = discover_files([str(tmp_path)])
    names = {f.name for f in files}
    assert names == {"a.pdf", "b.xml"}


def test_discover_files_glob(tmp_path):
    (tmp_path / "one.pdf").write_text("x")
    (tmp_path / "two.pdf").write_text("x")
    (tmp_path / "three.docx").write_text("x")

    import os

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        files = discover_files(["*.pdf"])
    finally:
        os.chdir(cwd)

    assert len(files) == 2


def test_discover_files_skips_missing_paths():
    files = discover_files(["/nonexistent/path/does/not/exist.pdf"])
    assert files == []


# ---------- config.py ----------

def test_load_default_tags_missing_file(tmp_path):
    tags = config_mod.load_default_tags(tmp_path / "nope.json")
    assert tags == ["document"]


def test_load_default_tags_valid_file(tmp_path):
    cfg = tmp_path / "tags_config.json"
    cfg.write_text(json.dumps({"default_tags": ["research", "urgent"]}))
    tags = config_mod.load_default_tags(cfg)
    assert tags == ["research", "urgent"]


def test_load_default_tags_malformed_json_falls_back(tmp_path):
    cfg = tmp_path / "tags_config.json"
    cfg.write_text("{not valid json")
    tags = config_mod.load_default_tags(cfg)
    assert tags == ["document"]
