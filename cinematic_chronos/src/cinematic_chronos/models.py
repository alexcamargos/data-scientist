"""Shared pipeline result models."""

from __future__ import annotations

from dataclasses import dataclass


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
