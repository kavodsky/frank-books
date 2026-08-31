"""Lemma types, disputes, and overrides (roadmap 2.2b)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class LemmaSource(StrEnum):
    LLM = "llm"
    LLM_VOTE = "llm_vote"
    ANALYZER_KEPT = "analyzer_kept"


class LemmaType(BaseModel):
    model_config = ConfigDict(frozen=True)

    surface: str
    upos: str
    example_sentence: str
    analyzer_lemma: str


class LemmaPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    surface: str
    upos: str
    example_sentence: str
    analyzer_lemma: str
    second_lemma: str


class DisputedLemma(BaseModel):
    model_config = ConfigDict(frozen=True)

    surface: str
    upos: str
    example_sentence: str
    analyzer_lemma: str
    second_lemma: str


class LemmaOverride(BaseModel):
    model_config = ConfigDict(frozen=True)

    surface: str
    upos: str
    lemma: str
    source: LemmaSource


class LemmaPartition(BaseModel):
    model_config = ConfigDict(frozen=True)

    disputed: tuple[DisputedLemma, ...]
