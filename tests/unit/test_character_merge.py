"""Deterministic Character reduce (roadmap 3.3)."""

from __future__ import annotations

import pytest

from frank.domain.model.termbase import CharacterDraft, Gender, Term, TermKind
from frank.domain.services.character_merge import merge_characters


def _draft(lemma: str, canonical: str) -> CharacterDraft:
    return CharacterDraft(
        lemma=lemma,
        canonical_name=canonical,
        translation_uk="",
        gender=Gender.UNKNOWN,
    )


def _person(lemma: str, uk: str, surfaces: tuple[str, ...] = ()) -> Term:
    return Term(
        id=f"b-PERSON-{lemma}",
        book_id="b",
        kind=TermKind.PERSON,
        surface_forms=surfaces or (lemma.title(),),
        lemma=lemma,
        translation_uk=uk,
    )


@pytest.mark.unit
def test_sanyi_merges_with_sandor_via_canonical() -> None:
    drafts = (
        _draft("sándor", "Sándor").model_copy(
            update={"gender": Gender.MALE, "translation_uk": "Шандор"}
        ),
        _draft("sanyi", "Sándor").model_copy(
            update={"aliases": ("Sanyi",), "translation_uk": "Шані"}
        ),
    )
    found = merge_characters("b", drafts, (_person("sándor", "Шандор"),))
    assert len(found) == 1
    assert found[0].canonical_name == "Sándor"
    assert found[0].gender is Gender.MALE
    assert "Sanyi" in found[0].aliases
    assert found[0].translation_uk == "Шандор"


@pytest.mark.unit
def test_gender_conflict_stays_unknown() -> None:
    drafts = (
        _draft("oliver", "Oliver").model_copy(update={"gender": Gender.MALE}),
        _draft("oliver", "Oliver").model_copy(update={"gender": Gender.FEMALE}),
    )
    found = merge_characters("b", drafts, ())
    assert found[0].gender is Gender.UNKNOWN


@pytest.mark.unit
def test_known_gender_wins_over_unknown() -> None:
    drafts = (
        _draft("gretel", "Margarete").model_copy(update={"aliases": ("Gretel",)}),
        _draft("margarete", "Margarete").model_copy(update={"gender": Gender.FEMALE}),
    )
    found = merge_characters("b", drafts, ())
    assert found[0].gender is Gender.FEMALE
    assert found[0].canonical_name == "Margarete"
    assert "Gretel" in found[0].aliases


@pytest.mark.unit
def test_unrelated_persons_stay_apart() -> None:
    drafts = (
        _draft("oliver", "Oliver").model_copy(update={"gender": Gender.MALE}),
        _draft("berliner", "Berliner").model_copy(update={"gender": Gender.MALE}),
    )
    found = merge_characters("b", drafts, ())
    assert [item.canonical_name for item in found] == ["Berliner", "Oliver"]
