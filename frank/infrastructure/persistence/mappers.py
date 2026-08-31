"""Explicit row <-> domain conversions. Boring on purpose."""

from __future__ import annotations

from datetime import UTC, datetime

from frank.domain.errors import ErrorClass
from frank.domain.model.book import (
    Book,
    BookStatus,
    Chapter,
    Paragraph,
    ParagraphStatus,
)
from frank.domain.model.run import Run, RunStatus
from frank.infrastructure.persistence.tables import (
    BookRow,
    ChapterRow,
    ParagraphRow,
    RunRow,
)


def run_from_row(row: RunRow) -> Run:
    error_class = None if row.error_class is None else ErrorClass(row.error_class)
    return Run(
        id=row.id,
        book_id=row.book_id,
        started_at=_as_utc(row.started_at),
        ended_at=None if row.ended_at is None else _as_utc(row.ended_at),
        status=RunStatus(row.status),
        passages_done=row.passages_done,
        last_passage_id=row.last_passage_id,
        error_class=error_class,
        error_msg=row.error_msg,
    )


def row_from_run(run: Run) -> RunRow:
    return RunRow(
        id=run.id,
        book_id=run.book_id,
        started_at=run.started_at,
        ended_at=run.ended_at,
        status=run.status.value,
        passages_done=run.passages_done,
        last_passage_id=run.last_passage_id,
        error_class=None if run.error_class is None else run.error_class.value,
        error_msg=run.error_msg,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def book_from_row(row: BookRow) -> Book:
    return Book(
        id=row.id,
        slug=row.slug,
        lang=row.lang,
        title=row.title,
        author=row.author,
        source_url=row.source_url,
        license_note=row.license_note,
        status=BookStatus(row.status),
    )


def row_from_book(book: Book) -> BookRow:
    return BookRow(
        id=book.id,
        slug=book.slug,
        lang=book.lang,
        title=book.title,
        author=book.author,
        source_url=book.source_url,
        license_note=book.license_note,
        status=book.status.value,
    )


def chapter_from_row(row: ChapterRow) -> Chapter:
    return Chapter(
        id=row.id,
        book_id=row.book_id,
        index=row.index,
        title=row.title,
        summary_uk=row.summary_uk,
    )


def row_from_chapter(chapter: Chapter) -> ChapterRow:
    return ChapterRow(
        id=chapter.id,
        book_id=chapter.book_id,
        index=chapter.index,
        title=chapter.title,
        summary_uk=chapter.summary_uk,
    )


def paragraph_from_row(row: ParagraphRow) -> Paragraph:
    return Paragraph(
        id=row.id,
        chapter_id=row.chapter_id,
        passage_id=row.passage_id,
        index=row.index,
        raw_text=row.raw_text,
        hash=row.hash,
        status=ParagraphStatus(row.status),
    )


def row_from_paragraph(paragraph: Paragraph) -> ParagraphRow:
    return ParagraphRow(
        id=paragraph.id,
        chapter_id=paragraph.chapter_id,
        passage_id=paragraph.passage_id,
        index=paragraph.index,
        raw_text=paragraph.raw_text,
        hash=paragraph.hash,
        status=paragraph.status.value,
    )
