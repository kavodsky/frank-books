"""Concrete repositories. SQLAlchemy sessions stay inside this module."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from frank.domain.errors import DbError, FrankError
from frank.domain.model.book import BookStatus, BookStructure
from frank.domain.model.run import Run, RunFailure, RunStatus, RunTally
from frank.infrastructure.persistence.mappers import (
    book_from_row,
    chapter_from_row,
    paragraph_from_row,
    row_from_book,
    row_from_chapter,
    row_from_paragraph,
    row_from_run,
    run_from_row,
)
from frank.infrastructure.persistence.tables import (
    BookRow,
    ChapterRow,
    ParagraphRow,
    RunRow,
)


class SqliteRunRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def start(self, book_id: str) -> Run:
        run = Run(
            id=str(uuid4()),
            book_id=book_id,
            started_at=datetime.now(UTC),
            ended_at=None,
            status=RunStatus.RUNNING,
            passages_done=0,
            last_passage_id=None,
            error_class=None,
            error_msg=None,
        )
        try:
            with Session(self._engine) as session:
                session.add(row_from_run(run))
                session.commit()
        except Exception as exc:
            raise DbError(str(exc)) from exc
        return run

    def record_success(self, tally: RunTally) -> Run:
        return self._finish(tally, RunStatus.COMPLETED, error=None)

    def record_failure(self, failure: RunFailure) -> Run:
        return self._finish(failure.tally, RunStatus.FAILED, error=failure.error)

    def get(self, run_id: str) -> Run:
        with Session(self._engine) as session:
            row = session.get(RunRow, run_id)
            if row is None:
                raise DbError(f"run not found: {run_id}")
            return run_from_row(row)

    def _finish(
        self,
        tally: RunTally,
        status: RunStatus,
        error: FrankError | None,
    ) -> Run:
        with Session(self._engine) as session:
            row = session.get(RunRow, tally.run_id)
            if row is None:
                raise DbError(f"run not found: {tally.run_id}")
            _apply_finish(row, tally, status, error)
            session.commit()
            session.refresh(row)
            return run_from_row(row)


def _apply_finish(
    row: RunRow,
    tally: RunTally,
    status: RunStatus,
    error: FrankError | None,
) -> None:
    row.ended_at = datetime.now(UTC)
    row.status = status.value
    row.passages_done = tally.passages_done
    row.last_passage_id = tally.last_passage_id
    if error is None:
        row.error_class = None
        row.error_msg = None
        return
    row.error_class = error.error_class.value
    row.error_msg = error.message


class SqliteBookRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save_structure(self, structure: BookStructure) -> None:
        with Session(self._engine) as session:
            _wipe_book(session, structure.book.slug)
            session.add(row_from_book(structure.book))
            session.add_all([row_from_chapter(ch) for ch in structure.chapters])
            session.add_all([row_from_paragraph(p) for p in structure.paragraphs])
            session.commit()

    def get_structure(self, slug: str) -> BookStructure:
        with Session(self._engine) as session:
            book_row = session.scalar(select(BookRow).where(BookRow.slug == slug))
            if book_row is None:
                raise DbError(f"book not found: {slug}")
            chapter_rows = session.scalars(
                select(ChapterRow)
                .where(ChapterRow.book_id == book_row.id)
                .order_by(ChapterRow.index)
            ).all()
            paragraph_rows = session.scalars(
                select(ParagraphRow)
                .join(ChapterRow, ParagraphRow.chapter_id == ChapterRow.id)
                .where(ChapterRow.book_id == book_row.id)
                .order_by(ChapterRow.index, ParagraphRow.index)
            ).all()
            return BookStructure(
                book=book_from_row(book_row),
                chapters=tuple(chapter_from_row(row) for row in chapter_rows),
                paragraphs=tuple(paragraph_from_row(row) for row in paragraph_rows),
            )

    def set_status(self, slug: str, status: BookStatus) -> None:
        with Session(self._engine) as session:
            book_row = session.scalar(select(BookRow).where(BookRow.slug == slug))
            if book_row is None:
                raise DbError(f"book not found: {slug}")
            book_row.status = status.value
            session.commit()


def _wipe_book(session: Session, slug: str) -> None:
    book = session.scalar(select(BookRow).where(BookRow.slug == slug))
    if book is None:
        return
    chapter_ids = session.scalars(
        select(ChapterRow.id).where(ChapterRow.book_id == book.id)
    ).all()
    if chapter_ids:
        session.execute(
            delete(ParagraphRow).where(ParagraphRow.chapter_id.in_(chapter_ids))
        )
        session.execute(delete(ChapterRow).where(ChapterRow.book_id == book.id))
    session.execute(delete(BookRow).where(BookRow.id == book.id))
