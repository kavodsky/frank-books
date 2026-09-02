"""Book, Chapter, Passage, Paragraph, Sentence."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class BookStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    INGESTED = "ingested"


class ParagraphStatus(StrEnum):
    RAW = "raw"
    COMPLETE = "complete"


class Book(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    slug: str
    lang: str
    title: str
    author: str
    source_url: str
    license_note: str
    status: BookStatus


class Chapter(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    book_id: str
    index: int
    title: str
    summary_uk: str | None = None


class Passage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    chapter_id: str
    index: int


class PassageGroupingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_chars: int
    max_chars: int
    dialogue_max_chars: int


class Paragraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    chapter_id: str
    passage_id: str | None
    index: int
    raw_text: str
    hash: str
    status: ParagraphStatus


class Sentence(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    paragraph_id: str
    index: int
    text: str


class BookStructure(BaseModel):
    model_config = ConfigDict(frozen=True)

    book: Book
    chapters: tuple[Chapter, ...]
    paragraphs: tuple[Paragraph, ...]
    passages: tuple[Passage, ...] = ()
