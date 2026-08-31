"""Hungarian HuSpaCy pipeline → ParsedSentence VOs (roadmap 2.1–2.2b)."""

from __future__ import annotations

from spacy.language import Language

from frank.domain.model.annotation import ParsedSentence
from frank.infrastructure.nlp.spacy_parse import parsed_sentences

_LOOKUP = "lookup_lemmatizer"


class HungarianAnalyzer:
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
        if _LOOKUP not in self._nlp.pipe_names:
            return surface
        lookup = self._nlp.get_pipe(_LOOKUP)
        doc = lookup(self._nlp.make_doc(surface))
        if len(doc) == 0:
            return surface
        return doc[0].lemma_.strip() or surface
