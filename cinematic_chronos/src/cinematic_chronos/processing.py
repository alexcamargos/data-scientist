#!/usr/bin/env python
"""Medallion processing steps for Cinematic Chronos."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from cinematic_chronos.ingestion import IngestionConfig

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


@dataclass(frozen=True)
class RuntimeEnrichmentResult:
    """Metadata emitted after TMDb runtime enrichment."""

    layer: str
    source_path: str
    target_path: str
    rows_read: int
    rows_written: int
    tmdb_candidates: int
    tmdb_calls: int
    runtimes_found: int
    processed_at: str
    status: str = "processed"


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


def enrich_tmdb_runtime(
    config: IngestionConfig,
    *,
    dry_run: bool = False,
) -> RuntimeEnrichmentResult:
    """Fill runtime for Oscar nominees without an existing IMDb runtime match."""

    LOGGER.info("Starting TMDb runtime enrichment")
    source_path = config.bronze_data_dir / "oscar_best_picture_nominees.parquet"
    if not source_path.exists():
        raise FileNotFoundError(
            f"Bronze dataset not found: {source_path}. Run process-bronze first."
        )

    output_path = config.gold_data_dir / "oscar_best_picture_nominees_runtime.parquet"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = pd.read_parquet(source_path, engine="pyarrow")
    enriched = data.copy()
    if "runtime_minutes" not in enriched.columns:
        enriched["runtime_minutes"] = pd.NA
    if "runtime_source" not in enriched.columns:
        enriched["runtime_source"] = pd.NA
    if "tmdb_id" not in enriched.columns:
        enriched["tmdb_id"] = pd.NA

    movie_column = _find_column(enriched, candidates=("film", "movie", "title", "name"))
    year_column = _optional_column(
        enriched,
        candidates=("year_film", "year", "ceremony_year"),
    )
    tmdb_candidates = enriched["runtime_minutes"].isna()
    LOGGER.info(
        "Loaded bronze data: rows=%s tmdb_candidates=%s dry_run=%s",
        len(enriched),
        int(tmdb_candidates.sum()),
        dry_run,
    )

    tmdb_calls = 0
    runtimes_found = 0
    if not dry_run and tmdb_candidates.any():
        api_key = _load_secret(config.tmdb_api_key_env, config.tmdb_env_path)
        if not api_key:
            raise RuntimeError(
                f"TMDb API key not found. Set {config.tmdb_api_key_env} "
                f"in {config.tmdb_env_path} "
                "or export it as an environment variable before running enrichment."
            )

        client = TmdbRuntimeClient(
            api_key=api_key,
            cache_dir=config.tmdb_cache_dir,
            language=config.tmdb_language,
            request_interval_seconds=config.tmdb_request_interval_seconds,
        )
        candidates = enriched.loc[tmdb_candidates]
        for position, (index, row) in enumerate(candidates.iterrows(), start=1):
            title = str(row[movie_column]).strip()
            year = _parse_year(row[year_column]) if year_column else None
            LOGGER.info(
                "Fetching TMDb runtime %s/%s: title=%s year=%s",
                position,
                len(candidates),
                title,
                year,
            )
            result = client.get_runtime(title, year)
            tmdb_calls += int(result["api_calls"])
            runtime = result.get("runtime_minutes")
            if runtime:
                enriched.at[index, "runtime_minutes"] = runtime
                enriched.at[index, "runtime_source"] = "tmdb"
                enriched.at[index, "tmdb_id"] = result.get("tmdb_id")
                runtimes_found += 1
                LOGGER.info(
                    "Runtime found in TMDb: title=%s runtime_minutes=%s",
                    title,
                    runtime,
                )
            else:
                LOGGER.warning(
                    "Runtime not found in TMDb: title=%s year=%s",
                    title,
                    year,
                )

    if not dry_run:
        enriched.to_parquet(
            output_path, index=False, engine="pyarrow", compression="zstd"
        )
        LOGGER.info("Wrote enriched dataset: %s", output_path)
    else:
        LOGGER.info("Dry run finished without writing dataset: target=%s", output_path)

    return RuntimeEnrichmentResult(
        layer="gold",
        source_path=str(source_path),
        target_path=str(output_path),
        rows_read=len(data),
        rows_written=0 if dry_run else len(enriched),
        tmdb_candidates=int(tmdb_candidates.sum()),
        tmdb_calls=tmdb_calls,
        runtimes_found=runtimes_found,
        processed_at=datetime.now(UTC).isoformat(),
        status="dry-run" if dry_run else "processed",
    )


class TmdbRuntimeClient:
    """TMDb client focused on runtime enrichment with local response caching."""

    base_url = "https://api.themoviedb.org/3"

    def __init__(
        self,
        *,
        api_key: str,
        cache_dir: Path,
        language: str = "en-US",
        request_interval_seconds: float = 0.25,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.language = language
        self.request_interval_seconds = request_interval_seconds
        self.session = session or requests.Session()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_runtime(self, title: str, year: int | None) -> dict[str, Any]:
        cache_path = self.cache_dir / f"{_cache_key(title, year)}.json"
        if cache_path.exists():
            LOGGER.debug("Reading TMDb cache: %s", cache_path)
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if year and cached.get("runtime_minutes") is None:
                LOGGER.info(
                    "Retrying cached TMDb miss with fallback search: title=%s",
                    title,
                )
                payload = self._fetch_runtime_with_fallbacks(title, year)
                cache_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return payload
            cached["api_calls"] = 0
            cached["from_api"] = False
            return cached

        LOGGER.debug("TMDb cache miss: title=%s year=%s", title, year)
        payload = self._fetch_runtime_with_fallbacks(title, year)
        cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return payload

    def _fetch_runtime_with_fallbacks(
        self,
        title: str,
        year: int | None,
    ) -> dict[str, Any]:
        attempts: list[tuple[str, int | None, bool]] = [(title, year, False)]
        if year:
            attempts.append((title, None, False))
        attempts.extend((variant, None, True) for variant in _title_variants(title))

        api_calls = 0
        last_payload: dict[str, Any] | None = None
        for candidate_title, candidate_year, title_variant in attempts:
            payload = self._fetch_runtime(candidate_title, candidate_year)
            api_calls += int(payload["api_calls"])
            last_payload = payload
            if payload.get("runtime_minutes") is not None:
                payload["api_calls"] = api_calls
                payload["from_api"] = True
                payload["matched_without_year"] = (
                    candidate_year is None and year is not None
                )
                payload["matched_title_variant"] = title_variant
                payload["requested_title"] = title
                return payload

        fallback_payload = last_payload or {
            "title": title,
            "year": year,
            "runtime_minutes": None,
            "tmdb_id": None,
        }
        fallback_payload["api_calls"] = api_calls
        fallback_payload["from_api"] = True
        fallback_payload["requested_title"] = title
        return fallback_payload

    def _fetch_runtime(self, title: str, year: int | None) -> dict[str, Any]:
        search_params: dict[str, Any] = {
            "api_key": self.api_key,
            "query": title,
            "language": self.language,
            "include_adult": "false",
        }
        if year:
            search_params["year"] = year

        search_response = self.session.get(
            f"{self.base_url}/search/movie",
            params=search_params,
            timeout=30,
        )
        search_response.raise_for_status()
        self._sleep_between_requests()
        results = search_response.json().get("results", [])
        if not results:
            return {
                "title": title,
                "year": year,
                "runtime_minutes": None,
                "tmdb_id": None,
                "api_calls": 1,
            }

        tmdb_id = results[0]["id"]
        detail_response = self.session.get(
            f"{self.base_url}/movie/{tmdb_id}",
            params={"api_key": self.api_key, "language": self.language},
            timeout=30,
        )
        detail_response.raise_for_status()
        self._sleep_between_requests()
        details = detail_response.json()
        return {
            "title": title,
            "year": year,
            "runtime_minutes": details.get("runtime") or None,
            "tmdb_id": tmdb_id,
            "api_calls": 2,
        }

    def _sleep_between_requests(self) -> None:
        if self.request_interval_seconds > 0:
            time.sleep(self.request_interval_seconds)


def filter_best_picture_nominees(data: pd.DataFrame) -> pd.DataFrame:
    """Filter Oscar records to Best Picture nominees only."""

    category_column = _find_column(
        data,
        candidates=("category", "award", "award_category"),
        required_content="best",
    )
    movie_column = _find_column(data, candidates=("film", "movie", "title", "name"))

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
            or data[column]
            .fillna("")
            .astype(str)
            .str.lower()
            .str.contains(required_content)
            .any()
        ):
            return column

    candidate_list = ", ".join(candidates)
    raise ValueError(
        f"Could not find a compatible column. Expected one of: {candidate_list}. "
        f"Available columns: {', '.join(map(str, data.columns))}"
    )


def _optional_column(data: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    normalized_columns = {_normalize_column(column): column for column in data.columns}
    for candidate in candidates:
        column = normalized_columns.get(_normalize_column(candidate))
        if column:
            return column
    return None


def _parse_year(value: object) -> int | None:
    if pd.isna(value):
        return None
    match = re.search(r"\d{4}", str(value))
    return int(match.group(0)) if match else None


def _cache_key(title: str, year: int | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{normalized}-{year}" if year else normalized


def _title_variants(title: str) -> list[str]:
    possessive_match = re.search(r"'s\s+(.+)$", title)
    if not possessive_match:
        return []
    return [possessive_match.group(1).strip()]


def _load_secret(name: str, env_path: Path) -> str | None:
    return os.environ.get(name) or _load_dotenv_value(env_path, name)


def _load_dotenv_value(env_path: Path, name: str) -> str | None:
    if not env_path.exists():
        return None

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        if key.strip() != name:
            continue

        return _strip_env_quotes(value.strip())
    return None


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _normalize_column(column: object) -> str:
    return str(column).strip().lower().replace(" ", "_").replace("-", "_")
