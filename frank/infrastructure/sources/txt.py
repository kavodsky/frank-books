"""Plain-text source adapter."""

from __future__ import annotations

from pathlib import Path

from frank.domain.model.source import FetchedSource
from frank.infrastructure.sources.load import decode_bytes

TXT_HEADING = r"^(?:#\s+(.+)|(?:[0-9]+\.\s*)?(?:Kapitel|KAPITEL|Fejezet|FEJEZET)\b.*)$"


def matches(location: str) -> bool:
    return location.lower().split("?", 1)[0].endswith(".txt")


def parse(raw: bytes, location: str, default_lang: str) -> FetchedSource:
    text = decode_bytes(raw)
    stem = Path(location.split("?", 1)[0]).stem or "book"
    return FetchedSource(
        location=location,
        raw_bytes=raw,
        filename=Path(location).name or "source.txt",
        suggested_slug=stem,
        lang=default_lang,
        title=stem.replace("-", " "),
        author="",
        license_note="",
        heading_pattern=TXT_HEADING,
        plain_text=text,
    )
