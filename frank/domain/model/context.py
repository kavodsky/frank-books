"""PromptContext and the inputs of budgeted assembly (roadmap Phase 4)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from frank.domain.model.annotation import Token
from frank.domain.model.book import Paragraph
from frank.domain.model.termbase import AddressPair, Character, StyleCard, Term


class ContextSectionName(StrEnum):
    TASK_INSTRUCTION = "task_instruction"
    TERMBASE_SLICE = "termbase_slice"
    SPEAKER_CONTEXT = "speaker_context"
    ROLLING_WINDOW = "rolling_window"
    SCENE_BRIEF = "scene_brief"
    CHAPTER_SUMMARY = "chapter_summary"
    STYLE_CARD_DIGEST = "style_card_digest"


class PromptSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: ContextSectionName
    text: str


class RollingSentence(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    idiomatic_uk: str


class ContextAssemblyConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_tokens: int
    rolling_window_sentences: int
    scene_brief_sentences: int
    style_card_digest_lines: int


class ContextAssemblyRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    paragraph: Paragraph
    tokens: tuple[Token, ...]
    terms: tuple[Term, ...]
    characters: tuple[Character, ...]
    address_pairs: tuple[AddressPair, ...]
    rolling_window: tuple[RollingSentence, ...]
    scene_brief: str
    chapter_summary: str
    style_card: StyleCard | None
    task_instruction: str
    config: ContextAssemblyConfig


class PromptContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    paragraph_id: str
    sections: tuple[PromptSection, ...]
    rendered: str
    token_count: int
    rolling_window_text: str
