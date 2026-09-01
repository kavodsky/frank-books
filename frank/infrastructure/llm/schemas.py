"""Pydantic contracts for LLM I/O; `model_json_schema()` feeds response_format."""

from __future__ import annotations

from pydantic import BaseModel, Field

from frank.domain.errors import SchemaInvalid


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


class TermProposal(BaseModel):
    lemma: str
    translation_uk: str
    note: str


class TermBatchResult(BaseModel):
    items: list[TermProposal]


def openai_strict_schema(schema: dict[str, object]) -> dict[str, object]:
    """Pydantic fields stay the source; OpenAI requires additionalProperties: false."""
    strict = _strict_node(schema)
    if not isinstance(strict, dict):
        raise SchemaInvalid("json_schema must be an object")
    return strict


def _strict_node(node: object) -> object:
    if isinstance(node, dict):
        out = {key: _strict_node(value) for key, value in node.items()}
        if out.get("type") == "object" or "properties" in out:
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_strict_node(item) for item in node]
    return node
