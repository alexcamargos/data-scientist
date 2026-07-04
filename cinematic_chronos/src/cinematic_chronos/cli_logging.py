"""Logging helpers for command-line entrypoints."""

from __future__ import annotations

import logging
import sys

DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_cli_logging(level_name: str = "INFO") -> None:
    """Configure stderr logging for interactive CLI progress tracking.

    Args:
        level_name: Logging level name accepted by the standard logging module.
    """

    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format=DEFAULT_LOG_FORMAT,
        stream=sys.stderr,
        force=True,
    )
