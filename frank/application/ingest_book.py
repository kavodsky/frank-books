"""Ingest a source into per-book SQLite (roadmap 1.1–1.4)."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from frank.domain.model.book import BookStructure
from frank.domain.model.source import FetchedSource
from frank.domain.ports.repositories import BookRepository
from frank.domain.ports.sources import RawStore, SourceFetcher
from frank.domain.services.ingestion_report import (
    InspectReport,
    InspectRules,
    inspect_structure,
)
from frank.domain.services.normalization import NormalizeConfig, normalize_text
from frank.domain.services.structure import build_structure


class BookOverrides(BaseModel):
    model_config = ConfigDict(extra="ignore")

    heading_pattern: str | None = None
    whitelist_hashes: tuple[str, ...] = ()
    title: str | None = None
    author: str | None = None
    license_note: str | None = None
    source_url: str | None = None
    lang: str | None = None
    max_paragraph_chars: int | None = Field(default=None, ge=1)


@dataclass(frozen=True)
class IngestPorts:
    fetcher: SourceFetcher
    raw_store: RawStore
    open_books: Callable[[str], BookRepository]
    books_dir: Path


@dataclass(frozen=True)
class IngestRequest:
    location: str
    slug: str | None
    lang: str | None
    header_max_chars: int
    header_min_repeats: int
    max_paragraph_chars: int
    foreign_script_ratio: float


def ingest_book(ports: IngestPorts, request: IngestRequest) -> InspectReport:
    fetched = ports.fetcher.fetch(request.location)
    slug = request.slug or fetched.suggested_slug
    overrides = load_overrides(ports.books_dir / slug / "book.toml")
    fetched = _apply_overrides(fetched, overrides, request.lang)
    ports.raw_store.write(slug, fetched.filename, fetched.raw_bytes)
    _ensure_book_toml(ports.books_dir / slug / "book.toml", fetched)
    normalized = normalize_text(
        fetched.plain_text,
        NormalizeConfig(
            lang=fetched.lang,
            header_max_chars=request.header_max_chars,
            header_min_repeats=request.header_min_repeats,
        ),
    )
    structure = build_structure(fetched, normalized, slug)
    repo = ports.open_books(slug)
    repo.save_structure(structure)
    return _inspect_and_store(repo, structure, request, overrides)


def inspect_slug(
    ports: IngestPorts, slug: str, request: IngestRequest
) -> InspectReport:
    repo = ports.open_books(slug)
    structure = repo.get_structure(slug)
    overrides = load_overrides(ports.books_dir / slug / "book.toml")
    return _inspect_and_store(repo, structure, request, overrides)


def render_inspect_report(report: InspectReport) -> str:
    lines = [
        f"slug: {report.slug}",
        f"status: {report.status.value}",
        f"chapters: {report.chapter_count}",
        f"paragraphs: {report.paragraph_count}",
    ]
    if report.clean:
        lines.append("suspicious: none")
        return "\n".join(lines) + "\n"
    lines.append("suspicious:")
    for item in report.suspicions:
        lines.append(
            f"  - c{item.chapter_index} p{item.paragraph_index} "
            f"{item.kind.value} ({item.detail})"
        )
    return "\n".join(lines) + "\n"


def load_overrides(path: Path) -> BookOverrides:
    if not path.is_file():
        return BookOverrides()
    with path.open("rb") as fh:
        payload = tomllib.load(fh)
    return BookOverrides.model_validate(payload)


def _inspect_and_store(
    repo: BookRepository,
    structure: BookStructure,
    request: IngestRequest,
    overrides: BookOverrides,
) -> InspectReport:
    cap = overrides.max_paragraph_chars or request.max_paragraph_chars
    report = inspect_structure(
        structure,
        InspectRules(
            max_paragraph_chars=cap,
            foreign_script_ratio=request.foreign_script_ratio,
            whitelist_hashes=overrides.whitelist_hashes,
        ),
    )
    repo.set_status(structure.book.slug, report.status)
    return report


def _apply_overrides(
    fetched: FetchedSource,
    overrides: BookOverrides,
    lang: str | None,
) -> FetchedSource:
    chosen_lang = lang if lang is not None else overrides.lang
    mapping = {
        "heading_pattern": overrides.heading_pattern,
        "title": overrides.title,
        "author": overrides.author,
        "license_note": overrides.license_note or None,
        "location": overrides.source_url or None,
        "lang": chosen_lang,
    }
    updates = {key: value for key, value in mapping.items() if value}
    if not updates:
        return fetched
    return fetched.model_copy(update=updates)


def _ensure_book_toml(path: Path, fetched: FetchedSource) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            f'lang = "{fetched.lang}"\n'
            f"heading_pattern = {json.dumps(fetched.heading_pattern)}\n"
            'source_url = ""\n'
            'license_note = ""\n'
            "whitelist_hashes = []\n"
        ),
        encoding="utf-8",
    )
