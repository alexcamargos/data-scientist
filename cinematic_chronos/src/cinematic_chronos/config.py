"""Configuration loading for Cinematic Chronos pipelines."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "ingestion.json"
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionConfig:
    """Resolved ingestion settings.

    Attributes:
        project_dir: Root directory for the Cinematic Chronos project.
        raw_data_dir: Directory for raw input data.
        bronze_data_dir: Directory for bronze datasets.
        silver_data_dir: Directory for silver datasets.
        gold_data_dir: Directory for gold datasets.
        manifest_path: JSON Lines manifest path for extract metadata.
        kaggle_dataset_slug: Kaggle dataset slug in ``owner/dataset`` format.
        kaggle_target_dir: Directory name for the Kaggle extract.
        kaggle_unzip: Whether Kaggle downloads should be unzipped.
        tmdb_env_path: Dotenv file path for TMDb credentials.
        tmdb_api_key_env: Environment variable name for the TMDb API key.
        tmdb_cache_dir: Directory for TMDb response cache files.
        tmdb_language: TMDb language code.
        tmdb_request_interval_seconds: Delay between TMDb API requests.
    """

    project_dir: Path
    raw_data_dir: Path
    bronze_data_dir: Path
    silver_data_dir: Path
    gold_data_dir: Path
    manifest_path: Path
    kaggle_dataset_slug: str
    kaggle_target_dir: str
    kaggle_unzip: bool
    tmdb_env_path: Path
    tmdb_api_key_env: str
    tmdb_cache_dir: Path
    tmdb_language: str
    tmdb_request_interval_seconds: float


def load_config(config_path: Path = DEFAULT_CONFIG) -> IngestionConfig:
    """Load JSON configuration and resolve project-relative paths.

    Args:
        config_path: Path to the ingestion JSON configuration file.

    Returns:
        Resolved ingestion configuration.
    """

    config_path = config_path.resolve()
    project_dir = config_path.parents[1]
    LOGGER.debug("Loading ingestion config from %s", config_path)
    with config_path.open(encoding="utf-8") as config_file:
        config: dict[str, Any] = json.load(config_file)

    tmdb_config = config.get("tmdb", {})
    return IngestionConfig(
        project_dir=project_dir,
        raw_data_dir=_resolve_project_path(project_dir, config["raw_data_dir"]),
        bronze_data_dir=_resolve_project_path(project_dir, config["bronze_data_dir"]),
        silver_data_dir=_resolve_project_path(
            project_dir,
            config.get("silver_data_dir", "data/silver"),
        ),
        gold_data_dir=_resolve_project_path(
            project_dir,
            config.get("gold_data_dir", "data/gold"),
        ),
        manifest_path=_resolve_project_path(project_dir, config["manifest_path"]),
        kaggle_dataset_slug=config["kaggle"]["dataset_slug"],
        kaggle_target_dir=config["kaggle"]["target_dir"],
        kaggle_unzip=bool(config["kaggle"].get("unzip", True)),
        tmdb_env_path=_resolve_project_path(
            project_dir,
            tmdb_config.get("env_path", ".env"),
        ),
        tmdb_api_key_env=tmdb_config.get("api_key_env", "TMDB_API_KEY"),
        tmdb_cache_dir=_resolve_project_path(
            project_dir,
            tmdb_config.get("cache_dir", "data/raw/tmdb/runtime_cache"),
        ),
        tmdb_language=tmdb_config.get("language", "en-US"),
        tmdb_request_interval_seconds=float(
            tmdb_config.get("request_interval_seconds", 0.25),
        ),
    )


def _resolve_project_path(project_dir: Path, path_value: str) -> Path:
    """Resolve a path value relative to the project directory.

    Args:
        project_dir: Base project directory.
        path_value: Absolute path or project-relative path from configuration.

    Returns:
        Resolved absolute or project-relative path object.
    """

    path = Path(path_value)
    return path if path.is_absolute() else project_dir / path
