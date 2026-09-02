"""Sentence chrF for advisory back-translation QA (roadmap 5.4)."""

from __future__ import annotations

from sacrebleu.metrics import CHRF

_CHRF = CHRF()


def sentence_chrf(hypothesis: str, reference: str) -> float:
    return _CHRF.sentence_score(hypothesis, [reference]).score
