"""FrankGenerator: paragraph in, FrankRecords out. Anti-corruption lives in infra."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from frank.domain.model.annotation import SenseUnit, Token
from frank.domain.model.book import Sentence
from frank.domain.model.context import PromptContext
from frank.domain.model.frank import FrankRecord, ModelTier


class ParagraphGenerationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: PromptContext
    sentences: tuple[Sentence, ...]
    sense_units: tuple[SenseUnit, ...]
    gloss_tokens: tuple[Token, ...]
    lang: str
    correction: str = ""


class FrankGenerator(Protocol):
    def generate_fast(
        self, request: ParagraphGenerationRequest
    ) -> tuple[FrankRecord, ...]: ...

    def generate_smart(
        self, request: ParagraphGenerationRequest
    ) -> tuple[FrankRecord, ...]: ...

    def back_translate(
        self, text: str, source_lang: str, producer: ModelTier
    ) -> str: ...

    def update_scene_brief(self, source_so_far: str, lang: str) -> str: ...


class GenerationCache(Protocol):
    def get_records(self, key: str) -> tuple[FrankRecord, ...] | None: ...
    def put_records(self, key: str, records: tuple[FrankRecord, ...]) -> None: ...
    def get_brief(self, key: str) -> str | None: ...
    def put_brief(self, key: str, brief: str) -> None: ...
