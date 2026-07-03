#!/usr/bin/env python
# encoding: utf-8
"""Raw batch ingestion for Kaggle Oscar data."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "ingestion.json"


@dataclass(frozen=True)
class DownloadResult:
    """Metadata emitted after an extract operation."""

    source: str
    target_path: str
    status: str
    downloaded_at: str
    bytes_written: int = 0
    sha256: str | None = None
    source_uri: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class IngestionConfig:
    """Resolved ingestion settings."""

    project_dir: Path
    raw_data_dir: Path
    manifest_path: Path
    kaggle_dataset_slug: str
    kaggle_target_dir: str
    kaggle_unzip: bool


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


def load_config(config_path: Path = DEFAULT_CONFIG) -> IngestionConfig:
    """Load JSON configuration and resolve project-relative paths."""

    config_path = config_path.resolve()
    project_dir = config_path.parents[1]
    with config_path.open(encoding="utf-8") as config_file:
        config: dict[str, Any] = json.load(config_file)

    raw_data_dir = _resolve_project_path(project_dir, config["raw_data_dir"])
    manifest_path = _resolve_project_path(project_dir, config["manifest_path"])

    return IngestionConfig(
        project_dir=project_dir,
        raw_data_dir=raw_data_dir,
        manifest_path=manifest_path,
        kaggle_dataset_slug=config["kaggle"]["dataset_slug"],
        kaggle_target_dir=config["kaggle"]["target_dir"],
        kaggle_unzip=bool(config["kaggle"].get("unzip", True)),
    )


class KaggleDatasetDownloader:
    """Downloads a Kaggle dataset through the configured Kaggle client."""

    def __init__(self, python_executable: str = sys.executable) -> None:
        self.python_executable = python_executable

    def download(
        self,
        store: LocalRawStore,
        dataset_slug: str,
        target_dir: str,
        *,
        unzip: bool = True,
        force: bool = False,
        dry_run: bool = False,
    ) -> DownloadResult:
        target_path = store.path_for("kaggle", target_dir)
        source = "kaggle.oscar_awards"
        if dry_run:
            return _result(source, target_path, "dry-run", source_uri=dataset_slug)

        if target_path.exists() and any(target_path.iterdir()) and not force:
            result = _result(
                source,
                target_path,
                "skipped",
                source_uri=dataset_slug,
                message="Target directory already contains files. Use --force to refresh it.",
            )
            store.record(result)
            return result

        target_path.mkdir(parents=True, exist_ok=True)
        command = self._build_command(dataset_slug, target_path, unzip, force)
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as error:
            raise RuntimeError(_missing_kaggle_message()) from error
        except subprocess.CalledProcessError as error:
            details = (error.stderr or error.stdout or "").strip()
            raise RuntimeError(
                "Kaggle download failed. Check Kaggle credentials and dataset access. "
                f"Details: {details}"
            ) from error

        bytes_written = sum(
            file_path.stat().st_size for file_path in target_path.rglob("*") if file_path.is_file()
        )
        result = _result(
            source,
            target_path,
            "downloaded",
            bytes_written=bytes_written,
            source_uri=dataset_slug,
            message=completed.stdout.strip() or None,
        )
        store.record(result)
        return result

    def _build_command(
        self,
        dataset_slug: str,
        target_path: Path,
        unzip: bool,
        force: bool,
    ) -> list[str]:
        if importlib.util.find_spec("kaggle"):
            command = [self.python_executable, "-m", "kaggle"]
        elif shutil.which("kaggle"):
            command = ["kaggle"]
        else:
            raise RuntimeError(_missing_kaggle_message())

        command.extend(["datasets", "download", "-d", dataset_slug, "-p", str(target_path)])
        if unzip:
            command.append("--unzip")
        if force:
            command.append("--force")
        return command


def ingest_all(config: IngestionConfig, *, force: bool, dry_run: bool) -> list[DownloadResult]:
    """Run the configured batch extract jobs."""

    store = LocalRawStore(config.raw_data_dir, config.manifest_path)
    return [
        KaggleDatasetDownloader().download(
            store,
            config.kaggle_dataset_slug,
            config.kaggle_target_dir,
            unzip=config.kaggle_unzip,
            force=force,
            dry_run=dry_run,
        )
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Cinematic Chronos raw batch ingestion.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to ingestion JSON configuration.",
    )
    parser.add_argument(
        "--source",
        choices=("kaggle",),
        default="kaggle",
        help="Source to ingest.",
    )
    parser.add_argument("--force", action="store_true", help="Refresh existing raw files.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve targets without downloading files.",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    results = ingest_all(config, force=args.force, dry_run=args.dry_run)
    for result in results:
        print(json.dumps(asdict(result), ensure_ascii=False))
    return 0


def _resolve_project_path(project_dir: Path, path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else project_dir / path


def _result(
    source: str,
    target_path: Path,
    status: str,
    *,
    downloaded_at: str | None = None,
    bytes_written: int = 0,
    sha256: str | None = None,
    source_uri: str | None = None,
    message: str | None = None,
) -> DownloadResult:
    return DownloadResult(
        source=source,
        target_path=str(target_path),
        status=status,
        downloaded_at=downloaded_at or datetime.now(UTC).isoformat(),
        bytes_written=bytes_written,
        sha256=sha256,
        source_uri=source_uri,
        message=message,
    )


def _missing_kaggle_message() -> str:
    return (
        "Kaggle client is not available. Install it in the project venv with "
        "`python -m pip install kaggle` and configure KAGGLE_USERNAME/KAGGLE_KEY "
        "or `%USERPROFILE%\\.kaggle\\kaggle.json`."
    )


if __name__ == "__main__":
    raise SystemExit(main())
