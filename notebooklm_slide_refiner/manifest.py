"""Manifest logging for page processing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ManifestEntry:
    """Manifest entry for a page."""

    page_index: int
    raw_path: str
    enhanced_path: str | None
    status: str
    duration_ms: int
    error: str | None

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "page_index": self.page_index,
            "raw_path": self.raw_path,
            "enhanced_path": self.enhanced_path,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }
        return json.dumps(payload, ensure_ascii=False)


class ManifestWriter:
    """Append-only JSONL manifest writer."""

    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = manifest_path
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: ManifestEntry) -> None:
        with self.manifest_path.open("a", encoding="utf-8") as handle:
            handle.write(entry.to_json() + "\n")
