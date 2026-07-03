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
    bronze_data_dir: Path
    silver_data_dir: Path
    manifest_path: Path
    kaggle_dataset_slug: str
    kaggle_target_dir: str
    kaggle_unzip: bool
    tmdb_env_path: Path
    tmdb_api_key_env: str
    tmdb_cache_dir: Path
    tmdb_language: str
    tmdb_request_interval_seconds: float


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
    bronze_data_dir = _resolve_project_path(project_dir, config["bronze_data_dir"])
    silver_data_dir = _resolve_project_path(
        project_dir,
        config.get("silver_data_dir", "data/silver"),
    )
    manifest_path = _resolve_project_path(project_dir, config["manifest_path"])
    tmdb_config = config.get("tmdb", {})
    tmdb_cache_dir = _resolve_project_path(
        project_dir,
        tmdb_config.get("cache_dir", "data/raw/tmdb/runtime_cache"),
    )
    tmdb_env_path = _resolve_project_path(project_dir, tmdb_config.get("env_path", ".env"))

    return IngestionConfig(
        project_dir=project_dir,
        raw_data_dir=raw_data_dir,
        bronze_data_dir=bronze_data_dir,
        silver_data_dir=silver_data_dir,
        manifest_path=manifest_path,
        kaggle_dataset_slug=config["kaggle"]["dataset_slug"],
        kaggle_target_dir=config["kaggle"]["target_dir"],
        kaggle_unzip=bool(config["kaggle"].get("unzip", True)),
        tmdb_env_path=tmdb_env_path,
        tmdb_api_key_env=tmdb_config.get("api_key_env", "TMDB_API_KEY"),
        tmdb_cache_dir=tmdb_cache_dir,
        tmdb_language=tmdb_config.get("language", "en-US"),
        tmdb_request_interval_seconds=float(tmdb_config.get("request_interval_seconds", 0.25)),
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
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {"extract", "process-bronze", "enrich-tmdb-runtime", "-h", "--help"}:
        argv.insert(0, "extract")

    parser = argparse.ArgumentParser(description="Run Cinematic Chronos data pipeline tasks.")
    subparsers = parser.add_subparsers(dest="command")

    extract_parser = subparsers.add_parser("extract", help="Run raw Kaggle ingestion.")
    extract_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to ingestion JSON configuration.",
    )
    extract_parser.add_argument(
        "--source",
        choices=("kaggle",),
        default="kaggle",
        help="Source to ingest.",
    )
    extract_parser.add_argument("--force", action="store_true", help="Refresh existing raw files.")
    extract_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve targets without downloading files.",
    )

    bronze_parser = subparsers.add_parser(
        "process-bronze",
        help="Filter Kaggle Oscar data to Best Picture nominees.",
    )
    bronze_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to ingestion JSON configuration.",
    )

    tmdb_parser = subparsers.add_parser(
        "enrich-tmdb-runtime",
        help="Use TMDb to fill runtime only for Oscar movies without an IMDb runtime match.",
    )
    tmdb_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to ingestion JSON configuration.",
    )
    tmdb_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many movies would require TMDb without calling the API.",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.command == "process-bronze":
        from cinematic_chronos.processing import process_bronze

        print(json.dumps(asdict(process_bronze(config)), ensure_ascii=False))
    elif args.command == "enrich-tmdb-runtime":
        from cinematic_chronos.processing import enrich_tmdb_runtime

        print(json.dumps(asdict(enrich_tmdb_runtime(config, dry_run=args.dry_run)), ensure_ascii=False))
    else:
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
