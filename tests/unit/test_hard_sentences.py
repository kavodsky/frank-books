"""Hard-sentence flags for SMART escalation (roadmap 5.3)."""

from __future__ import annotations

import pytest

from frank.domain.model.annotation import MorphFeature, Morphology, Token
from frank.domain.model.book import Sentence
from frank.domain.model.termbase import Term, TermKind
from frank.domain.services.hard_sentences import hard_sentence_ids


def _token(row: tuple[str, int, str, str, str], mood: str | None = None) -> Token:
    sentence_id, index, surface, lemma, upos = row
    features = () if mood is None else (MorphFeature(key="Mood", value=mood),)
    return Token(
        id=f"{sentence_id}-t{index}",
        sentence_id=sentence_id,
        index=index,
        surface=surface,
        lemma=lemma,
        upos=upos,
        morph=Morphology(features=features),
    )


def _sentence(sid: str, text: str) -> Sentence:
    return Sentence(id=sid, paragraph_id="p1", index=1, text=text)


@pytest.mark.unit
def test_german_subjunctive_is_hard() -> None:
    sentence = _sentence("s1", "Wenn er Zeit hätte.")
    tokens = (
        _token(("s1", 1, "Wenn", "wenn", "SCONJ")),
        _token(("s1", 2, "er", "er", "PRON")),
        _token(("s1", 3, "Zeit", "Zeit", "NOUN")),
        _token(("s1", 4, "hätte", "haben", "VERB"), mood="Sub"),
        _token(("s1", 5, ".", ".", "PUNCT")),
    )
    assert hard_sentence_ids((sentence,), tokens, (), 24) == frozenset({"s1"})


@pytest.mark.unit
def test_hungarian_conditional_is_hard() -> None:
    sentence = _sentence("s1", "Ha időnk volna.")
    tokens = (
        _token(("s1", 1, "Ha", "ha", "SCONJ")),
        _token(("s1", 2, "időnk", "idő", "NOUN")),
        _token(("s1", 3, "volna", "van", "VERB"), mood="Cnd"),
        _token(("s1", 4, ".", ".", "PUNCT")),
    )
    assert hard_sentence_ids((sentence,), tokens, (), 24) == frozenset({"s1"})


@pytest.mark.unit
def test_idiom_hit_is_hard() -> None:
    sentence = _sentence("s1", "Kutyából nem lesz szalonna.")
    tokens = (
        _token(("s1", 1, "Kutyából", "kutya", "NOUN")),
        _token(("s1", 2, "nem", "nem", "ADV")),
        _token(("s1", 3, "lesz", "lesz", "VERB")),
        _token(("s1", 4, "szalonna", "szalonna", "NOUN")),
    )
    idiom = Term(
        id="idiom-1",
        book_id="b",
        kind=TermKind.IDIOM,
        surface_forms=("Kutyából nem lesz szalonna",),
        lemma="szalonna",
        translation_uk="горбатого могила виправить",
        approved=True,
    )
    assert hard_sentence_ids((sentence,), tokens, (idiom,), 24) == frozenset({"s1"})


@pytest.mark.unit
def test_long_hypotaxis_is_hard() -> None:
    sentence = _sentence("s1", "x")
    tokens = tuple(
        _token(("s1", index, f"w{index}", f"l{index}", "NOUN")) for index in range(24)
    )
    assert hard_sentence_ids((sentence,), tokens, (), 24) == frozenset({"s1"})


@pytest.mark.unit
def test_short_indicative_is_not_hard() -> None:
    sentence = _sentence("s1", "Oliver kommt.")
    tokens = (
        _token(("s1", 1, "Oliver", "Oliver", "PROPN")),
        _token(("s1", 2, "kommt", "kommen", "VERB")),
        _token(("s1", 3, ".", ".", "PUNCT")),
    )
    assert hard_sentence_ids((sentence,), tokens, (), 24) == frozenset()
