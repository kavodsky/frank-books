"""Separable-verb / igekötő pairing (roadmap 2.2c)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ReunionSource(StrEnum):
    LEXICON = "lexicon"
    LLM = "llm"
    LLM_VOTE = "llm_vote"


class PrefixInventory(BaseModel):
    model_config = ConfigDict(frozen=True)

    lang: Literal["de", "hu"]
    particles: frozenset[str]
    ambiguous: frozenset[str]
    auxiliaries: frozenset[str]


class ReunionCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    sentence_id: str
    particle_token_id: str
    verb_token_id: str
    example_sentence: str
    particle: str
    verb: str
    proposed_lemma: str
    needs_arbitration: bool


class VerbParticle(BaseModel):
    model_config = ConfigDict(frozen=True)

    sentence_id: str
    particle_token_id: str
    verb_token_id: str
    reunited_lemma: str
    source: ReunionSource
