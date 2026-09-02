"""Termbase review TOML round-trip and the Phase 5 gate (roadmap 3.6)."""

from __future__ import annotations

import pytest

from frank.domain.errors import SchemaInvalid, TermbaseNotApproved
from frank.domain.model.termbase import (
    AddressPair,
    Character,
    Gender,
    Term,
    TermbaseSnapshot,
    TermKind,
    TvForm,
)
from frank.domain.services.termbase_review import (
    apply_review,
    document_from_termbase,
    parse_review_toml,
    render_review_toml,
    require_approved_termbase,
)


def _term(*, approved: bool = False) -> Term:
    return Term(
        id="b-PERSON-oliver",
        book_id="b",
        kind=TermKind.PERSON,
        surface_forms=("Oliver", "Olivers"),
        lemma="oliver",
        translation_uk="Олівер",
        note="ім'я",
        approved=approved,
    )


def _character(*, gender: Gender = Gender.MALE) -> Character:
    return Character(
        id="c-oliver",
        book_id="b",
        canonical_name="Oliver",
        translation_uk="Олівер",
        gender=gender,
        aliases=("Olly",),
        role_note="хлопець",
    )


def _sandor() -> Character:
    return Character(
        id="c-sandor",
        book_id="b",
        canonical_name="Sándor",
        translation_uk="Шандор",
        gender=Gender.UNKNOWN,
    )


def _pair() -> AddressPair:
    return AddressPair(
        book_id="b",
        speaker_id="c-oliver",
        addressee_id="c-oliver",
        tv_form=TvForm.T,
    )


def _snapshot(
    *, approved: bool = False, gender: Gender = Gender.MALE
) -> TermbaseSnapshot:
    return TermbaseSnapshot(
        terms=(_term(approved=approved),),
        characters=(_character(gender=gender),),
        address_pairs=(_pair(),),
    )


@pytest.mark.unit
def test_export_parse_round_trip_preserves_rows() -> None:
    document = document_from_termbase(_snapshot())
    again = parse_review_toml(render_review_toml(document))
    assert again == document
    assert "approved" not in render_review_toml(document)


@pytest.mark.unit
def test_apply_review_sets_approved_and_keeps_edits() -> None:
    text = render_review_toml(document_from_termbase(_snapshot()))
    text = text.replace("Олівер", "Олівєр", 1)
    snapshot = apply_review("b", parse_review_toml(text))
    assert snapshot.terms[0].approved is True
    assert snapshot.terms[0].translation_uk == "Олівєр"
    assert snapshot.terms[0].surface_forms == ("Oliver", "Olivers")
    assert snapshot.characters[0].gender is Gender.MALE
    assert snapshot.address_pairs[0].tv_form is TvForm.T


@pytest.mark.unit
def test_empty_translation_round_trips() -> None:
    snapshot = TermbaseSnapshot(
        terms=(
            Term(
                id="b-PERSON-oliver",
                book_id="b",
                kind=TermKind.PERSON,
                surface_forms=("Oliver",),
                lemma="oliver",
            ),
        )
    )
    document = document_from_termbase(snapshot)
    again = apply_review("b", parse_review_toml(render_review_toml(document)))
    assert again.terms[0].translation_uk == ""
    assert again.terms[0].approved is True


@pytest.mark.unit
def test_gate_refuses_unapproved_terms_and_unknown_gender() -> None:
    require_approved_termbase(_snapshot(approved=True))
    with pytest.raises(TermbaseNotApproved, match="unapproved terms: oliver"):
        require_approved_termbase(_snapshot(approved=False))
    with pytest.raises(TermbaseNotApproved, match="unknown gender: Sándor"):
        require_approved_termbase(
            TermbaseSnapshot(
                terms=(_term(approved=True),),
                characters=(_sandor(),),
            )
        )


@pytest.mark.unit
def test_parse_rejects_dangling_address_and_bad_enum() -> None:
    with pytest.raises(SchemaInvalid, match="needs both characters"):
        parse_review_toml(
            "characters = []\n"
            "[[address_pairs]]\n"
            'speaker_id = "c-oliver"\n'
            'addressee_id = "c-bumble"\n'
            'tv_form = "T"\n'
        )
    with pytest.raises(SchemaInvalid, match="unknown gender"):
        parse_review_toml(
            "[[characters]]\n"
            'id = "c-oliver"\n'
            'canonical_name = "Oliver"\n'
            'translation_uk = "Олівер"\n'
            'gender = "nb"\n'
        )
