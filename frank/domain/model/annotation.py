"""Token, Morphology, SenseUnit — analyzer output, persistence-ignorant."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from frank.domain.model.book import Sentence
from frank.domain.model.reunion import VerbParticle


class MorphFeature(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    value: str


class Morphology(BaseModel):
    model_config = ConfigDict(frozen=True)

    features: tuple[MorphFeature, ...] = ()

    def value_of(self, key: str) -> str | None:
        for feature in self.features:
            if feature.key == key:
                return feature.value
        return None


class ParsedToken(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    surface: str
    lemma: str
    upos: str
    morph: Morphology
    dep: str = ""
    head_index: int = 0


class ParsedSentence(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    text: str
    tokens: tuple[ParsedToken, ...]


class Token(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    sentence_id: str
    index: int
    surface: str
    lemma: str
    upos: str
    morph: Morphology
    dep: str = ""
    head_index: int = 0
    reunited_lemma: str | None = None


class SenseUnit(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    sentence_id: str
    index: int
    start_index: int
    end_index: int


class SegmentationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    short_sentence_max_tokens: int
    unit_min_tokens: int
    unit_max_tokens: int
    heavy_pp_min_tokens: int


class GlossReason(StrEnum):
    FIRST_OCCURRENCE = "first_occurrence"
    REMINDER = "reminder"
    IDIOM = "idiom"
    FALSE_FRIEND = "false_friend"
    MORPH_TRAP = "morph_trap"


class GlossDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    token_id: str
    gloss: bool
    reason: GlossReason


class GlossPlanConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    frequency_top_n: int
    function_word_top_n: int
    reminder_gap_sentences: int
    reminder_max_occurrences: int
    quota_chapter_start: int
    quota_last_third: int
    rare_morph_max_count: int


class GlossLists(BaseModel):
    model_config = ConfigDict(frozen=True)

    ranked: tuple[str, ...] = ()
    false_friends: tuple[str, ...] = ()
    idioms: tuple[str, ...] = ()


class SentencePlacement(BaseModel):
    model_config = ConfigDict(frozen=True)

    sentence_id: str
    ordinal: int
    chapter_index: int


class Annotation(BaseModel):
    model_config = ConfigDict(frozen=True)

    sentences: tuple[Sentence, ...]
    tokens: tuple[Token, ...]
    particles: tuple[VerbParticle, ...] = ()
    sense_units: tuple[SenseUnit, ...] = ()
    gloss_plan: tuple[GlossDecision, ...] = ()


class GlossPlanRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    annotation: Annotation
    placements: tuple[SentencePlacement, ...]
    chapter_count: int
    lang: str
    lists: GlossLists
    config: GlossPlanConfig
