"""Sense-unit spans over a dependency parse (roadmap 2.3)."""

from __future__ import annotations

import pytest

from frank.domain.model.annotation import (
    Annotation,
    MorphFeature,
    Morphology,
    SegmentationConfig,
    Token,
)
from frank.domain.model.book import Sentence
from frank.domain.services.segmentation import segment_annotation, segment_sentence

_CFG = SegmentationConfig(
    short_sentence_max_tokens=8,
    unit_min_tokens=3,
    unit_max_tokens=8,
    heavy_pp_min_tokens=6,
)
_FIN = Morphology(features=(MorphFeature(key="VerbForm", value="Fin"),))
_INF = Morphology(features=(MorphFeature(key="VerbForm", value="Inf"),))


def _token(
    spec: tuple[int, str, str, str, int], morph: Morphology | None = None
) -> Token:
    index, surface, upos, dep, head_index = spec
    return Token(
        id=f"s1-t{index}",
        sentence_id="s1",
        index=index,
        surface=surface,
        lemma=surface.casefold(),
        upos=upos,
        morph=morph or Morphology(),
        dep=dep,
        head_index=head_index,
    )


def _sentence(text: str) -> Sentence:
    return Sentence(id="s1", paragraph_id="p1", index=1, text=text)


def _spans(tokens: tuple[Token, ...], text: str) -> list[tuple[int, int]]:
    units = segment_sentence(_sentence(text), tokens, _CFG)
    return [(unit.start_index, unit.end_index) for unit in units]


def _surfaces(tokens: tuple[Token, ...], text: str) -> tuple[str, ...]:
    units = segment_sentence(_sentence(text), tokens, _CFG)
    return tuple(
        " ".join(
            token.surface
            for token in tokens
            if unit.start_index <= token.index <= unit.end_index
        )
        for unit in units
    )


def _covered(tokens: tuple[Token, ...], text: str) -> bool:
    units = segment_sentence(_sentence(text), tokens, _CFG)
    seen: list[int] = []
    for unit in units:
        seen.extend(range(unit.start_index, unit.end_index + 1))
    return seen == [token.index for token in tokens]


@pytest.mark.unit
def test_short_sentence_is_one_unit() -> None:
    tokens = (
        _token((1, "Es", "PRON", "sb", 2)),
        _token((2, "war", "AUX", "ROOT", 0), _FIN),
        _token((3, "einmal", "ADV", "mo", 2)),
        _token((4, "ein", "DET", "nk", 6)),
        _token((5, "armer", "ADJ", "nk", 6)),
        _token((6, "Mann", "NOUN", "pd", 2)),
        _token((7, ".", "PUNCT", "punct", 2)),
    )
    text = "Es war einmal ein armer Mann."
    assert _spans(tokens, text) == [(1, 7)]
    assert _covered(tokens, text)


@pytest.mark.unit
def test_german_hypotaxis_splits_three_clauses() -> None:
    tokens = (
        _token((1, "Als", "SCONJ", "cp", 3)),
        _token((2, "er", "PRON", "sb", 3)),
        _token((3, "aufstand", "VERB", "mo", 5), _FIN),
        _token((4, ",", "PUNCT", "punct", 5)),
        _token((5, "sah", "VERB", "ROOT", 0), _FIN),
        _token((6, "er", "PRON", "sb", 5)),
        _token((7, ",", "PUNCT", "punct", 5)),
        _token((8, "dass", "SCONJ", "cp", 12)),
        _token((9, "der", "DET", "nk", 10)),
        _token((10, "Wald", "NOUN", "sb", 12)),
        _token((11, "still", "ADV", "pd", 12)),
        _token((12, "war", "AUX", "oc", 5), _FIN),
        _token((13, ".", "PUNCT", "punct", 5)),
    )
    text = "Als er aufstand, sah er, dass der Wald still war."
    assert _spans(tokens, text) == [(1, 4), (5, 7), (8, 13)]
    assert _surfaces(tokens, text) == (
        "Als er aufstand ,",
        "sah er ,",
        "dass der Wald still war .",
    )
    assert _covered(tokens, text)


@pytest.mark.unit
def test_german_coordination_keeps_und_on_second_unit() -> None:
    tokens = (
        _token((1, "Er", "PRON", "sb", 2)),
        _token((2, "lebte", "VERB", "ROOT", 0), _FIN),
        _token((3, "am", "ADP", "mo", 2)),
        _token((4, "Waldrand", "PROPN", "nk", 3)),
        _token((5, "und", "CCONJ", "cd", 2)),
        _token((6, "suchte", "VERB", "cj", 5), _FIN),
        _token((7, "Beeren", "NOUN", "oa", 6)),
        _token((8, "im", "ADP", "mo", 6)),
        _token((9, "Herbst", "NOUN", "nk", 8)),
        _token((10, ".", "PUNCT", "punct", 2)),
    )
    text = "Er lebte am Waldrand und suchte Beeren im Herbst."
    assert _surfaces(tokens, text) == (
        "Er lebte am Waldrand",
        "und suchte Beeren im Herbst .",
    )
    assert _covered(tokens, text)


