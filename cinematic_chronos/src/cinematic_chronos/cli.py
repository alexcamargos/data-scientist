"""Command-line interface for Cinematic Chronos pipelines."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from cinematic_chronos.cli_logging import configure_cli_logging
from cinematic_chronos.config import DEFAULT_CONFIG, load_config
from cinematic_chronos.ingestion import ingest_all

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"extract", "process-bronze", "enrich-tmdb-runtime", "-h", "--help"}
    if not argv or argv[0] not in commands:
        argv.insert(0, "extract")

    parser = argparse.ArgumentParser(
        description="Run Cinematic Chronos data pipeline tasks.",
    )
    logging_parent = argparse.ArgumentParser(add_help=False)
    logging_parent.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default="INFO",
        help="Minimum log level emitted to stderr.",
    )
    subparsers = parser.add_subparsers(dest="command")

    extract_parser = subparsers.add_parser(
        "extract",
        help="Run raw Kaggle ingestion.",
        parents=[logging_parent],
    )
    extract_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to ingestion JSON configuration.",
    )
    extract_parser.add_argument(
        "--source",
        choices=("kaggle",),
        default="kaggle",
        help="Source to ingest.",
    )
    extract_parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh existing raw files.",
    )
    extract_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve targets without downloading files.",
    )

    bronze_parser = subparsers.add_parser(
        "process-bronze",
        help="Filter Kaggle Oscar data to Best Picture nominees.",
        parents=[logging_parent],
    )
    bronze_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to ingestion JSON configuration.",
    )

    tmdb_parser = subparsers.add_parser(
        "enrich-tmdb-runtime",
        help=(
            "Use TMDb to fill runtime only for Oscar movies without "
            "an IMDb runtime match."
        ),
        parents=[logging_parent],
    )
    tmdb_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to ingestion JSON configuration.",
    )
    tmdb_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many movies would require TMDb without calling the API.",
    )
    args = parser.parse_args(argv)
    configure_cli_logging(args.log_level)

    config = load_config(args.config)
    if args.command == "process-bronze":
        from cinematic_chronos.processing import process_bronze

        LOGGER.info("Running command: process-bronze")
        print(json.dumps(asdict(process_bronze(config)), ensure_ascii=False))
    elif args.command == "enrich-tmdb-runtime":
        from cinematic_chronos.processing import enrich_tmdb_runtime

        LOGGER.info("Running command: enrich-tmdb-runtime")
        print(
            json.dumps(
                asdict(enrich_tmdb_runtime(config, dry_run=args.dry_run)),
                ensure_ascii=False,
            )
        )
    else:
        LOGGER.info("Running command: extract")
        results = ingest_all(config, force=args.force, dry_run=args.dry_run)
        for result in results:
            print(json.dumps(asdict(result), ensure_ascii=False))
    return 0
