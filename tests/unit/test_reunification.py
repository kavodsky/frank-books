"""Separable-verb / igekötő pairing (roadmap 2.2c)."""

from __future__ import annotations

import pytest

from frank.domain.model.annotation import Annotation, MorphFeature, Morphology, Token
from frank.domain.model.book import Sentence
from frank.domain.model.reunion import PrefixInventory, ReunionSource, VerbParticle
from frank.domain.services.reunification import (
    apply_reunions,
    partition_reunions,
    reunion_candidates,
)

_DE = PrefixInventory(
    lang="de",
    particles=frozenset({"an", "auf", "um"}),
    ambiguous=frozenset({"um"}),
    auxiliaries=frozenset({"haben", "sein", "werden"}),
)
_HU = PrefixInventory(
    lang="hu",
    particles=frozenset({"el", "fel", "föl", "meg"}),
    ambiguous=frozenset(),
    auxiliaries=frozenset({"tud", "fog", "akar", "kell"}),
)


class _Lexicon:
    def __init__(self, forms: frozenset[str]) -> None:
        self._forms = forms

    def contains(self, form: str) -> bool:
        return form.casefold() in self._forms


def _token(index: int, surface: str, lemma: str, upos: str) -> Token:
    return Token(
        id=f"s1-t{index}",
        sentence_id="s1",
        index=index,
        surface=surface,
        lemma=lemma,
        upos=upos,
        morph=Morphology(),
    )


def _dep(token: Token, dep: str, head_index: int) -> Token:
    return token.model_copy(update={"dep": dep, "head_index": head_index})


def _inf(token: Token) -> Token:
    morph = Morphology(features=(MorphFeature(key="VerbForm", value="Inf"),))
    return token.model_copy(update={"morph": morph})


def _annotation(text: str, tokens: tuple[Token, ...]) -> Annotation:
    sentence = Sentence(id="s1", paragraph_id="p1", index=1, text=text)
    return Annotation(sentences=(sentence,), tokens=tokens)


@pytest.mark.unit
def test_german_svp_pairs_anrufen() -> None:
    annotation = _annotation(
        "Er ruft an.",
        (
            _dep(_token(1, "Er", "er", "PRON"), "sb", 2),
            _dep(_token(2, "ruft", "rufen", "VERB"), "ROOT", 0),
            _dep(_token(3, "an", "an", "PART"), "svp", 2),
            _dep(_token(4, ".", ".", "PUNCT"), "punct", 2),
        ),
    )
    found = reunion_candidates(annotation, _DE, _Lexicon(frozenset({"anrufen"})))
    assert len(found) == 1
    assert found[0].proposed_lemma == "anrufen"
    assert found[0].needs_arbitration is False
    accepted, pending = partition_reunions(found)
    assert pending == ()
    assert accepted[0].source is ReunionSource.LEXICON
    verbs = apply_reunions(annotation.tokens, accepted)
    assert verbs[1].reunited_lemma == "anrufen"
    assert verbs[2].reunited_lemma is None


@pytest.mark.unit
def test_german_preposition_an_is_not_a_particle() -> None:
    annotation = _annotation(
        "Er sitzt an dem Tisch.",
        (
            _dep(_token(1, "Er", "er", "PRON"), "sb", 2),
            _dep(_token(2, "sitzt", "sitzen", "VERB"), "ROOT", 0),
            _dep(_token(3, "an", "an", "ADP"), "case", 5),
            _dep(_token(4, "dem", "der", "DET"), "det", 5),
            _dep(_token(5, "Tisch", "Tisch", "NOUN"), "obj", 2),
        ),
    )
    found = reunion_candidates(annotation, _DE, _Lexicon(frozenset({"ansitzen"})))
    assert found == ()


@pytest.mark.unit
def test_german_ambiguous_um_goes_to_arbitration() -> None:
    annotation = _annotation(
        "Er fährt um.",
        (
            _dep(_token(1, "Er", "er", "PRON"), "sb", 2),
            _dep(_token(2, "fährt", "fahren", "VERB"), "ROOT", 0),
            _dep(_token(3, "um", "um", "PART"), "svp", 2),
        ),
    )
    found = reunion_candidates(annotation, _DE, _Lexicon(frozenset({"umfahren"})))
    assert found[0].proposed_lemma == "umfahren"
    assert found[0].needs_arbitration is True
    accepted, pending = partition_reunions(found)
    assert accepted == ()
    assert pending[0].particle == "um"


@pytest.mark.unit
def test_hungarian_preverb_attaches_to_infinitive_not_auxiliary() -> None:
    annotation = _annotation(
        "El tudta olvasni.",
        (
            _dep(_token(1, "El", "el", "ADV"), "compound:preverb", 2),
            _dep(_token(2, "tudta", "tud", "AUX"), "ROOT", 0),
            _inf(_dep(_token(3, "olvasni", "olvas", "VERB"), "xcomp", 2)),
            _dep(_token(4, ".", ".", "PUNCT"), "punct", 2),
        ),
    )
    found = reunion_candidates(annotation, _HU, _Lexicon(frozenset({"elolvas"})))
    assert len(found) == 1
    assert found[0].verb == "olvas"
    assert found[0].proposed_lemma == "elolvas"
    assert found[0].needs_arbitration is False


@pytest.mark.unit
def test_hungarian_olvasd_el_pairs_elolvas() -> None:
    annotation = _annotation(
        "Olvasd el.",
        (
            _dep(_token(1, "Olvasd", "olvas", "VERB"), "ROOT", 0),
            _dep(_token(2, "el", "el", "ADV"), "compound:preverb", 1),
        ),
    )
    found = reunion_candidates(annotation, _HU, _Lexicon(frozenset({"elolvas"})))
    assert found[0].proposed_lemma == "elolvas"


@pytest.mark.unit
def test_hungarian_fol_tries_fel_variant() -> None:
    annotation = _annotation(
        "Fölállt.",
        (
            _dep(_token(1, "Föl", "föl", "ADV"), "compound:preverb", 2),
            _dep(_token(2, "állt", "áll", "VERB"), "ROOT", 0),
        ),
    )
    found = reunion_candidates(annotation, _HU, _Lexicon(frozenset({"feláll"})))
    assert found[0].needs_arbitration is False
    assert found[0].proposed_lemma == "feláll"


@pytest.mark.unit
def test_oov_reunited_lemma_is_disputed() -> None:
    annotation = _annotation(
        "Er ruft an.",
        (
            _dep(_token(2, "ruft", "rufen", "VERB"), "ROOT", 0),
            _dep(_token(3, "an", "an", "PART"), "svp", 2),
        ),
    )
    found = reunion_candidates(annotation, _DE, _Lexicon(frozenset()))
    assert found[0].needs_arbitration is True


@pytest.mark.unit
def test_apply_reunions_only_touches_the_verb() -> None:
    tokens = (
        _token(1, "ruft", "rufen", "VERB"),
        _token(2, "an", "an", "PART"),
    )
    particles = (
        VerbParticle(
            sentence_id="s1",
            particle_token_id="s1-t2",
            verb_token_id="s1-t1",
            reunited_lemma="anrufen",
            source=ReunionSource.LLM,
        ),
    )
    updated = apply_reunions(tokens, particles)
    assert updated[0].reunited_lemma == "anrufen"
    assert updated[1].reunited_lemma is None
