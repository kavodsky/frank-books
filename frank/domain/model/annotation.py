"""Token, Morphology — analyzer output, persistence-ignorant (roadmap 2.2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from frank.domain.model.book import Sentence


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


class Annotation(BaseModel):
    model_config = ConfigDict(frozen=True)

    sentences: tuple[Sentence, ...]
    tokens: tuple[Token, ...]
