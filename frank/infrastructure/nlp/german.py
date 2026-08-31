"""German spaCy pipeline → ParsedSentence VOs (roadmap 2.1–2.2b)."""

from __future__ import annotations

import simplemma
from spacy.language import Language

from frank.domain.model.annotation import ParsedSentence
from frank.infrastructure.nlp.spacy_parse import parsed_sentences


class GermanAnalyzer:
    def __init__(self, nlp: Language) -> None:
        self._nlp = nlp

    def analyze(self, text: str) -> tuple[ParsedSentence, ...]:
        if not text.strip():
            return ()
        return parsed_sentences(self._nlp(text))

    def second_lemma(self, surface: str, upos: str) -> str:
        _ = upos
        if not surface.strip():
            return surface
        return simplemma.lemmatize(surface, lang="de") or surface
