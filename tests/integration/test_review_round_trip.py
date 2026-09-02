"""Export → edit → import preserves the termbase (roadmap 3.6)."""

from __future__ import annotations

import pytest

from frank.application.review_termbase import (
    ReviewPorts,
    approve_review,
    check_generation_gate,
    export_review,
)
from frank.domain.errors import SchemaInvalid, TermbaseNotApproved
from frank.domain.model.book import (
    Book,
    BookStatus,
    BookStructure,
    Chapter,
    Paragraph,
    ParagraphStatus,
)
from frank.domain.model.termbase import (
    AddressPair,
    Character,
    Gender,
    Term,
    TermKind,
    TvForm,
)
from frank.infrastructure.persistence.repositories import SqliteBookRepository
from frank.infrastructure.persistence.tables import create_book_db


def _structure() -> BookStructure:
    return BookStructure(
        book=Book(
            id="book",
            slug="review",
            lang="de",
            title="T",
            author="",
            source_url="file.txt",
            license_note="",
            status=BookStatus.INGESTED,
        ),
        chapters=(Chapter(id="book-c1", book_id="book", index=1, title="I"),),
        paragraphs=(
            Paragraph(
                id="book-c1-p1",
                chapter_id="book-c1",
                passage_id=None,
                index=1,
                raw_text="x",
                hash="h",
                status=ParagraphStatus.RAW,
            ),
        ),
    )


def _seed(repo: SqliteBookRepository) -> None:
    repo.replace_terms(
        "review",
        (
            Term(
                id="book-PERSON-oliver",
                book_id="book",
                kind=TermKind.PERSON,
                surface_forms=("Oliver",),
                lemma="oliver",
                translation_uk="Олівер",
            ),
            Term(
                id="book-PLACE-wien",
                book_id="book",
                kind=TermKind.PLACE,
                surface_forms=("Wien",),
                lemma="wien",
                translation_uk="Відень",
            ),
        ),
    )
    repo.replace_characters(
        "review",
        (
            Character(
                id="c-oliver",
                book_id="book",
                canonical_name="Oliver",
                translation_uk="Олівер",
                gender=Gender.UNKNOWN,
            ),
        ),
    )
    repo.replace_address_pairs(
        "review",
        (
            AddressPair(
                book_id="book",
                speaker_id="c-oliver",
                addressee_id="c-oliver",
                tv_form=TvForm.T,
            ),
        ),
    )


@pytest.mark.integration
def test_review_round_trip_approves_and_gate(tmp_path) -> None:
    repo = SqliteBookRepository(create_book_db(tmp_path / "book.db"))
    repo.save_structure(_structure())
    _seed(repo)
    ports = ReviewPorts(open_books=lambda _slug: repo, open_terms=lambda _slug: repo)
    with pytest.raises(TermbaseNotApproved):
        check_generation_gate(ports, "review")
    text = export_review(ports, "review").replace(
        'gender = "unknown"', 'gender = "male"', 1
    )
    report = approve_review(ports, "review", text)
    assert report.term_count == 2
    assert report.unknown_gender_count == 0
    terms = {item.lemma: item for item in repo.get_terms("review")}
    assert terms["oliver"].approved is True
    assert terms["wien"].approved is True
    assert terms["oliver"].translation_uk == "Олівер"
    assert repo.get_characters("review")[0].gender is Gender.MALE
    assert repo.get_address_pairs("review")[0].tv_form is TvForm.T
    check_generation_gate(ports, "review")


@pytest.mark.integration
def test_empty_approve_does_not_wipe(tmp_path) -> None:
    repo = SqliteBookRepository(create_book_db(tmp_path / "book.db"))
    repo.save_structure(_structure())
    _seed(repo)
    ports = ReviewPorts(open_books=lambda _slug: repo, open_terms=lambda _slug: repo)
    with pytest.raises(SchemaInvalid, match="empty"):
        approve_review(ports, "review", "  \n")
    assert repo.get_terms("review")[0].approved is False
    assert len(repo.get_characters("review")) == 1
