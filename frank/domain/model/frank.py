"""FrankRecord and generation validation value objects (roadmap Phase 5)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from frank.domain.model.annotation import SenseUnit, Token
from frank.domain.model.book import ParagraphStatus, Sentence
from frank.domain.model.termbase import Term, TvForm


class ModelTier(StrEnum):
    FAST = "FAST"
    SMART = "SMART"


class CheckName(StrEnum):
    SCHEMA = "schema_valid"
    SENSE_UNIT_COVERAGE = "sense_unit_coverage"
    GLOSS_COVERAGE = "gloss_coverage"
    TERMBASE = "termbase_consistency"
    UKRAINIAN = "ukrainian_language"
    LENGTH_RATIO = "length_ratio"
    TV = "tv_compliance"


class SenseUnitTranslation(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_span: tuple[int, int]
    natural_uk: str
    word_for_word_uk: str | None = None


class WordNote(BaseModel):
    model_config = ConfigDict(frozen=True)

    surface: str
    lemma: str
    morph_note_uk: str
    gloss_uk: str


class FrankRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    sentence_id: str
    units: tuple[SenseUnitTranslation, ...]
    idiomatic_uk: str
    word_notes: tuple[WordNote, ...]
    tier: ModelTier


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: CheckName
    passed: bool
    detail: str = ""


class QaResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    paragraph_id: str
    check_name: str
    passed: bool
    detail: str
    attempt: int


class ParagraphOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    paragraph_id: str
    records: tuple[FrankRecord, ...]
    qa: tuple[QaResult, ...] = ()
    status: ParagraphStatus = ParagraphStatus.RAW


class ValidationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    length_ratio_min: float
    length_ratio_max: float
    ukrainian_marker_min_chars: int
    calques: tuple[str, ...] = ()


class SentenceCheckSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    sentence: Sentence
    sense_units: tuple[SenseUnit, ...]
    gloss_tokens: tuple[Token, ...]
    terms: tuple[Term, ...]
    tv_form: TvForm | None
    config: ValidationConfig
