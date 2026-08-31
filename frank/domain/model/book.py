"""Book, Chapter, Paragraph — ingestion-time structure (Passage comes in 2.5)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class BookStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    INGESTED = "ingested"


class ParagraphStatus(StrEnum):
    RAW = "raw"


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


class Paragraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    chapter_id: str
    passage_id: str | None
    index: int
    raw_text: str
    hash: str
    status: ParagraphStatus


class BookStructure(BaseModel):
    model_config = ConfigDict(frozen=True)

    book: Book
    chapters: tuple[Chapter, ...]
    paragraphs: tuple[Paragraph, ...]
