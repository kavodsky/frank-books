"""Local-file ingest: txt/html/epub, idempotent re-run (roadmap 1.1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from ebooklib import epub

from frank.application.ingest_book import IngestPorts, IngestRequest, ingest_book
from frank.domain.errors import UnknownError
from frank.domain.model.book import BookStatus
from frank.infrastructure.persistence.repositories import SqliteBookRepository
from frank.infrastructure.persistence.tables import create_book_db
from frank.infrastructure.sources.fetch import LocalFileFetcher
from frank.infrastructure.sources.raw_store import FilesystemRawStore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sources"


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
def test_ingest_txt_html_and_epub(tmp_path) -> None:
    hu = ingest_book(
        _ports(tmp_path, "hu"),
        _request(FIXTURES / "sample.txt", "hu-txt", "hu"),
    )
    de = ingest_book(
        _ports(tmp_path, "de"),
        _request(FIXTURES / "sample_de.html", "de-html", "de"),
    )
    hu_html = ingest_book(
        _ports(tmp_path, "hu"),
        _request(FIXTURES / "sample_hu.html", "hu-html", "hu"),
    )
    epub_path = _write_epub(tmp_path / "probe.epub")
    book = ingest_book(
        _ports(tmp_path, "de"),
        _request(epub_path, "de-epub", "de"),
    )
    assert hu.clean and hu.chapter_count == 2
    assert de.clean and de.chapter_count == 2
    assert hu_html.clean and hu_html.chapter_count == 2
    assert book.clean and book.chapter_count >= 1
    assert (tmp_path / "hu-txt" / "raw").is_dir()


@pytest.mark.integration
def test_reingest_is_idempotent(tmp_path) -> None:
    ports = _ports(tmp_path, "hu")
    request = _request(FIXTURES / "sample.txt", "same", "hu")
    first = ingest_book(ports, request)
    repo = SqliteBookRepository(create_book_db(tmp_path / "same" / "book.db"))
    hashes = tuple(p.hash for p in repo.get_structure("same").paragraphs)
    second = ingest_book(ports, request)
    again = tuple(p.hash for p in repo.get_structure("same").paragraphs)
    assert first.paragraph_count == second.paragraph_count
    assert hashes == again
    assert repo.get_structure("same").book.status is BookStatus.INGESTED


@pytest.mark.integration
def test_url_and_unknown_type_are_rejected(tmp_path) -> None:
    ports = _ports(tmp_path, "hu")
    with pytest.raises(UnknownError):
        ingest_book(ports, _request(Path("https://mek.oszk.hu/x"), "no", "hu"))
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(UnknownError):
        ingest_book(ports, _request(pdf, "pdf", "hu"))


def _write_epub(path: Path) -> Path:
    book = epub.EpubBook()
    book.set_title("Probe")
    chapter = epub.EpubHtml(title="Kap", file_name="chap.xhtml", lang="de")
    chapter.content = "<h1>Kapitel</h1><p>Hallo Welt.</p>"
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    book.toc = [chapter]
    epub.write_epub(str(path), book)
    return path
