"""Batch extract layer for the Cinematic Chronos project."""

from cinematic_chronos.ingestion import (
    DownloadResult,
    IngestionConfig,
    KaggleDatasetDownloader,
    LocalRawStore,
    ingest_all,
    load_config,
)
from cinematic_chronos.processing import (
    ProcessingResult,
    filter_best_picture_nominees,
    process_bronze,
)

__all__ = [
    "DownloadResult",
    "IngestionConfig",
    "KaggleDatasetDownloader",
    "LocalRawStore",
    "ProcessingResult",
    "filter_best_picture_nominees",
    "ingest_all",
    "load_config",
    "process_bronze",
]
