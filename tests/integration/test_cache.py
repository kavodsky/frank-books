"""Content-addressed cache: unchanged key returns the stored payload."""

from __future__ import annotations

import pytest

from frank.infrastructure.persistence.cache import CacheKey, StepCache


@pytest.mark.integration
def test_cache_round_trip_is_byte_identical(tmp_path) -> None:
    cache = StepCache(tmp_path)
    key = CacheKey(book_slug="minta", paragraph_hash="abc123", step_name="gloss")
    payload = {"lemma": "elolvas", "gloss_uk": "прочитати"}
    cache.put(key, payload)
    assert cache.get(key) == payload
    again = tmp_path / "minta" / "abc123" / "gloss.json"
    first = again.read_bytes()
    cache.put(key, payload)
    assert again.read_bytes() == first


@pytest.mark.integration
def test_cache_miss_returns_none(tmp_path) -> None:
    cache = StepCache(tmp_path)
    key = CacheKey(book_slug="minta", paragraph_hash="abc123", step_name="gloss")
    assert cache.get(key) is None
