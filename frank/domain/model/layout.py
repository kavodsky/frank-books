"""Layout tree for a Frank book. Persistence- and docx-ignorant (roadmap Phase 6)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from frank.domain.model.annotation import SenseUnit, Token
from frank.domain.model.book import BookStructure, Sentence
from frank.domain.model.frank import FrankRecord


class RunStyle(StrEnum):
    ORIGINAL = "original"
    TRANSLATION = "translation"
    GLOSS = "gloss"
    NOTE = "note"
    UNADAPTED = "unadapted"


class LayoutRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    style: RunStyle


class LayoutParagraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    runs: tuple[LayoutRun, ...]


class LayoutPassage(BaseModel):
    model_config = ConfigDict(frozen=True)

    adapted: tuple[LayoutParagraph, ...]
    unadapted: tuple[LayoutParagraph, ...]


class LayoutChapter(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    passages: tuple[LayoutPassage, ...]


class LayoutBook(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    author: str
    source_url: str
    license_note: str
    chapters: tuple[LayoutChapter, ...]
    marker: str


class LayoutRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    structure: BookStructure
    sentences: tuple[Sentence, ...]
    tokens: tuple[Token, ...]
    units: tuple[SenseUnit, ...]
    records: tuple[FrankRecord, ...]
