"""Shared pipeline result models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadResult:
    """Metadata emitted after an extract operation.

    Attributes:
        source: Logical source identifier.
        target_path: Path where data was or would be written.
        status: Operation status.
        downloaded_at: ISO timestamp for the operation.
        bytes_written: Number of bytes written to disk.
        sha256: Optional content hash.
        source_uri: Optional upstream source URI.
        message: Optional human-readable details.
    """

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
    """Metadata emitted after a medallion processing step.

    Attributes:
        layer: Medallion layer written by the processing step.
        source_path: Input dataset path.
        target_path: Output dataset path.
        rows_read: Number of input rows read.
        rows_written: Number of output rows written.
        processed_at: ISO timestamp for the processing step.
        status: Operation status.
    """

    layer: str
    source_path: str
    target_path: str
    rows_read: int
    rows_written: int
    processed_at: str
    status: str = "processed"


@dataclass(frozen=True)
class RuntimeEnrichmentResult:
    """Metadata emitted after TMDb runtime enrichment.

    Attributes:
        layer: Medallion layer written by the enrichment step.
        source_path: Input dataset path.
        target_path: Output dataset path.
        rows_read: Number of input rows read.
        rows_written: Number of output rows written.
        tmdb_candidates: Number of rows eligible for TMDb lookup.
        tmdb_calls: Number of TMDb API calls made.
        runtimes_found: Number of runtimes filled from TMDb.
        processed_at: ISO timestamp for the enrichment step.
        status: Operation status.
    """

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
