#!/usr/bin/env python
# encoding: utf-8
"""Medallion processing steps for Cinematic Chronos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from cinematic_chronos.ingestion import IngestionConfig


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


@dataclass(frozen=True)
class ProcessingResult:
    """Metadata emitted after a medallion processing step."""

    layer: str
    source_path: str
    target_path: str
    rows_read: int
    rows_written: int
    processed_at: str
    status: str = "processed"


def process_bronze(config: IngestionConfig) -> ProcessingResult:
    """Create the bronze Oscar Best Picture nominees dataset from Kaggle raw files."""

    source_path = _find_oscar_csv(config.raw_data_dir / "kaggle" / config.kaggle_target_dir)
    output_path = config.bronze_data_dir / "oscar_best_picture_nominees.parquet"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw_data = pd.read_csv(source_path)
    bronze_data = filter_best_picture_nominees(raw_data)
    bronze_data.to_parquet(output_path, index=False, engine="pyarrow", compression="zstd")

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

    category_column = _find_column(
        data,
        candidates=("category", "award", "award_category"),
        required_content="best",
    )
    movie_column = _find_column(data, candidates=("film", "movie", "title", "name"))

    category = data[category_column].fillna("").astype(str).str.strip().str.lower()
    best_picture = data[category_column].notna() & category.isin(BEST_PICTURE_CATEGORIES)
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
        raise FileNotFoundError(f"No CSV files found in raw Kaggle directory: {raw_kaggle_dir}")

    preferred = [
        csv_file
        for csv_file in csv_files
        if "oscar" in csv_file.name.lower() or "academy" in csv_file.name.lower()
    ]
    return preferred[0] if preferred else csv_files[0]


def _find_column(
    data: pd.DataFrame,
    candidates: tuple[str, ...],
    required_content: str | None = None,
) -> str:
    normalized_columns = {_normalize_column(column): column for column in data.columns}
    for candidate in candidates:
        column = normalized_columns.get(_normalize_column(candidate))
        if column and (
            required_content is None
            or data[column].fillna("").astype(str).str.lower().str.contains(required_content).any()
        ):
            return column

    candidate_list = ", ".join(candidates)
    raise ValueError(
        f"Could not find a compatible column. Expected one of: {candidate_list}. "
        f"Available columns: {', '.join(map(str, data.columns))}"
    )


def _normalize_column(column: object) -> str:
    return str(column).strip().lower().replace(" ", "_").replace("-", "_")
