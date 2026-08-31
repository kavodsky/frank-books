"""HTML → plain text. BeautifulSoup first, trafilatura if that is too thin."""

from __future__ import annotations

from pathlib import Path

import trafilatura
from bs4 import BeautifulSoup

from frank.domain.model.source import FetchedSource
from frank.infrastructure.sources.load import decode_bytes

HTML_HEADING = r"^# (.+)$"


def matches(location: str) -> bool:
    lower = location.lower().split("?", 1)[0]
    return lower.endswith(".html") or lower.endswith(".htm")


def parse(raw: bytes, location: str, default_lang: str) -> FetchedSource:
    html = decode_bytes(raw)
    soup = BeautifulSoup(html, "lxml")
    title = _title(soup, location)
    return FetchedSource(
        location=location,
        raw_bytes=raw,
        filename=_filename(location, "source.html"),
        suggested_slug=_stem(location),
        lang=default_lang,
        title=title,
        author="",
        license_note="",
        heading_pattern=HTML_HEADING,
        plain_text=extract_html_text(html),
    )


def extract_html_text(html: str) -> str:
    from_bs4 = extract_with_bs4(html)
    if _has_structure(from_bs4):
        return from_bs4
    from_traf = trafilatura.extract(html)
    if from_traf:
        return from_traf
    return from_bs4


def extract_with_bs4(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    chunks: list[str] = []
    for el in soup.find_all(["h1", "h2", "h3", "p"]):
        text = el.get_text(" ", strip=True)
        if text == "":
            continue
        if el.name in {"h1", "h2", "h3"}:
            chunks.append(f"# {text}")
        else:
            chunks.append(text)
    return "\n\n".join(chunks)


def _has_structure(text: str) -> bool:
    return "\n\n" in text or text.startswith("# ")


def _title(soup: BeautifulSoup, location: str) -> str:
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    heading = soup.find(["h1", "h2"])
    if heading:
        return heading.get_text(" ", strip=True)
    return _stem(location)


def _stem(location: str) -> str:
    name = Path(location.split("?", 1)[0]).stem
    return name or "book"


def _filename(location: str, fallback: str) -> str:
    name = Path(location.split("?", 1)[0]).name
    if name and "." in name:
        return name
    return fallback