@pytest.mark.unit
def test_relative_clause_absorbs_short_noun_leftover() -> None:
    tokens = (
        _token((1, "Eine", "DET", "nk", 2)),
        _token((2, "Stadt", "NOUN", "sb", 10)),
        _token((3, ",", "PUNCT", "punct", 2)),
        _token((4, "die", "PRON", "oa", 7)),
        _token((5, "ich", "PRON", "sb", 8)),
        _token((6, "nicht", "PART", "ng", 8)),
        _token((7, "bezeichnen", "VERB", "oc", 8), _INF),
        _token((8, "will", "AUX", "rc", 2), _FIN),
        _token((9, ",", "PUNCT", "punct", 10)),
        _token((10, "besitzt", "VERB", "ROOT", 0), _FIN),
        _token((11, "ein", "DET", "nk", 12)),
        _token((12, "Armenhaus", "NOUN", "oa", 10)),
        _token((13, ".", "PUNCT", "punct", 10)),
    )
    text = "Eine Stadt, die ich nicht bezeichnen will, besitzt ein Armenhaus."
    assert _surfaces(tokens, text) == (
        "Eine Stadt , die ich nicht bezeichnen will ,",
        "besitzt ein Armenhaus .",
    )
    assert _covered(tokens, text)


@pytest.mark.unit
def test_hungarian_advcl_under_length_cap_stays_one_unit() -> None:
    tokens = (
        _token((1, "A", "DET", "det", 2)),
        _token((2, "királyfi", "NOUN", "nsubj", 3)),
        _token((3, "elindult", "VERB", "ROOT", 0), _FIN),
        _token((4, ",", "PUNCT", "punct", 6)),
        _token((5, "mert", "SCONJ", "mark", 6)),
        _token((6, "hallotta", "VERB", "advcl", 3), _FIN),
        _token((7, "a", "DET", "det", 8)),
        _token((8, "hírt", "NOUN", "obj", 6)),
        _token((9, ".", "PUNCT", "punct", 3)),
    )
    text = "A királyfi elindult, mert hallotta a hírt."
    assert _spans(tokens, text) == [(1, 9)]


@pytest.mark.unit
def test_hungarian_conj_splits_two_units() -> None:
    tokens = (
        _token((1, "Amikor", "ADV", "advmod:tlocy", 2)),
        _token((2, "megérkezett", "VERB", "ROOT", 0), _FIN),
        _token((3, "a", "DET", "det", 4)),
        _token((4, "várba", "NOUN", "obl", 2)),
        _token((5, ",", "PUNCT", "punct", 8)),
        _token((6, "az", "DET", "det", 7)),
        _token((7, "őrök", "NOUN", "nsubj", 8)),
        _token((8, "kinyitották", "VERB", "conj", 2), _FIN),
        _token((9, "a", "DET", "det", 10)),
        _token((10, "kaput", "NOUN", "obj", 8)),
        _token((11, ".", "PUNCT", "punct", 2)),
    )
    text = "Amikor megérkezett a várba, az őrök kinyitották a kaput."
    assert _surfaces(tokens, text) == (
        "Amikor megérkezett a várba ,",
        "az őrök kinyitották a kaput .",
    )
    assert _covered(tokens, text)


@pytest.mark.unit
def test_hungarian_short_ccomp_stays_one_unit() -> None:
    tokens = (
        _token((1, "Azt", "PRON", "obj", 2)),
        _token((2, "mondta", "VERB", "ROOT", 0), _FIN),
        _token((3, ",", "PUNCT", "punct", 6)),
        _token((4, "hogy", "SCONJ", "mark", 6)),
        _token((5, "holnap", "ADV", "advmod:tlocy", 6)),
        _token((6, "eljön", "VERB", "ccomp:obj", 2), _FIN),
        _token((7, ".", "PUNCT", "punct", 2)),
    )
    text = "Azt mondta, hogy holnap eljön."
    assert _spans(tokens, text) == [(1, 7)]


@pytest.mark.unit
def test_heavy_pp_splits_oversize_unit() -> None:
    tokens = (
        _token((1, "Er", "PRON", "sb", 2)),
        _token((2, "ging", "VERB", "ROOT", 0), _FIN),
        _token((3, "unter", "ADP", "mo", 2)),
        _token((4, "der", "DET", "nk", 6)),
        _token((5, "mütterlichen", "ADJ", "nk", 6)),
        _token((6, "Aufsicht", "NOUN", "nk", 3)),
        _token((7, "einer", "DET", "nk", 9)),
        _token((8, "ältlichen", "ADJ", "nk", 9)),
        _token((9, "Frau", "NOUN", "nk", 6)),
        _token((10, "nach", "ADP", "mo", 2)),
        _token((11, "Hause", "NOUN", "nk", 10)),
        _token((12, ".", "PUNCT", "punct", 2)),
    )
    text = "Er ging unter der mütterlichen Aufsicht einer ältlichen Frau nach Hause."
    units = _surfaces(tokens, text)
    assert len(units) >= 2
    assert any("Aufsicht" in piece for piece in units)
    assert _covered(tokens, text)


@pytest.mark.unit
def test_segment_annotation_is_byte_identical_on_rerun() -> None:
    sentence = Sentence(id="s1", paragraph_id="p1", index=1, text="Er geht.")
    tokens = (
        _token((1, "Er", "PRON", "sb", 2)),
        _token((2, "geht", "VERB", "ROOT", 0), _FIN),
        _token((3, ".", "PUNCT", "punct", 2)),
    )
    annotation = Annotation(sentences=(sentence,), tokens=tokens)
    first = segment_annotation(annotation, _CFG)
    second = segment_annotation(annotation, _CFG)
    assert first == second
