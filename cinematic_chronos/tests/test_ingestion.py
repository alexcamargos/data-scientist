import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cinematic_chronos.ingestion import KaggleDatasetDownloader, LocalRawStore, load_config


class IngestionTestCase(unittest.TestCase):
    def test_load_config_resolves_project_paths(self) -> None:
        config = load_config(Path("cinematic_chronos/config/ingestion.json"))

        self.assertEqual(config.raw_data_dir, Path("cinematic_chronos/data/raw").resolve())
        self.assertEqual(
            config.manifest_path,
            Path("cinematic_chronos/data/raw/manifest.jsonl").resolve(),
        )
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


if __name__ == "__main__":
    unittest.main()
