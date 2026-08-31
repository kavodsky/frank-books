"""Dual-lemmatizer partition and override application (roadmap 2.2b)."""

from __future__ import annotations

import pytest

from frank.domain.model.annotation import Annotation, Morphology, Token
from frank.domain.model.book import Sentence
from frank.domain.model.lemma import LemmaOverride, LemmaPair, LemmaSource
from frank.domain.services.lemmas import apply_overrides, lemma_types, partition_lemmas


class _TinyLexicon:
    def __init__(self, forms: frozenset[str]) -> None:
        self._forms = forms

    def contains(self, form: str) -> bool:
        return form.casefold() in self._forms


@pytest.mark.unit
def test_disagreement_and_oov_are_disputed() -> None:
    lexicon = _TinyLexicon(frozenset({"der", "kind"}))
    pairs = (
        LemmaPair(
            surface="sah",
            upos="VERB",
            example_sentence="Der Arzt sah das Kind.",
            analyzer_lemma="sah",
            second_lemma="sehen",
        ),
        LemmaPair(
            surface="felállt",
            upos="VERB",
            example_sentence="Az orvos felállt.",
            analyzer_lemma="felállt",
            second_lemma="felállt",
        ),
        LemmaPair(
            surface="Kind",
            upos="NOUN",
            example_sentence="Der Arzt sah das Kind.",
            analyzer_lemma="kind",
            second_lemma="kind",
        ),
    )
    disputed = partition_lemmas(pairs, lexicon).disputed
    surfaces = {item.surface for item in disputed}
    assert surfaces == {"sah", "felállt"}
    assert "Kind" not in surfaces


@pytest.mark.unit
def test_apply_overrides_changes_matching_tokens_only() -> None:
    sentence = Sentence(id="s1", paragraph_id="p1", index=1, text="Er sah.")
    tokens = (
        Token(
            id="s1-t1",
            sentence_id="s1",
            index=1,
            surface="sah",
            lemma="sah",
            upos="VERB",
            morph=Morphology(),
        ),
        Token(
            id="s1-t2",
            sentence_id="s1",
            index=2,
            surface=".",
            lemma=".",
            upos="PUNCT",
            morph=Morphology(),
        ),
    )
    annotation = Annotation(sentences=(sentence,), tokens=tokens)
    types = lemma_types(annotation)
    assert [item.surface for item in types] == ["sah"]
    updated = apply_overrides(
        tokens,
        (
            LemmaOverride(
                surface="sah",
                upos="VERB",
                lemma="sehen",
                source=LemmaSource.LLM,
            ),
        ),
    )
    assert updated[0].lemma == "sehen"
    assert updated[1].lemma == "."
