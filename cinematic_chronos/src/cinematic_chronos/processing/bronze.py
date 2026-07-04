"""Bronze layer processing for Oscar data."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from cinematic_chronos.config import IngestionConfig
from cinematic_chronos.models import ProcessingResult
from cinematic_chronos.utils.columns import find_column

LOGGER = logging.getLogger(__name__)

BEST_PICTURE_CATEGORIES = {
    "best picture",
    "best motion picture",
    "best motion picture of the year",
    "best production",
    "outstanding picture",
    "outstanding production",
    "outstanding motion picture",
    "outstanding motion picture production",
    "outstanding production by a studio",
}


def process_bronze(config: IngestionConfig) -> ProcessingResult:
    """Create the bronze Oscar Best Picture nominees dataset from Kaggle raw files."""

    LOGGER.info("Starting bronze processing")
    source_path = _find_oscar_csv(
        config.raw_data_dir / "kaggle" / config.kaggle_target_dir
    )
    output_path = config.bronze_data_dir / "oscar_best_picture_nominees.parquet"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    LOGGER.info("Reading raw Oscar CSV: %s", source_path)
    raw_data = pd.read_csv(source_path)
    bronze_data = filter_best_picture_nominees(raw_data)
    bronze_data.to_parquet(
        output_path, index=False, engine="pyarrow", compression="zstd"
    )
    LOGGER.info(
        "Finished bronze processing: rows_read=%s rows_written=%s target=%s",
        len(raw_data),
        len(bronze_data),
        output_path,
    )

    return ProcessingResult(
        layer="bronze",
        source_path=str(source_path),
        target_path=str(output_path),
        rows_read=len(raw_data),
        rows_written=len(bronze_data),
        processed_at=datetime.now(UTC).isoformat(),
    )


def filter_best_picture_nominees(data: pd.DataFrame) -> pd.DataFrame:
    """Filter Oscar records to Best Picture nominees only."""

    category_column = find_column(
        data,
        candidates=("category", "award", "award_category"),
        required_content="best",
    )
    movie_column = find_column(data, candidates=("film", "movie", "title", "name"))

    category = data[category_column].fillna("").astype(str).str.strip().str.lower()
    best_picture = data[category_column].notna() & category.isin(
        BEST_PICTURE_CATEGORIES
    )
    filtered = data.loc[best_picture].copy()

    filtered[movie_column] = filtered[movie_column].fillna("").astype(str).str.strip()
    filtered = filtered[filtered[movie_column] != ""]
    filtered = filtered.drop_duplicates().reset_index(drop=True)
    return filtered


def _find_oscar_csv(raw_kaggle_dir: Path) -> Path:
    if not raw_kaggle_dir.exists():
        raise FileNotFoundError(
            f"Raw Kaggle directory not found: {raw_kaggle_dir}. Run extract first."
        )

    csv_files = sorted(raw_kaggle_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(
            f"No CSV files found in raw Kaggle directory: {raw_kaggle_dir}"
        )

    preferred = [
        csv_file
        for csv_file in csv_files
        if "oscar" in csv_file.name.lower() or "academy" in csv_file.name.lower()
    ]
    return preferred[0] if preferred else csv_files[0]
