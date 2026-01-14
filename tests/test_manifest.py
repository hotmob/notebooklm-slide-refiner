"""Tests for manifest writer."""

import json
from pathlib import Path

from notebooklm_slide_refiner.manifest import ManifestEntry, ManifestWriter


def test_manifest_write(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    writer = ManifestWriter(manifest_path)
    entry = ManifestEntry(
        page_index=0,
        raw_path="raw/page_0001.png",
        enhanced_path="enhanced/page_0001.png",
        status="refined",
        duration_ms=123,
        error=None,
    )
    writer.append(entry)
    lines = manifest_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["page_index"] == 0
    assert payload["status"] == "refined"
