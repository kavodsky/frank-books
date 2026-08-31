"""EPUB source adapter (ebooklib)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import ebooklib
from ebooklib import epub

from frank.domain.model.source import FetchedSource
from frank.infrastructure.sources.html import HTML_HEADING, extract_html_text


def matches(location: str) -> bool:
    return location.lower().split("?", 1)[0].endswith(".epub")


def parse(raw: bytes, location: str, default_lang: str) -> FetchedSource:
    book = epub.read_epub(BytesIO(raw))
    chunks = [
        extract_html_text(item.get_content().decode("utf-8", errors="replace"))
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
    ]
    title = book.get_metadata("DC", "title")
    authors = book.get_metadata("DC", "creator")
    stem = Path(location.split("?", 1)[0]).stem or "book"
    return FetchedSource(
        location=location,
        raw_bytes=raw,
        filename=Path(location).name or "source.epub",
        suggested_slug=stem,
        lang=default_lang,
        title=title[0][0] if title else stem,
        author=authors[0][0] if authors else "",
        license_note="",
        heading_pattern=HTML_HEADING,
        plain_text="\n\n".join(chunk for chunk in chunks if chunk.strip()),
    )
