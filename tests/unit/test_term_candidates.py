"""NER term candidates (roadmap 3.1)."""

from __future__ import annotations

import pytest

from frank.domain.model.annotation import Morphology, Token
from frank.domain.model.termbase import TermCollectConfig, TermKind
from frank.domain.services.term_candidates import TermCollectRequest, collect_terms

_CFG = TermCollectConfig(
    entity_min_occurrences=3,
    unknown_lemma_min_count=3,
    idiom_min_occurrences=1,
    merge_max_edit_distance=2,
    merge_min_stem_chars=4,
)


class _Lexicon:
    def __init__(self, forms: tuple[str, ...] = ()) -> None:
        self._forms = frozenset(item.casefold() for item in forms)

    def contains(self, form: str) -> bool:
        return form.casefold() in self._forms


def _named(index: int, lemma: str, ent_type: str, sentence_id: str = "s1") -> Token:
    return Token(
        id=f"{sentence_id}-t{index}",
        sentence_id=sentence_id,
        index=index,
        surface=lemma,
        lemma=lemma,
        upos="PROPN",
        morph=Morphology(),
        ent_type=ent_type,
    )


def _plain(index: int, lemma: str, upos: str, sentence_id: str = "s1") -> Token:
    return Token(
        id=f"{sentence_id}-t{index}",
        sentence_id=sentence_id,
        index=index,
        surface=lemma,
        lemma=lemma,
        upos=upos,
        morph=Morphology(),
    )


def _collect(
    tokens: tuple[Token, ...],
    *,
    lexicon: _Lexicon | None = None,
    idioms: tuple[str, ...] = (),
    config: TermCollectConfig = _CFG,
) -> tuple[tuple[TermKind, str], ...]:
    terms = collect_terms(
        TermCollectRequest(
            book_id="b",
            tokens=tokens,
            lexicon=lexicon or _Lexicon(),
            idioms=idioms,
            config=config,
        )
    )
    return tuple((item.kind, item.lemma) for item in terms)


@pytest.mark.unit
def test_person_and_place_need_min_occurrences() -> None:
    tokens = (
        _named(1, "Oliver", "PER"),
        _named(2, "Berlin", "LOC"),
        _named(1, "Oliver", "PER", "s2"),
        _named(2, "Berlin", "LOC", "s2"),
        _named(1, "Oliver", "PER", "s3"),
        _named(2, "Berlin", "LOC", "s3"),
        _named(1, "Paris", "LOC", "s4"),
        _named(2, "Paris", "LOC", "s4"),
    )
    assert _collect(tokens) == (
        (TermKind.PERSON, "oliver"),
        (TermKind.PLACE, "berlin"),
    )


@pytest.mark.unit
def test_hungarian_case_suffix_merges_to_stem() -> None:
    tokens = (
        _named(1, "Budapesten", "LOC"),
        _named(1, "Budapest", "LOC", "s2"),
        _named(1, "Budapestet", "LOC", "s3"),
    )
    terms = collect_terms(
        TermCollectRequest(
            book_id="b",
            tokens=tokens,
            lexicon=_Lexicon(),
            idioms=(),
            config=_CFG,
        )
    )
    assert len(terms) == 1
    assert terms[0].kind is TermKind.PLACE
    assert terms[0].lemma == "budapest"
    assert "Budapesten" in terms[0].surface_forms


@pytest.mark.unit
def test_german_inflected_person_merges() -> None:
    tokens = (
        _named(1, "Oliver", "PER"),
        _named(1, "Olivers", "PER", "s2"),
        _named(1, "Oliver", "PER", "s3"),
    )
    assert _collect(tokens) == ((TermKind.PERSON, "oliver"),)


@pytest.mark.unit
def test_nickname_is_not_merged() -> None:
    tokens = (
        _named(1, "Sanyi", "PER"),
        _named(1, "Sanyi", "PER", "s2"),
        _named(1, "Sanyi", "PER", "s3"),
        _named(1, "Sándor", "PER", "s4"),
        _named(1, "Sándor", "PER", "s5"),
        _named(1, "Sándor", "PER", "s6"),
    )
    assert _collect(tokens) == (
        (TermKind.PERSON, "sanyi"),
        (TermKind.PERSON, "sándor"),
    )


@pytest.mark.unit
def test_misc_label_is_dropped() -> None:
    tokens = tuple(_named(1, "Weihnachten", "MISC", f"s{i}") for i in range(1, 5))
    assert _collect(tokens) == ()


@pytest.mark.unit
def test_multiword_person_stays_one_mention() -> None:
    tokens = (
        _named(1, "Oliver", "PER"),
        _named(2, "Twist", "PER"),
        _named(1, "Oliver", "PER", "s2"),
        _named(2, "Twist", "PER", "s2"),
        _named(1, "Oliver", "PER", "s3"),
        _named(2, "Twist", "PER", "s3"),
    )
    assert _collect(tokens) == ((TermKind.PERSON, "oliver twist"),)


@pytest.mark.unit
def test_unknown_lemma_becomes_disambig() -> None:
    tokens = tuple(_plain(1, "xyzzy", "NOUN", f"s{i}") for i in range(1, 4))
    assert _collect(tokens, lexicon=_Lexicon(("der",))) == (
        (TermKind.DISAMBIG, "xyzzy"),
    )


@pytest.mark.unit
def test_lexicon_hit_is_not_disambig() -> None:
    tokens = tuple(_plain(1, "haus", "NOUN", f"s{i}") for i in range(1, 6))
    assert _collect(tokens, lexicon=_Lexicon(("haus",))) == ()


@pytest.mark.unit
def test_idiom_list_hit_is_kept() -> None:
    tokens = (
        _plain(1, "kutyabol", "NOUN"),
        _plain(2, "nem", "ADV"),
        _plain(3, "lesz", "VERB"),
        _plain(4, "szalonna", "NOUN"),
    )
    assert _collect(tokens, idioms=("kutyabol nem lesz szalonna",)) == (
        (TermKind.IDIOM, "kutyabol nem lesz szalonna"),
    )


@pytest.mark.unit
def test_rerun_is_byte_identical() -> None:
    tokens = (
        _named(1, "Oliver", "PER"),
        _named(1, "Oliver", "PER", "s2"),
        _named(1, "Oliver", "PER", "s3"),
    )
    request = TermCollectRequest(
        book_id="b",
        tokens=tokens,
        lexicon=_Lexicon(),
        idioms=(),
        config=_CFG,
    )
    assert collect_terms(request) == collect_terms(request)
