"""Content-addressed FrankRecord and scene-brief cache (roadmap 5.5)."""

from __future__ import annotations

from frank.domain.model.frank import FrankRecord
from frank.infrastructure.persistence.cache import CacheKey, StepCache


class StepGenerationCache:
    def __init__(self, cache: StepCache, slug: str) -> None:
        self._cache = cache
        self._slug = slug

    def get_records(self, key: str) -> tuple[FrankRecord, ...] | None:
        hit = self._cache.get(CacheKey(self._slug, key, "generate"))
        if hit is None:
            return None
        raw = hit.get("records")
        if not isinstance(raw, list):
            return None
        return tuple(FrankRecord.model_validate(item) for item in raw)

    def put_records(self, key: str, records: tuple[FrankRecord, ...]) -> None:
        payload = {
            "records": [item.model_dump(mode="json") for item in records],
        }
        self._cache.put(CacheKey(self._slug, key, "generate"), payload)

    def get_brief(self, key: str) -> str | None:
        hit = self._cache.get(CacheKey(self._slug, key, "scene_brief"))
        if hit is None:
            return None
        text = hit.get("summary_uk")
        return text if isinstance(text, str) else None

    def put_brief(self, key: str, brief: str) -> None:
        self._cache.put(CacheKey(self._slug, key, "scene_brief"), {"summary_uk": brief})
