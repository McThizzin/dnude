"""Tests for the manifest (incremental conversion) and DirectoryWatcher."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strip.core.manifest import compute_hash, is_unchanged, load_manifest, record, save_manifest
from strip.core.watcher import DirectoryWatcher

SAMPLE_XML = '<order id="42"><item>Punch cards</item></order>'


# ---------- manifest.py ----------

def test_manifest_round_trip(tmp_path):
    manifest = {}
    xml_path = tmp_path / "data.xml"
    xml_path.write_text(SAMPLE_XML, encoding="utf-8")
    file_hash = compute_hash(xml_path)

    assert not is_unchanged(manifest, xml_path, file_hash, ["research"], False)

    record(manifest, xml_path, file_hash, ["research"], False, ["out/data.md"])
    save_manifest(tmp_path / "out", manifest)

    reloaded = load_manifest(tmp_path / "out")
    assert is_unchanged(reloaded, xml_path, file_hash, ["research"], False)


def test_manifest_detects_content_change(tmp_path):
    manifest = {}
    xml_path = tmp_path / "data.xml"
    xml_path.write_text(SAMPLE_XML, encoding="utf-8")
    original_hash = compute_hash(xml_path)
    record(manifest, xml_path, original_hash, ["research"], False, ["out/data.md"])

    xml_path.write_text(SAMPLE_XML + "<extra/>", encoding="utf-8")
    new_hash = compute_hash(xml_path)

    assert new_hash != original_hash
    assert not is_unchanged(manifest, xml_path, new_hash, ["research"], False)


def test_manifest_detects_tag_change(tmp_path):
    manifest = {}
    xml_path = tmp_path / "data.xml"
    xml_path.write_text(SAMPLE_XML, encoding="utf-8")
    file_hash = compute_hash(xml_path)
    record(manifest, xml_path, file_hash, ["research"], False, ["out/data.md"])

    # Same content, different tags -> must reconvert, output would differ.
    assert not is_unchanged(manifest, xml_path, file_hash, ["urgent"], False)


def test_manifest_detects_split_change(tmp_path):
    manifest = {}
    xml_path = tmp_path / "data.xml"
    xml_path.write_text(SAMPLE_XML, encoding="utf-8")
    file_hash = compute_hash(xml_path)
    record(manifest, xml_path, file_hash, ["research"], False, ["out/data.md"])

    assert not is_unchanged(manifest, xml_path, file_hash, ["research"], True)


def test_load_manifest_missing_file(tmp_path):
    assert load_manifest(tmp_path / "does_not_exist") == {}


def test_load_manifest_corrupt_file(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / ".strip_manifest.json").write_text("{not valid json", encoding="utf-8")
    assert load_manifest(out_dir) == {}


# ---------- watcher.py ----------

def test_directory_watcher_fires_on_new_file(tmp_path):
    seen = []
    watcher = DirectoryWatcher(tmp_path, seen.append, debounce_seconds=0.2)
    watcher.start()
    try:
        target = tmp_path / "new.xml"
        target.write_text(SAMPLE_XML, encoding="utf-8")

        deadline = time.time() + 5
        while not seen and time.time() < deadline:
            time.sleep(0.1)

        assert seen, "watcher never fired for a new supported file"
        assert Path(seen[0]).name == "new.xml"
    finally:
        watcher.stop()


def test_directory_watcher_debounces_rapid_writes(tmp_path):
    seen = []
    watcher = DirectoryWatcher(tmp_path, seen.append, debounce_seconds=0.3)
    watcher.start()
    try:
        target = tmp_path / "burst.xml"
        for i in range(5):
            target.write_text(SAMPLE_XML + f"<!-- {i} -->", encoding="utf-8")
            time.sleep(0.05)

        deadline = time.time() + 5
        while not seen and time.time() < deadline:
            time.sleep(0.1)
        time.sleep(0.3)  # let any spurious extra fire show up if it were going to

        assert len(seen) == 1, f"expected exactly one debounced callback, got {seen}"
    finally:
        watcher.stop()


def test_directory_watcher_ignores_unsupported_extensions(tmp_path):
    seen = []
    watcher = DirectoryWatcher(tmp_path, seen.append, debounce_seconds=0.2)
    watcher.start()
    try:
        (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
        time.sleep(0.6)
        assert seen == []
    finally:
        watcher.stop()
