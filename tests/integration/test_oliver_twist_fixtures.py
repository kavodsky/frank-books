"""Oliver Twist excerpts ingest as two chapters (Phase 2 fixture)."""

from __future__ import annotations

from pathlib import Path

import pytest

from frank.application.ingest_book import IngestPorts, IngestRequest, ingest_book
from frank.infrastructure.persistence.repositories import SqliteBookRepository
from frank.infrastructure.persistence.tables import create_book_db
from frank.infrastructure.sources.fetch import LocalFileFetcher
from frank.infrastructure.sources.raw_store import FilesystemRawStore

CHAPTERS = Path(__file__).resolve().parents[1] / "fixtures" / "chapters"


def _ports(tmp_path: Path, lang: str) -> IngestPorts:
    return IngestPorts(
        fetcher=LocalFileFetcher(lang),
        raw_store=FilesystemRawStore(tmp_path),
        open_books=lambda slug: SqliteBookRepository(
            create_book_db(tmp_path / slug / "book.db")
        ),
        books_dir=tmp_path,
    )


def _request(path: Path, slug: str, lang: str) -> IngestRequest:
    return IngestRequest(
        location=str(path),
        slug=slug,
        lang=lang,
        header_max_chars=60,
        header_min_repeats=3,
        max_paragraph_chars=1500,
        foreign_script_ratio=0.08,
    )


@pytest.mark.integration
def test_oliver_twist_excerpts_ingest_two_chapters(tmp_path) -> None:
    de = ingest_book(
        _ports(tmp_path, "de"),
        _request(CHAPTERS / "oliver_twist_de.txt", "oliver-de", "de"),
    )
    hu = ingest_book(
        _ports(tmp_path, "hu"),
        _request(CHAPTERS / "oliver_twist_hu.txt", "oliver-hu", "hu"),
    )
    repo_de = SqliteBookRepository(create_book_db(tmp_path / "oliver-de" / "book.db"))
    repo_hu = SqliteBookRepository(create_book_db(tmp_path / "oliver-hu" / "book.db"))
    de_book = repo_de.get_structure("oliver-de")
    hu_book = repo_hu.get_structure("oliver-hu")
    de_text = " ".join(p.raw_text for p in de_book.paragraphs)
    hu_text = " ".join(p.raw_text for p in hu_book.paragraphs)
    assert de.clean and de.chapter_count == 2
    assert hu.clean and hu.chapter_count == 2
    assert [ch.title for ch in de_book.chapters] == ["1. Kapitel", "2. Kapitel"]
    assert [ch.title for ch in hu_book.chapters] == ["Első fejezet", "Második fejezet"]
    assert "ich möchte noch ein wenig" in de_text
    assert "Kérek még egy kicsit" in hu_text
