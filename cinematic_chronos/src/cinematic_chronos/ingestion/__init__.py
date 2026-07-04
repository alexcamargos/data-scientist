"""Raw batch ingestion package for Cinematic Chronos."""

from cinematic_chronos.config import DEFAULT_CONFIG, IngestionConfig, load_config
from cinematic_chronos.ingestion.kaggle import KaggleDatasetDownloader
from cinematic_chronos.ingestion.pipeline import ingest_all
from cinematic_chronos.models import DownloadResult
from cinematic_chronos.storage import LocalRawStore

__all__ = [
    "DEFAULT_CONFIG",
    "DownloadResult",
    "IngestionConfig",
    "KaggleDatasetDownloader",
    "LocalRawStore",
    "ingest_all",
    "load_config",
]
