"""Pick a format adapter for a local file (ADR 0013)."""

from __future__ import annotations

from collections.abc import Callable

from frank.domain.errors import UnknownError
from frank.domain.model.source import FetchedSource
from frank.infrastructure.sources import epub, html, txt
from frank.infrastructure.sources.load import load_bytes

_Parser = Callable[[bytes, str, str], FetchedSource]
_ADAPTERS: tuple[tuple[Callable[[str], bool], _Parser], ...] = (
    (epub.matches, epub.parse),
    (html.matches, html.parse),
    (txt.matches, txt.parse),
)


class LocalFileFetcher:
    def __init__(self, default_lang: str) -> None:
        self._default_lang = default_lang

    def fetch(self, location: str) -> FetchedSource:
        raw, resolved = load_bytes(location)
        return _pick(resolved)(raw, resolved, self._default_lang)


def _pick(path: str) -> _Parser:
    for matches, parse in _ADAPTERS:
        if matches(path):
            return parse
    raise UnknownError(f"unsupported file type: {path}")
