"""LinguisticAnalyzer: spaCy/HuSpaCy behind a domain-shaped port (ADR 0003)."""

from __future__ import annotations

from typing import Protocol

from frank.domain.model.annotation import ParsedSentence
from frank.domain.model.lemma import DisputedLemma, LemmaOverride


class LinguisticAnalyzer(Protocol):
    def analyze(self, text: str) -> tuple[ParsedSentence, ...]: ...
    def second_lemma(self, surface: str, upos: str) -> str: ...


class LemmaLexicon(Protocol):
    def contains(self, form: str) -> bool: ...


class LemmaArbiter(Protocol):
    def decide(
        self, disputed: tuple[DisputedLemma, ...]
    ) -> tuple[LemmaOverride, ...]: ...
