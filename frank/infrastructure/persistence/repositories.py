"""Concrete repositories. SQLAlchemy sessions stay inside this module."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from frank.domain.errors import DbError, FrankError
from frank.domain.model.annotation import Annotation, GlossDecision, SenseUnit, Token
from frank.domain.model.book import BookStatus, BookStructure, Sentence
from frank.domain.model.lemma import LemmaOverride
from frank.domain.model.reunion import VerbParticle
from frank.domain.model.run import Run, RunFailure, RunStatus, RunTally
from frank.infrastructure.persistence.mappers import (
    book_from_row,
    chapter_from_row,
    gloss_decision_from_row,
    override_from_row,
    paragraph_from_row,
    particle_from_row,
    row_from_book,
    row_from_chapter,
    row_from_gloss_decision,
    row_from_override,
    row_from_paragraph,
    row_from_particle,
    row_from_run,
    row_from_sense_unit,
    row_from_sentence,
    row_from_token,
    run_from_row,
    sense_unit_from_row,
    sentence_from_row,
    token_from_row,
)
from frank.infrastructure.persistence.tables import (
    BookRow,
    ChapterRow,
    GlossPlanRow,
    LemmaOverrideRow,
    ParagraphRow,
    RunRow,
    SenseUnitRow,
    SentenceRow,
    TokenRow,
    VerbParticleRow,
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

    def replace_annotation(self, slug: str, annotation: Annotation) -> None:
        with Session(self._engine) as session:
            book_id = _book_id(session, slug)
            _delete_sentences(session, book_id)
            session.add_all([row_from_sentence(item) for item in annotation.sentences])
            session.add_all([row_from_token(item) for item in annotation.tokens])
            session.add_all([row_from_particle(item) for item in annotation.particles])
            session.add_all(
                [row_from_sense_unit(item) for item in annotation.sense_units]
            )
            session.add_all(
                [row_from_gloss_decision(item) for item in annotation.gloss_plan]
            )
            session.commit()

    def get_sentences(self, slug: str) -> tuple[Sentence, ...]:
        with Session(self._engine) as session:
            book_id = _book_id(session, slug)
            rows = session.scalars(
                select(SentenceRow)
                .join(ParagraphRow, SentenceRow.paragraph_id == ParagraphRow.id)
                .join(ChapterRow, ParagraphRow.chapter_id == ChapterRow.id)
                .where(ChapterRow.book_id == book_id)
                .order_by(ChapterRow.index, ParagraphRow.index, SentenceRow.index)
            ).all()
            return tuple(sentence_from_row(row) for row in rows)

    def get_tokens(self, slug: str) -> tuple[Token, ...]:
        with Session(self._engine) as session:
            book_id = _book_id(session, slug)
            rows = session.scalars(
                select(TokenRow)
                .join(SentenceRow, TokenRow.sentence_id == SentenceRow.id)
                .join(ParagraphRow, SentenceRow.paragraph_id == ParagraphRow.id)
                .join(ChapterRow, ParagraphRow.chapter_id == ChapterRow.id)
                .where(ChapterRow.book_id == book_id)
                .order_by(
                    ChapterRow.index,
                    ParagraphRow.index,
                    SentenceRow.index,
                    TokenRow.index,
                )
            ).all()
            return tuple(token_from_row(row) for row in rows)

    def get_particles(self, slug: str) -> tuple[VerbParticle, ...]:
        with Session(self._engine) as session:
            book_id = _book_id(session, slug)
            rows = session.scalars(
                select(VerbParticleRow)
                .join(SentenceRow, VerbParticleRow.sentence_id == SentenceRow.id)
                .join(ParagraphRow, SentenceRow.paragraph_id == ParagraphRow.id)
                .join(ChapterRow, ParagraphRow.chapter_id == ChapterRow.id)
                .where(ChapterRow.book_id == book_id)
                .order_by(SentenceRow.index, VerbParticleRow.particle_token_id)
            ).all()
            return tuple(particle_from_row(row) for row in rows)

    def get_sense_units(self, slug: str) -> tuple[SenseUnit, ...]:
        with Session(self._engine) as session:
            book_id = _book_id(session, slug)
            rows = session.scalars(
                select(SenseUnitRow)
                .join(SentenceRow, SenseUnitRow.sentence_id == SentenceRow.id)
                .join(ParagraphRow, SentenceRow.paragraph_id == ParagraphRow.id)
                .join(ChapterRow, ParagraphRow.chapter_id == ChapterRow.id)
                .where(ChapterRow.book_id == book_id)
                .order_by(
                    ChapterRow.index,
                    ParagraphRow.index,
                    SentenceRow.index,
                    SenseUnitRow.index,
                )
            ).all()
            return tuple(sense_unit_from_row(row) for row in rows)

    def get_gloss_plan(self, slug: str) -> tuple[GlossDecision, ...]:
        with Session(self._engine) as session:
            book_id = _book_id(session, slug)
            rows = session.scalars(
                select(GlossPlanRow)
                .join(TokenRow, GlossPlanRow.token_id == TokenRow.id)
                .join(SentenceRow, TokenRow.sentence_id == SentenceRow.id)
                .join(ParagraphRow, SentenceRow.paragraph_id == ParagraphRow.id)
                .join(ChapterRow, ParagraphRow.chapter_id == ChapterRow.id)
                .where(ChapterRow.book_id == book_id)
                .order_by(
                    ChapterRow.index,
                    ParagraphRow.index,
                    SentenceRow.index,
                    TokenRow.index,
                )
            ).all()
            return tuple(gloss_decision_from_row(row) for row in rows)

    def replace_overrides(
        self, slug: str, overrides: tuple[LemmaOverride, ...]
    ) -> None:
        with Session(self._engine) as session:
            _book_id(session, slug)
            session.execute(delete(LemmaOverrideRow))
            session.add_all([row_from_override(item) for item in overrides])
            session.commit()

    def get_overrides(self, slug: str) -> tuple[LemmaOverride, ...]:
        with Session(self._engine) as session:
            _book_id(session, slug)
            rows = session.scalars(
                select(LemmaOverrideRow).order_by(
                    LemmaOverrideRow.surface, LemmaOverrideRow.upos
                )
            ).all()
            return tuple(override_from_row(row) for row in rows)


def _wipe_book(session: Session, slug: str) -> None:
    book = session.scalar(select(BookRow).where(BookRow.slug == slug))
    if book is None:
        return
    _delete_sentences(session, book.id)
    session.execute(delete(LemmaOverrideRow))
    chapter_ids = session.scalars(
        select(ChapterRow.id).where(ChapterRow.book_id == book.id)
    ).all()
    if chapter_ids:
        session.execute(
            delete(ParagraphRow).where(ParagraphRow.chapter_id.in_(chapter_ids))
        )
        session.execute(delete(ChapterRow).where(ChapterRow.book_id == book.id))
    session.execute(delete(BookRow).where(BookRow.id == book.id))


def _book_id(session: Session, slug: str) -> str:
    book = session.scalar(select(BookRow).where(BookRow.slug == slug))
    if book is None:
        raise DbError(f"book not found: {slug}")
    return book.id


def _delete_sentences(session: Session, book_id: str) -> None:
    paragraph_ids = session.scalars(
        select(ParagraphRow.id)
        .join(ChapterRow, ParagraphRow.chapter_id == ChapterRow.id)
        .where(ChapterRow.book_id == book_id)
    ).all()
    if not paragraph_ids:
        return
    sentence_ids = session.scalars(
        select(SentenceRow.id).where(SentenceRow.paragraph_id.in_(paragraph_ids))
    ).all()
    if not sentence_ids:
        return
    token_ids = session.scalars(
        select(TokenRow.id).where(TokenRow.sentence_id.in_(sentence_ids))
    ).all()
    if token_ids:
        session.execute(
            delete(GlossPlanRow).where(GlossPlanRow.token_id.in_(token_ids))
        )
    session.execute(
        delete(SenseUnitRow).where(SenseUnitRow.sentence_id.in_(sentence_ids))
    )
    session.execute(
        delete(VerbParticleRow).where(VerbParticleRow.sentence_id.in_(sentence_ids))
    )
    session.execute(delete(TokenRow).where(TokenRow.sentence_id.in_(sentence_ids)))
    session.execute(delete(SentenceRow).where(SentenceRow.id.in_(sentence_ids)))
