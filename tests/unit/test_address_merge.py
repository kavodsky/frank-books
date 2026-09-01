"""Merge AddressObservation rows into AddressPair (roadmap 3.4)."""

from __future__ import annotations

import pytest

from frank.domain.model.termbase import (
    AddressMatrixConfig,
    AddressObservation,
    Character,
    Gender,
    TvForm,
)
from frank.domain.services.address_merge import (
    fill_unresolved_mixed,
    merge_address_observations,
)

_CFG = AddressMatrixConfig(evidence_sentences_per_pair=3)


def _char(name: str) -> Character:
    slug = name.casefold()
    return Character(
        id=f"b-char-{slug}",
        book_id="b",
        canonical_name=name,
        translation_uk=name,
        gender=Gender.MALE,
    )


def _obs(
    speaker: str | None,
    addressee: str | None,
    form: TvForm | None,
    sentence: str,
) -> AddressObservation:
    return AddressObservation(
        speaker_id=None if speaker is None else f"b-char-{speaker}",
        addressee_id=None if addressee is None else f"b-char-{addressee}",
        tv_form=form,
        sentence=sentence,
    )


@pytest.mark.unit
def test_consistent_du_stays_t() -> None:
    resolved, unresolved = merge_address_observations(
        "b",
        (
            _obs("bumble", "oliver", TvForm.T, "Willst du, Oliver?"),
            _obs("bumble", "oliver", TvForm.T, "Du bist neun."),
        ),
        (_char("Bumble"), _char("Oliver")),
        _CFG,
    )
    assert unresolved == ()
    assert len(resolved) == 1
    assert resolved[0].tv_form is TvForm.T


@pytest.mark.unit
def test_t_then_v_becomes_mixed() -> None:
    resolved, unresolved = merge_address_observations(
        "b",
        (
            _obs("bumble", "oliver", TvForm.T, "Du kommst."),
            _obs("bumble", "oliver", TvForm.V, "Sie kommen."),
        ),
        (_char("Bumble"), _char("Oliver")),
        _CFG,
    )
    assert unresolved == ()
    assert resolved[0].tv_form is TvForm.MIXED


@pytest.mark.unit
def test_unknown_form_is_unresolved() -> None:
    resolved, unresolved = merge_address_observations(
        "b",
        (_obs("bumble", "oliver", None, "Oliver, hörst du? Nein, wait."),),
        (_char("Bumble"), _char("Oliver")),
        _CFG,
    )
    assert resolved == ()
    assert len(unresolved) == 1
    assert unresolved[0].speaker_name == "Bumble"
    assert unresolved[0].addressee_name == "Oliver"


@pytest.mark.unit
def test_missing_endpoint_is_dropped() -> None:
    resolved, unresolved = merge_address_observations(
        "b",
        (_obs("bumble", None, TvForm.T, "Du!"),),
        (_char("Bumble"), _char("Oliver")),
        _CFG,
    )
    assert resolved == ()
    assert unresolved == ()


@pytest.mark.unit
def test_unanswered_smart_pairs_become_mixed() -> None:
    _, unresolved = merge_address_observations(
        "b",
        (_obs("bumble", "oliver", None, "Na?"),),
        (_char("Bumble"), _char("Oliver")),
        _CFG,
    )
    filled = fill_unresolved_mixed("b", unresolved, ())
    assert filled[0].tv_form is TvForm.MIXED
