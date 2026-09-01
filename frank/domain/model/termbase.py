"""Termbase candidates (roadmap 3.1). Translation and approval come in 3.2 / 3.6."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class TermKind(StrEnum):
    PERSON = "PERSON"
    PLACE = "PLACE"
    ORG = "ORG"
    TITLE = "TITLE"
    IDIOM = "IDIOM"
    DISAMBIG = "DISAMBIG"


class Term(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    book_id: str
    kind: TermKind
    surface_forms: tuple[str, ...]
    lemma: str
    translation_uk: str = ""
    note: str = ""
    approved: bool = False


class Exonym(BaseModel):
    model_config = ConfigDict(frozen=True)

    lemma: str
    translation_uk: str


class TermRendering(BaseModel):
    model_config = ConfigDict(frozen=True)

    lemma: str
    translation_uk: str
    note: str


class TermCollectConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_min_occurrences: int
    unknown_lemma_min_count: int
    idiom_min_occurrences: int
    merge_max_edit_distance: int
    merge_min_stem_chars: int
