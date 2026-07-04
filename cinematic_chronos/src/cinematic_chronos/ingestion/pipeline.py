"""Ingestion pipeline orchestration."""

from __future__ import annotations

import logging

from cinematic_chronos.config import IngestionConfig
from cinematic_chronos.ingestion.kaggle import KaggleDatasetDownloader
from cinematic_chronos.models import DownloadResult
from cinematic_chronos.storage import LocalRawStore

LOGGER = logging.getLogger(__name__)


def ingest_all(
    config: IngestionConfig, *, force: bool, dry_run: bool
) -> list[DownloadResult]:
    """Run the configured batch extract jobs."""

    LOGGER.info("Starting extract jobs")
    store = LocalRawStore(config.raw_data_dir, config.manifest_path)
    results = [
        KaggleDatasetDownloader().download(
            store,
            config.kaggle_dataset_slug,
            config.kaggle_target_dir,
            unzip=config.kaggle_unzip,
            force=force,
            dry_run=dry_run,
        )
    ]
    LOGGER.info("Finished extract jobs: jobs=%s", len(results))
    return results
