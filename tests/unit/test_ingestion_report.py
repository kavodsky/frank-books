"""Ingestion sanity report (roadmap 1.4)."""

from __future__ import annotations

import pytest

from frank.domain.model.book import (
    Book,
    BookStatus,
    BookStructure,
    Chapter,
    Paragraph,
    ParagraphStatus,
)
from frank.domain.services.ingestion_report import (
    InspectRules,
    SuspicionKind,
    inspect_structure,
)


def _structure(*texts: str) -> BookStructure:
    book = Book(
        id="s",
        slug="s",
        lang="de",
        title="T",
        author="",
        source_url="file.txt",
        license_note="",
        status=BookStatus.NEEDS_REVIEW,
    )
    chapter = Chapter(id="s-c1", book_id="s", index=1, title="K")
    paragraphs = tuple(
        Paragraph(
            id=f"s-c1-p{i}",
            chapter_id="s-c1",
            passage_id=None,
            index=i,
            raw_text=text,
            hash=f"h{i}",
            status=ParagraphStatus.RAW,
        )
        for i, text in enumerate(texts, start=1)
    )
    return BookStructure(book=book, chapters=(chapter,), paragraphs=paragraphs)


@pytest.mark.unit
def test_flags_overlong_markup_and_cyrillic() -> None:
    rules = InspectRules(
        max_paragraph_chars=20,
        foreign_script_ratio=0.08,
        whitelist_hashes=(),
    )
    report = inspect_structure(
        _structure("a" * 21, "<p>hallo</p>", "Це майже все кирилиця тут"),
        rules,
    )
    kinds = {item.kind for item in report.suspicions}
    assert SuspicionKind.TOO_LONG in kinds
    assert SuspicionKind.MARKUP in kinds
    assert SuspicionKind.FOREIGN_SCRIPT in kinds
    assert report.clean is False


@pytest.mark.unit
def test_whitelist_skips_hash() -> None:
    rules = InspectRules(
        max_paragraph_chars=20,
        foreign_script_ratio=0.08,
        whitelist_hashes=("h1",),
    )
    report = inspect_structure(_structure("a" * 99), rules)
    assert report.clean is True
    assert report.status is BookStatus.INGESTED
