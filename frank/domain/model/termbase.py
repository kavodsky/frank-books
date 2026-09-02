"""Termbase, Character registry, AddressPair, and StyleCard (roadmap 3.1–3.5)."""

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


class BriefCharacter(BaseModel):
    model_config = ConfigDict(frozen=True)

    canonical_name: str
    translation_uk: str


class ChapterBrief(BaseModel):
    model_config = ConfigDict(frozen=True)

    chapter_id: str
    index: int
    title: str
    lang: str
    lead: tuple[str, ...]
    tail: tuple[str, ...]
    characters: tuple[BriefCharacter, ...]


class ChapterBriefConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    lead_sentences: int
    tail_sentences: int
    summary_sentence_min: int
    summary_sentence_max: int


class ChapterSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    title: str
    summary_uk: str


class StyleCard(BaseModel):
    model_config = ConfigDict(frozen=True)

    book_id: str
    epoch: str
    setting: str
    source_register: str
    narration: str
    tone: str
    directives: str


class StyleReduceInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    book_id: str
    title: str
    author: str
    lang: str
    summaries: tuple[ChapterSummary, ...]


class ReviewTerm(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: TermKind
    lemma: str
    translation_uk: str
    note: str = ""
    surface_forms: tuple[str, ...] = ()


class ReviewCharacter(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    canonical_name: str
    translation_uk: str
    gender: Gender
    aliases: tuple[str, ...] = ()
    role_note: str = ""


class ReviewAddressPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    speaker_id: str
    addressee_id: str
    tv_form: TvForm


class ReviewDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    terms: tuple[ReviewTerm, ...] = ()
    characters: tuple[ReviewCharacter, ...] = ()
    address_pairs: tuple[ReviewAddressPair, ...] = ()


class TermbaseSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    terms: tuple[Term, ...] = ()
    characters: tuple[Character, ...] = ()
    address_pairs: tuple[AddressPair, ...] = ()
