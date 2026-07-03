import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cinematic_chronos.ingestion import (
    KaggleDatasetDownloader,
    LocalRawStore,
    load_config,
)
from cinematic_chronos.processing import (
    filter_best_picture_nominees,
    process_bronze,
)


class IngestionTestCase(unittest.TestCase):
    def test_load_config_resolves_project_paths(self) -> None:
        config = load_config(Path("cinematic_chronos/config/ingestion.json"))

        self.assertEqual(config.raw_data_dir, Path("cinematic_chronos/data/raw").resolve())
        self.assertEqual(
            config.manifest_path,
            Path("cinematic_chronos/data/raw/manifest.jsonl").resolve(),
        )
        self.assertEqual(config.bronze_data_dir, Path("cinematic_chronos/data/bronze").resolve())
        self.assertEqual(config.kaggle_dataset_slug, "unanimad/the-oscar-award")

    def test_local_raw_store_records_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            store = LocalRawStore(tmp_path / "raw", tmp_path / "raw" / "manifest.jsonl")
            result = KaggleDatasetDownloader().download(
                store,
                "owner/dataset",
                "oscars",
                dry_run=True,
            )
            store.record(result)

            manifest = tmp_path / "raw" / "manifest.jsonl"
            self.assertTrue(manifest.exists())
            self.assertIn('"status": "dry-run"', manifest.read_text(encoding="utf-8"))

    def test_kaggle_dry_run_does_not_require_client(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            store = LocalRawStore(tmp_path / "raw", tmp_path / "raw" / "manifest.jsonl")

            result = KaggleDatasetDownloader().download(
                store,
                "owner/dataset",
                "oscars",
                dry_run=True,
            )

            self.assertEqual(result.status, "dry-run")
            self.assertEqual(result.source, "kaggle.oscar_awards")
            self.assertEqual(result.source_uri, "owner/dataset")

    def test_filter_best_picture_nominees_keeps_only_best_picture(self) -> None:
        data = pd.DataFrame(
            [
                {
                    "year_film": 2024,
                    "category": "BEST PICTURE",
                    "film": "Anora",
                    "winner": True,
                },
                {
                    "year_film": 2024,
                    "category": "ACTOR IN A LEADING ROLE",
                    "film": "The Brutalist",
                    "winner": False,
                },
                {
                    "year_film": 1928,
                    "category": "OUTSTANDING PICTURE",
                    "film": "Wings",
                    "winner": True,
                },
            ]
        )

        filtered = filter_best_picture_nominees(data)

        self.assertEqual(len(filtered), 2)
        self.assertEqual(set(filtered["category"]), {"BEST PICTURE", "OUTSTANDING PICTURE"})
        self.assertEqual(set(filtered["film"]), {"Anora", "Wings"})

    def test_process_bronze_writes_best_picture_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            raw_dir = tmp_path / "raw"
            raw_kaggle_dir = raw_dir / "kaggle" / "oscar_awards"
            raw_kaggle_dir.mkdir(parents=True)
            pd.DataFrame(
                [
                    {"category": "BEST PICTURE", "film": "Moonlight", "winner": True},
                    {"category": "DIRECTING", "film": "La La Land", "winner": False},
                ]
            ).to_csv(raw_kaggle_dir / "the_oscar_award.csv", index=False)

            config_path = tmp_path / "ingestion.json"
            config_path.write_text(
                json.dumps(
                    {
                        "raw_data_dir": str(raw_dir),
                        "bronze_data_dir": str(tmp_path / "bronze"),
                        "manifest_path": str(raw_dir / "manifest.jsonl"),
                        "kaggle": {
                            "dataset_slug": "unanimad/the-oscar-award",
                            "target_dir": "oscar_awards",
                            "unzip": True,
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = process_bronze(load_config(config_path))
            output = pd.read_parquet(result.target_path, engine="pyarrow")

            self.assertEqual(result.layer, "bronze")
            self.assertTrue(result.target_path.endswith(".parquet"))
            self.assertEqual(result.rows_read, 2)
            self.assertEqual(result.rows_written, 1)
            self.assertEqual(output.loc[0, "film"], "Moonlight")


if __name__ == "__main__":
    unittest.main()
