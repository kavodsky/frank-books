"""Build the language Strategy from config (architecture.md factory function)."""

from __future__ import annotations

import spacy

from frank.config import NlpSettings
from frank.domain.errors import UnknownError
from frank.domain.ports.linguistics import LinguisticAnalyzer
from frank.infrastructure.nlp.german import GermanAnalyzer
from frank.infrastructure.nlp.hungarian import HungarianAnalyzer


def load_analyzer(lang: str, nlp: NlpSettings) -> LinguisticAnalyzer:
    name = _model_name(lang, nlp)
    try:
        pipeline = spacy.load(name)
    except OSError as exc:
        raise UnknownError(f"spaCy model not installed: {name}") from exc
    if lang == "de":
        return GermanAnalyzer(pipeline)
    return HungarianAnalyzer(pipeline)


def _model_name(lang: str, nlp: NlpSettings) -> str:
    if lang == "de":
        return nlp.german_model
    if lang == "hu":
        return nlp.hungarian_model
    raise UnknownError(f"unsupported source language: {lang}")
