"""Termbase, Character registry, and AddressPair value objects (roadmap 3.1–3.4)."""

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


class Gender(StrEnum):
    FEMALE = "female"
    MALE = "male"
    UNKNOWN = "unknown"


class Character(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    book_id: str
    canonical_name: str
    translation_uk: str
    gender: Gender
    aliases: tuple[str, ...] = ()
    role_note: str = ""


class CharacterDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    lemma: str
    canonical_name: str
    translation_uk: str
    gender: Gender
    aliases: tuple[str, ...] = ()
    role_note: str = ""


class PersonEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    lemma: str
    translation_uk: str
    surface_forms: tuple[str, ...]
    sentences: tuple[str, ...]


class ChapterEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    chapter_id: str
    persons: tuple[PersonEvidence, ...]


class CharacterEvidenceConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_sentences_per_person: int


class TvForm(StrEnum):
    T = "T"
    V = "V"
    MIXED = "MIXED"


class AddressPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    book_id: str
    speaker_id: str
    addressee_id: str
    tv_form: TvForm


class AddressObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    speaker_id: str | None
    addressee_id: str | None
    tv_form: TvForm | None
    sentence: str


class UnresolvedPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    book_id: str
    speaker_id: str
    addressee_id: str
    speaker_name: str
    addressee_name: str
    sentences: tuple[str, ...]


class AddressCues(BaseModel):
    model_config = ConfigDict(frozen=True)

    t_lemmas: tuple[str, ...]
    v_lemmas: tuple[str, ...]
    v_surfaces: tuple[str, ...]
    speech_lemmas: tuple[str, ...]


class AddressMatrixConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_sentences_per_pair: int


class TermCollectConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_min_occurrences: int
    unknown_lemma_min_count: int
    idiom_min_occurrences: int
    merge_max_edit_distance: int
    merge_min_stem_chars: int
