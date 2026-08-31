"""Content-addressed step cache. Unchanged input hash must hit."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CacheKey:
    book_slug: str
    paragraph_hash: str
    step_name: str


class StepCache:
    def __init__(self, root: Path) -> None:
        self._root = root

    def get(self, key: CacheKey) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, key: CacheKey, payload: dict[str, Any]) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    def _path(self, key: CacheKey) -> Path:
        return self._root / key.book_slug / key.paragraph_hash / f"{key.step_name}.json"
