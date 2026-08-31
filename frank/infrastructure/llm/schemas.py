"""Pydantic contracts for LLM I/O; `model_json_schema()` feeds response_format."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BenchTranslation(BaseModel):
    translation_uk: str


class BenchJudgement(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str


class LemmaProposal(BaseModel):
    surface: str
    upos: str
    lemma: str


class LemmaBatchResult(BaseModel):
    items: list[LemmaProposal]


class ReunionProposal(BaseModel):
    particle: str
    verb: str
    reunited_lemma: str | None


class ReunionBatchResult(BaseModel):
    items: list[ReunionProposal]
