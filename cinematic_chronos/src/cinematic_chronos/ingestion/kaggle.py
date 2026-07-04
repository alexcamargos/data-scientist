"""Kaggle dataset ingestion adapter."""

from __future__ import annotations

import importlib.util
import logging
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from cinematic_chronos.models import DownloadResult
from cinematic_chronos.storage import LocalRawStore

LOGGER = logging.getLogger(__name__)


class KaggleDatasetDownloader:
    """Downloads a Kaggle dataset through the configured Kaggle client.

    Attributes:
        python_executable: Python executable used to invoke ``python -m kaggle``.
    """

    def __init__(self, python_executable: str = sys.executable) -> None:
        """Initialize the downloader.

        Args:
            python_executable: Python executable used to invoke the Kaggle
                module when it is installed in the active environment.
        """

        self.python_executable = python_executable

    def download(
        self,
        store: LocalRawStore,
        dataset_slug: str,
        target_dir: str,
        *,
        unzip: bool = True,
        force: bool = False,
        dry_run: bool = False,
    ) -> DownloadResult:
        """Download a Kaggle dataset into the local raw store.

        Args:
            store: Local raw store used to resolve paths and record metadata.
            dataset_slug: Kaggle dataset slug in ``owner/dataset`` format.
            target_dir: Directory name under the Kaggle raw data root.
            unzip: Whether the Kaggle client should unzip downloaded files.
            force: Whether existing target files should be refreshed.
            dry_run: Whether to resolve metadata without calling Kaggle.

        Returns:
            Download metadata for the attempted extract operation.

        Raises:
            RuntimeError: If the Kaggle client is unavailable or the download
                command fails.
        """

        target_path = store.path_for("kaggle", target_dir)
        source = "kaggle.oscar_awards"
        if dry_run:
            LOGGER.info(
                "Dry run: resolved Kaggle dataset %s to %s",
                dataset_slug,
                target_path,
            )
            return _result(source, target_path, "dry-run", source_uri=dataset_slug)

        if target_path.exists() and any(target_path.iterdir()) and not force:
            LOGGER.info(
                "Skipping Kaggle download because %s already has files",
                target_path,
            )
            result = _result(
                source,
                target_path,
                "skipped",
                source_uri=dataset_slug,
                message=(
                    "Target directory already contains files. "
                    "Use --force to refresh it."
                ),
            )
            store.record(result)
            return result

        target_path.mkdir(parents=True, exist_ok=True)
        command = self._build_command(dataset_slug, target_path, unzip, force)
        LOGGER.info(
            "Starting Kaggle download: dataset=%s target=%s",
            dataset_slug,
            target_path,
        )
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as error:
            raise RuntimeError(_missing_kaggle_message()) from error
        except subprocess.CalledProcessError as error:
            details = (error.stderr or error.stdout or "").strip()
            raise RuntimeError(
                "Kaggle download failed. Check Kaggle credentials and dataset access. "
                f"Details: {details}"
            ) from error

        bytes_written = sum(
            file_path.stat().st_size
            for file_path in target_path.rglob("*")
            if file_path.is_file()
        )
        LOGGER.info("Finished Kaggle download: bytes_written=%s", bytes_written)
        result = _result(
            source,
            target_path,
            "downloaded",
            bytes_written=bytes_written,
            source_uri=dataset_slug,
            message=completed.stdout.strip() or None,
        )
        store.record(result)
        return result

    def _build_command(
        self,
        dataset_slug: str,
        target_path: Path,
        unzip: bool,
        force: bool,
    ) -> list[str]:
        """Build the Kaggle download command.

        Args:
            dataset_slug: Kaggle dataset slug in ``owner/dataset`` format.
            target_path: Directory where files should be downloaded.
            unzip: Whether to pass ``--unzip`` to the Kaggle client.
            force: Whether to pass ``--force`` to the Kaggle client.

        Returns:
            Command arguments suitable for ``subprocess.run``.

        Raises:
            RuntimeError: If no Kaggle client is available.
        """

        if importlib.util.find_spec("kaggle"):
            command = [self.python_executable, "-m", "kaggle"]
        elif shutil.which("kaggle"):
            command = ["kaggle"]
        else:
            raise RuntimeError(_missing_kaggle_message())

        command.extend(
            ["datasets", "download", "-d", dataset_slug, "-p", str(target_path)],
        )
        if unzip:
            command.append("--unzip")
        if force:
            command.append("--force")
        return command


def _result(
    source: str,
    target_path: Path,
    status: str,
    *,
    downloaded_at: str | None = None,
    bytes_written: int = 0,
    sha256: str | None = None,
    source_uri: str | None = None,
    message: str | None = None,
) -> DownloadResult:
    """Create standardized download metadata.

    Args:
        source: Logical source identifier.
        target_path: Path where data was or would be written.
        status: Operation status.
        downloaded_at: Optional ISO timestamp. Defaults to the current UTC time.
        bytes_written: Number of bytes written to disk.
        sha256: Optional content hash.
        source_uri: Optional upstream source URI.
        message: Optional human-readable details.

    Returns:
        Download metadata.
    """

    return DownloadResult(
        source=source,
        target_path=str(target_path),
        status=status,
        downloaded_at=downloaded_at or datetime.now(UTC).isoformat(),
        bytes_written=bytes_written,
        sha256=sha256,
        source_uri=source_uri,
        message=message,
    )


def _missing_kaggle_message() -> str:
    """Build the missing Kaggle client error message.

    Returns:
        Guidance for installing and configuring the Kaggle client.
    """

    return (
        "Kaggle client is not available. Install it in the project venv with "
        "`python -m pip install kaggle` and configure KAGGLE_USERNAME/KAGGLE_KEY "
        "or `%USERPROFILE%\\.kaggle\\kaggle.json`."
    )
