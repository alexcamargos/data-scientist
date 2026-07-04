"""Gold layer runtime enrichment for Oscar data."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

import pandas as pd

from cinematic_chronos.clients.tmdb import TmdbRuntimeClient
from cinematic_chronos.config import IngestionConfig
from cinematic_chronos.models import RuntimeEnrichmentResult
from cinematic_chronos.utils.columns import find_column, optional_column
from cinematic_chronos.utils.env import load_secret

LOGGER = logging.getLogger(__name__)


def enrich_tmdb_runtime(
    config: IngestionConfig,
    *,
    dry_run: bool = False,
) -> RuntimeEnrichmentResult:
    """Fill runtime for Oscar nominees without an existing IMDb runtime match.

    Args:
        config: Resolved ingestion configuration.
        dry_run: Whether to count TMDb candidates without calling the API or
            writing an output dataset.

    Returns:
        Runtime enrichment metadata.

    Raises:
        FileNotFoundError: If the bronze nominees dataset is missing.
        RuntimeError: If TMDb credentials are required but unavailable.
        ValueError: If required movie columns cannot be found.
    """

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

    movie_column = find_column(enriched, candidates=("film", "movie", "title", "name"))
    year_column = optional_column(
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
        api_key = load_secret(config.tmdb_api_key_env, config.tmdb_env_path)
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
        tmdb_calls, runtimes_found = _enrich_missing_runtimes(
            enriched,
            tmdb_candidates,
            client,
            movie_column,
            year_column,
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


def _enrich_missing_runtimes(
    enriched: pd.DataFrame,
    tmdb_candidates: pd.Series,
    client: TmdbRuntimeClient,
    movie_column: str,
    year_column: str | None,
) -> tuple[int, int]:
    """Fill missing runtime values in an enriched nominees DataFrame.

    Args:
        enriched: DataFrame to mutate with TMDb runtime fields.
        tmdb_candidates: Boolean mask identifying rows that need TMDb lookup.
        client: Runtime client used for TMDb lookups.
        movie_column: Column containing movie titles.
        year_column: Optional column containing release or ceremony years.

    Returns:
        Pair containing TMDb API call count and number of runtimes found.
    """

    tmdb_calls = 0
    runtimes_found = 0
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
            LOGGER.warning("Runtime not found in TMDb: title=%s year=%s", title, year)

    return tmdb_calls, runtimes_found


def _parse_year(value: object) -> int | None:
    """Parse the first four-digit year from a value.

    Args:
        value: Raw year-like value from a DataFrame cell.

    Returns:
        Parsed year when present.
    """

    if pd.isna(value):
        return None
    match = re.search(r"\d{4}", str(value))
    return int(match.group(0)) if match else None
