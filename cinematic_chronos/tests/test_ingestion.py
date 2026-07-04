import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
    TmdbRuntimeClient,
    enrich_tmdb_runtime,
    filter_best_picture_nominees,
    process_bronze,
)


class IngestionTestCase(unittest.TestCase):
    """Tests for Cinematic Chronos ingestion and processing workflows."""

    def test_load_config_resolves_project_paths(self) -> None:
        """Verify that project-relative config paths are resolved correctly."""

        config = load_config(Path("cinematic_chronos/config/ingestion.json"))

        self.assertEqual(
            config.raw_data_dir, Path("cinematic_chronos/data/raw").resolve()
        )
        self.assertEqual(
            config.manifest_path,
            Path("cinematic_chronos/data/raw/manifest.jsonl").resolve(),
        )
        self.assertEqual(
            config.bronze_data_dir, Path("cinematic_chronos/data/bronze").resolve()
        )
        self.assertEqual(
            config.silver_data_dir, Path("cinematic_chronos/data/silver").resolve()
        )
        self.assertEqual(
            config.gold_data_dir, Path("cinematic_chronos/data/gold").resolve()
        )
        self.assertEqual(config.kaggle_dataset_slug, "unanimad/the-oscar-award")
        self.assertEqual(config.tmdb_env_path, Path("cinematic_chronos/.env").resolve())
        self.assertEqual(config.tmdb_api_key_env, "TMDB_API_KEY")

    def test_local_raw_store_records_json_lines(self) -> None:
        """Verify that local raw store writes extract metadata as JSON Lines."""

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
        """Verify that Kaggle dry runs avoid external client requirements."""

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
        """Verify that Best Picture filtering drops unrelated award rows."""

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
        self.assertEqual(
            set(filtered["category"]), {"BEST PICTURE", "OUTSTANDING PICTURE"}
        )
        self.assertEqual(set(filtered["film"]), {"Anora", "Wings"})

    def test_process_bronze_writes_best_picture_parquet(self) -> None:
        """Verify that bronze processing writes filtered nominees to Parquet."""

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

    def test_tmdb_runtime_enrichment_dry_run_only_counts_missing_runtime(self) -> None:
        """Verify that TMDb dry run counts rows without calling the API."""

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            bronze_dir = tmp_path / "bronze"
            bronze_dir.mkdir()
            pd.DataFrame(
                [
                    {"film": "Moonlight", "year_film": 2016, "runtime_minutes": 111},
                    {"film": "Parasite", "year_film": 2019, "runtime_minutes": pd.NA},
                ]
            ).to_parquet(
                bronze_dir / "oscar_best_picture_nominees.parquet",
                index=False,
                engine="pyarrow",
            )

            config_path = tmp_path / "ingestion.json"
            config_path.write_text(
                json.dumps(
                    {
                        "raw_data_dir": str(tmp_path / "raw"),
                        "bronze_data_dir": str(bronze_dir),
                        "silver_data_dir": str(tmp_path / "silver"),
                        "gold_data_dir": str(tmp_path / "gold"),
                        "manifest_path": str(tmp_path / "raw" / "manifest.jsonl"),
                        "kaggle": {
                            "dataset_slug": "unanimad/the-oscar-award",
                            "target_dir": "oscar_awards",
                            "unzip": True,
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = enrich_tmdb_runtime(load_config(config_path), dry_run=True)

            self.assertEqual(result.status, "dry-run")
            self.assertEqual(result.tmdb_candidates, 1)
            self.assertEqual(result.tmdb_calls, 0)
            self.assertEqual(result.rows_written, 0)

    def test_tmdb_runtime_enrichment_reads_api_key_from_dotenv(self) -> None:
        """Verify that TMDb enrichment can load API keys from dotenv files."""

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            bronze_dir = tmp_path / "bronze"
            bronze_dir.mkdir()
            pd.DataFrame(
                [{"film": "Parasite", "year_film": 2019, "runtime_minutes": pd.NA}]
            ).to_parquet(
                bronze_dir / "oscar_best_picture_nominees.parquet",
                index=False,
                engine="pyarrow",
            )
            env_path = tmp_path / ".env"
            env_path.write_text(
                "TEST_TMDB_API_KEY_FROM_ENV_FILE='dotenv-token'\n", encoding="utf-8"
            )

            config_path = tmp_path / "ingestion.json"
            config_path.write_text(
                json.dumps(
                    {
                        "raw_data_dir": str(tmp_path / "raw"),
                        "bronze_data_dir": str(bronze_dir),
                        "silver_data_dir": str(tmp_path / "silver"),
                        "gold_data_dir": str(tmp_path / "gold"),
                        "manifest_path": str(tmp_path / "raw" / "manifest.jsonl"),
                        "kaggle": {
                            "dataset_slug": "unanimad/the-oscar-award",
                            "target_dir": "oscar_awards",
                            "unzip": True,
                        },
                        "tmdb": {
                            "env_path": str(env_path),
                            "api_key_env": "TEST_TMDB_API_KEY_FROM_ENV_FILE",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "cinematic_chronos.processing.runtime_enrichment.TmdbRuntimeClient",
                FakeRuntimeClient,
            ):
                result = enrich_tmdb_runtime(load_config(config_path))

            output = pd.read_parquet(result.target_path, engine="pyarrow")
            self.assertEqual(result.layer, "gold")
            self.assertEqual(FakeRuntimeClient.last_api_key, "dotenv-token")
            self.assertEqual(result.tmdb_calls, 2)
            self.assertEqual(output.loc[0, "runtime_minutes"], 132)

    def test_tmdb_runtime_client_caches_api_response(self) -> None:
        """Verify that TMDb client reuses cached runtime payloads."""

        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeTmdbSession()
            client = TmdbRuntimeClient(
                api_key="token",
                cache_dir=Path(temp_dir),
                request_interval_seconds=0,
                session=session,
            )

            first = client.get_runtime("Parasite", 2019)
            second = client.get_runtime("Parasite", 2019)

            self.assertEqual(first["runtime_minutes"], 132)
            self.assertEqual(second["runtime_minutes"], 132)
            self.assertTrue(Path(temp_dir).joinpath("2019-parasite.json").exists())
            self.assertTrue(first["from_api"])
            self.assertFalse(second["from_api"])
            self.assertEqual(first["api_calls"], 2)
            self.assertEqual(second["api_calls"], 0)
            self.assertEqual(session.call_count, 2)

    def test_tmdb_runtime_client_reads_and_migrates_legacy_cache_name(self) -> None:
        """Verify that title-year cache files are reused without API calls."""

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            legacy_path = cache_dir / "parasite-2019.json"
            current_path = cache_dir / "2019-parasite.json"
            legacy_path.write_text(
                json.dumps(
                    {
                        "title": "Parasite",
                        "year": 2019,
                        "runtime_minutes": 132,
                        "tmdb_id": 496243,
                        "api_calls": 2,
                    }
                ),
                encoding="utf-8",
            )
            session = FakeTmdbSession()
            client = TmdbRuntimeClient(
                api_key="token",
                cache_dir=cache_dir,
                request_interval_seconds=0,
                session=session,
            )

            result = client.get_runtime("Parasite", 2019)

            self.assertEqual(result["runtime_minutes"], 132)
            self.assertEqual(result["api_calls"], 0)
            self.assertFalse(result["from_api"])
            self.assertEqual(session.call_count, 0)
            self.assertFalse(legacy_path.exists())
            self.assertTrue(current_path.exists())

    def test_tmdb_runtime_client_retries_cached_miss_without_year(self) -> None:
        """Verify that cached misses are retried without year constraints."""

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            cache_dir.joinpath("the-broadway-melody-1928.json").write_text(
                json.dumps(
                    {
                        "title": "The Broadway Melody",
                        "year": 1928,
                        "runtime_minutes": None,
                        "tmdb_id": None,
                        "api_calls": 1,
                    }
                ),
                encoding="utf-8",
            )
            session = FakeTmdbFallbackSession()
            client = TmdbRuntimeClient(
                api_key="token",
                cache_dir=cache_dir,
                request_interval_seconds=0,
                session=session,
            )

            result = client.get_runtime("The Broadway Melody", 1928)

            self.assertEqual(result["runtime_minutes"], 100)
            self.assertTrue(result["matched_without_year"])
            self.assertEqual(result["api_calls"], 3)
            self.assertEqual(session.call_count, 3)
            self.assertFalse(
                cache_dir.joinpath("the-broadway-melody-1928.json").exists()
            )
            self.assertTrue(
                cache_dir.joinpath("1928-the-broadway-melody.json").exists()
            )

    def test_tmdb_runtime_client_retries_possessive_title_variant(self) -> None:
        """Verify that possessive titles are retried with a shorter variant."""

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            cache_dir.joinpath("meredith-willson-s-the-music-man-1962.json").write_text(
                json.dumps(
                    {
                        "title": "Meredith Willson's The Music Man",
                        "year": None,
                        "runtime_minutes": None,
                        "tmdb_id": None,
                        "api_calls": 1,
                    }
                ),
                encoding="utf-8",
            )
            session = FakeTmdbTitleVariantSession()
            client = TmdbRuntimeClient(
                api_key="token",
                cache_dir=cache_dir,
                request_interval_seconds=0,
                session=session,
            )

            result = client.get_runtime("Meredith Willson's The Music Man", 1962)

            self.assertEqual(result["runtime_minutes"], 151)
            self.assertTrue(result["matched_title_variant"])
            self.assertEqual(
                result["requested_title"], "Meredith Willson's The Music Man"
            )


class FakeTmdbResponse:
    """Minimal TMDb HTTP response double.

    Attributes:
        payload: JSON payload returned by ``json``.
    """

    def __init__(self, payload: dict) -> None:
        """Initialize the response double.

        Args:
            payload: JSON payload returned by ``json``.
        """

        self.payload = payload

    def raise_for_status(self) -> None:
        """Simulate a successful HTTP response status check."""

        return None

    def json(self) -> dict:
        """Return the configured JSON payload.

        Returns:
            Response payload.
        """

        return self.payload


class FakeTmdbSession:
    """TMDb session double that returns a successful runtime lookup.

    Attributes:
        call_count: Number of fake HTTP calls made.
    """

    def __init__(self) -> None:
        """Initialize the fake session call counter."""

        self.call_count = 0

    def get(self, url: str, *, params: dict, timeout: int) -> FakeTmdbResponse:
        """Return fake search or detail responses.

        Args:
            url: Requested TMDb URL.
            params: Request query parameters.
            timeout: Request timeout in seconds.

        Returns:
            Fake TMDb response.
        """

        self.call_count += 1
        if url.endswith("/search/movie"):
            return FakeTmdbResponse({"results": [{"id": 496243}]})
        return FakeTmdbResponse({"runtime": 132})


class FakeTmdbFallbackSession:
    """TMDb session double that requires a fallback without year.

    Attributes:
        call_count: Number of fake HTTP calls made.
    """

    def __init__(self) -> None:
        """Initialize the fake session call counter."""

        self.call_count = 0

    def get(self, url: str, *, params: dict, timeout: int) -> FakeTmdbResponse:
        """Return fake responses for year-constrained fallback testing.

        Args:
            url: Requested TMDb URL.
            params: Request query parameters.
            timeout: Request timeout in seconds.

        Returns:
            Fake TMDb response.
        """

        self.call_count += 1
        if url.endswith("/search/movie"):
            if "year" in params:
                return FakeTmdbResponse({"results": []})
            return FakeTmdbResponse({"results": [{"id": 65203}]})
        return FakeTmdbResponse({"runtime": 100})


class FakeTmdbTitleVariantSession:
    """TMDb session double that matches only a title variant.

    Attributes:
        call_count: Number of fake HTTP calls made.
    """

    def __init__(self) -> None:
        """Initialize the fake session call counter."""

        self.call_count = 0

    def get(self, url: str, *, params: dict, timeout: int) -> FakeTmdbResponse:
        """Return fake responses for title variant fallback testing.

        Args:
            url: Requested TMDb URL.
            params: Request query parameters.
            timeout: Request timeout in seconds.

        Returns:
            Fake TMDb response.
        """

        self.call_count += 1
        if url.endswith("/search/movie"):
            if params["query"] == "The Music Man":
                return FakeTmdbResponse({"results": [{"id": 5174}]})
            return FakeTmdbResponse({"results": []})
        return FakeTmdbResponse({"runtime": 151})


class FakeRuntimeClient:
    """Runtime client double used by enrichment workflow tests.

    Attributes:
        last_api_key: Last API key passed to a fake client instance.
    """

    last_api_key: str | None = None

    def __init__(
        self,
        *,
        api_key: str,
        cache_dir: Path,
        language: str,
        request_interval_seconds: float,
    ) -> None:
        """Initialize the fake runtime client.

        Args:
            api_key: API key passed by the enrichment workflow.
            cache_dir: Cache directory passed by the workflow.
            language: TMDb language passed by the workflow.
            request_interval_seconds: Request interval passed by the workflow.
        """

        self.last_api_key = api_key
        FakeRuntimeClient.last_api_key = api_key

    def get_runtime(self, title: str, year: int | None) -> dict:
        """Return a deterministic runtime payload.

        Args:
            title: Requested movie title.
            year: Requested movie year.

        Returns:
            Runtime payload used by enrichment tests.
        """

        return {
            "runtime_minutes": 132,
            "tmdb_id": 496243,
            "api_calls": 2,
        }


if __name__ == "__main__":
    unittest.main()
