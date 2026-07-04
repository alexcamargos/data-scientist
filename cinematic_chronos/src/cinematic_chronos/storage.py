"""Storage adapters used by pipeline ingestion steps."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from cinematic_chronos.models import DownloadResult


class LocalRawStore:
    """Stores raw files and append-only ingestion metadata on local disk."""

    def __init__(self, root_dir: Path, manifest_path: Path) -> None:
        self.root_dir = root_dir
        self.manifest_path = manifest_path
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

    def path_for(self, *parts: str) -> Path:
        return self.root_dir.joinpath(*parts)

    def record(self, result: DownloadResult) -> None:
        with self.manifest_path.open("a", encoding="utf-8") as manifest_file:
            manifest_file.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
