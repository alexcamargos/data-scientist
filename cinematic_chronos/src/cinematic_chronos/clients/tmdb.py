"""TMDb API client for runtime enrichment."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)


class TmdbRuntimeClient:
    """TMDb client focused on runtime enrichment with local response caching.

    Attributes:
        base_url: Base URL for TMDb API requests.
        api_key: TMDb API key.
        cache_dir: Directory used to cache lookup payloads.
        language: TMDb language code used in requests.
        request_interval_seconds: Delay between TMDb API requests.
        session: HTTP session used for TMDb requests.
    """

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
        """Initialize the TMDb runtime client.

        Args:
            api_key: TMDb API key.
            cache_dir: Directory used to cache TMDb lookup payloads.
            language: TMDb language code used for search and detail calls.
            request_interval_seconds: Delay between TMDb requests.
            session: Optional HTTP session, primarily used by tests.
        """

        self.api_key = api_key
        self.cache_dir = cache_dir
        self.language = language
        self.request_interval_seconds = request_interval_seconds
        self.session = session or requests.Session()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_runtime(self, title: str, year: int | None) -> dict[str, Any]:
        """Get runtime metadata for one movie title.

        Args:
            title: Movie title to search on TMDb.
            year: Optional release year used to narrow search results.

        Returns:
            Runtime lookup payload containing runtime, TMDb id, call count, and
            cache/API metadata.
        """

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
        """Fetch runtime using progressively broader title/year fallbacks.

        Args:
            title: Original movie title.
            year: Optional release year.

        Returns:
            Runtime lookup payload with aggregate API call count.
        """

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
        """Fetch runtime from TMDb search and movie detail endpoints.

        Args:
            title: Candidate movie title.
            year: Optional candidate release year.

        Returns:
            Runtime lookup payload for the candidate title/year pair.

        Raises:
            requests.HTTPError: If TMDb returns an unsuccessful HTTP response.
        """

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
        """Pause between TMDb API requests when throttling is configured."""

        if self.request_interval_seconds > 0:
            time.sleep(self.request_interval_seconds)


def _cache_key(title: str, year: int | None) -> str:
    """Build a cache key for a title/year lookup.

    Args:
        title: Movie title.
        year: Optional release year.

    Returns:
        Filesystem-safe cache key.
    """

    normalized = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{normalized}-{year}" if year else normalized


def _title_variants(title: str) -> list[str]:
    """Build fallback title variants for possessive titles.

    Args:
        title: Original movie title.

    Returns:
        Candidate title variants.
    """

    possessive_match = re.search(r"'s\s+(.+)$", title)
    if not possessive_match:
        return []
    return [possessive_match.group(1).strip()]
