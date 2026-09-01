"""LinguisticAnalyzer: spaCy/HuSpaCy behind a domain-shaped port (ADR 0003)."""

from __future__ import annotations

from typing import Protocol

from frank.domain.model.annotation import ParsedSentence
from frank.domain.model.lemma import DisputedLemma, LemmaOverride
from frank.domain.model.reunion import ReunionCandidate, VerbParticle
from frank.domain.model.termbase import Term, TermRendering


class LinguisticAnalyzer(Protocol):
    def analyze(self, text: str) -> tuple[ParsedSentence, ...]: ...
    def second_lemma(self, surface: str, upos: str) -> str: ...


class LemmaLexicon(Protocol):
    def contains(self, form: str) -> bool: ...


class LemmaArbiter(Protocol):
    def decide(
        self, disputed: tuple[DisputedLemma, ...]
    ) -> tuple[LemmaOverride, ...]: ...
    def decide_reunions(
        self, pending: tuple[ReunionCandidate, ...]
    ) -> tuple[VerbParticle, ...]: ...


class TermTranslator(Protocol):
    def propose(
        self, terms: tuple[Term, ...], lang: str
    ) -> tuple[TermRendering, ...]: ...
