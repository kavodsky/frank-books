"""SQLAlchemy 2.0 storage shapes. Not domain objects (architecture.md)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, String, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BookRow(Base):
    __tablename__ = "book"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True)
    lang: Mapped[str]
    title: Mapped[str]
    author: Mapped[str]
    source_url: Mapped[str]
    license_note: Mapped[str]
    status: Mapped[str]


class ChapterRow(Base):
    __tablename__ = "chapter"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    book_id: Mapped[str] = mapped_column(ForeignKey("book.id"))
    index: Mapped[int]
    title: Mapped[str]
    summary_uk: Mapped[str | None] = mapped_column(Text, nullable=True)


class PassageRow(Base):
    __tablename__ = "passage"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapter.id"))
    index: Mapped[int]


class ParagraphRow(Base):
    __tablename__ = "paragraph"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapter.id"))
    passage_id: Mapped[str | None] = mapped_column(
        ForeignKey("passage.id"), nullable=True
    )
    index: Mapped[int]
    raw_text: Mapped[str] = mapped_column(Text)
    hash: Mapped[str]
    status: Mapped[str]


class SentenceRow(Base):
    __tablename__ = "sentence"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    paragraph_id: Mapped[str] = mapped_column(ForeignKey("paragraph.id"))
    index: Mapped[int]
    text: Mapped[str] = mapped_column(Text)


class TokenRow(Base):
    __tablename__ = "token"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    sentence_id: Mapped[str] = mapped_column(ForeignKey("sentence.id"))
    index: Mapped[int]
    surface: Mapped[str]
    lemma: Mapped[str]
    upos: Mapped[str]
    morph_json: Mapped[str] = mapped_column(Text)
    dep: Mapped[str] = mapped_column(String, default="")
    head_index: Mapped[int] = mapped_column(default=0)
    reunited_lemma: Mapped[str | None] = mapped_column(String, nullable=True)


class LemmaOverrideRow(Base):
    __tablename__ = "lemma_override"

    surface: Mapped[str] = mapped_column(String, primary_key=True)
    upos: Mapped[str] = mapped_column(String, primary_key=True)
    lemma: Mapped[str]
    source: Mapped[str]


class VerbParticleRow(Base):
    __tablename__ = "verb_particle"

    particle_token_id: Mapped[str] = mapped_column(
        String, ForeignKey("token.id"), primary_key=True
    )
    sentence_id: Mapped[str] = mapped_column(ForeignKey("sentence.id"))
    verb_token_id: Mapped[str] = mapped_column(ForeignKey("token.id"))
    reunited_lemma: Mapped[str]
    source: Mapped[str]


class SenseUnitRow(Base):
    __tablename__ = "sense_unit"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    sentence_id: Mapped[str] = mapped_column(ForeignKey("sentence.id"))
    index: Mapped[int]
    start_index: Mapped[int]
    end_index: Mapped[int]


class TermRow(Base):
    __tablename__ = "term"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    book_id: Mapped[str] = mapped_column(ForeignKey("book.id"))
    kind: Mapped[str]
    surface_forms_json: Mapped[str] = mapped_column(Text)
    lemma: Mapped[str]
    translation_uk: Mapped[str]
    note: Mapped[str] = mapped_column(Text)
    approved: Mapped[bool]


class CharacterRow(Base):
    __tablename__ = "character"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    book_id: Mapped[str] = mapped_column(ForeignKey("book.id"))
    canonical_name: Mapped[str]
    translation_uk: Mapped[str]
    gender: Mapped[str]
    aliases_json: Mapped[str] = mapped_column(Text)
    role_note: Mapped[str] = mapped_column(Text)


class AddressPairRow(Base):
    __tablename__ = "address_pair"

    book_id: Mapped[str] = mapped_column(ForeignKey("book.id"), primary_key=True)
    speaker_id: Mapped[str] = mapped_column(
        ForeignKey("character.id"), primary_key=True
    )
    addressee_id: Mapped[str] = mapped_column(
        ForeignKey("character.id"), primary_key=True
    )
    tv_form: Mapped[str]


class GlossUnitRow(Base):
    __tablename__ = "gloss_unit"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    sentence_id: Mapped[str] = mapped_column(ForeignKey("sentence.id"))
    index: Mapped[int]
    source_span: Mapped[str]
    natural_uk: Mapped[str] = mapped_column(Text)
    word_for_word_uk: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str]


class WordNoteRow(Base):
    __tablename__ = "word_note"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    sentence_id: Mapped[str] = mapped_column(ForeignKey("sentence.id"))
    index: Mapped[int]
    surface: Mapped[str]
    lemma: Mapped[str]
    morph_note_uk: Mapped[str] = mapped_column(Text)
    gloss_uk: Mapped[str]


class QaResultRow(Base):
    __tablename__ = "qa_result"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    paragraph_id: Mapped[str] = mapped_column(ForeignKey("paragraph.id"))
    check_name: Mapped[str]
    passed: Mapped[bool]
    detail_json: Mapped[str] = mapped_column(Text)
    attempt: Mapped[int]


class RunRow(Base):
    __tablename__ = "run"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    book_id: Mapped[str]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str]
    passages_done: Mapped[int]
    last_passage_id: Mapped[str | None] = mapped_column(nullable=True)
    error_class: Mapped[str | None] = mapped_column(nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)


def create_book_db(path: Path) -> Engine:
    """Create (or open) a per-book SQLite file and apply the Phase 0 DDL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    return engine
