"""Exonym lookup and SMART rendering application (roadmap 3.2)."""

from __future__ import annotations

import pytest

from frank.domain.model.termbase import Exonym, Term, TermKind, TermRendering
from frank.domain.services.term_renderings import (
    apply_exonyms,
    apply_renderings,
    untranslated,
)


def _term(lemma: str, kind: TermKind = TermKind.PLACE, uk: str = "") -> Term:
    return Term(
        id=f"b-{kind.value}-{lemma}",
        book_id="b",
        kind=kind,
        surface_forms=(lemma,),
        lemma=lemma,
        translation_uk=uk,
    )


@pytest.mark.unit
def test_wien_and_duna_use_exonyms() -> None:
    terms = (_term("Wien"), _term("Duna"), _term("Oliver", TermKind.PERSON))
    exonyms = (
        Exonym(lemma="wien", translation_uk="Відень"),
        Exonym(lemma="duna", translation_uk="Дунай"),
    )
    filled = apply_exonyms(terms, exonyms)
    assert filled[0].translation_uk == "Відень"
    assert filled[1].translation_uk == "Дунай"
    assert filled[2].translation_uk == ""
    assert filled[0].note == "конвенційна форма"
    assert untranslated(filled)[0].lemma == "Oliver"


@pytest.mark.unit
def test_renderings_fill_pending_and_ignore_unknown() -> None:
    terms = (
        _term("Wien", uk="Відень"),
        _term("Oliver", TermKind.PERSON),
    )
    renderings = (
        TermRendering(lemma="oliver", translation_uk="Олівер", note="ім'я"),
        TermRendering(lemma="ghost", translation_uk="Привид", note=""),
    )
    done = apply_renderings(terms, renderings)
    assert done[0].translation_uk == "Відень"
    assert done[1].translation_uk == "Олівер"
    assert done[1].note == "ім'я"
    assert done[0].approved is False
    assert done[1].approved is False


@pytest.mark.unit
def test_empty_rendering_does_not_clobber() -> None:
    terms = (_term("Oliver", TermKind.PERSON, uk="Олівер"),)
    renderings = (TermRendering(lemma="oliver", translation_uk="  ", note=""),)
    assert apply_renderings(terms, renderings)[0].translation_uk == "Олівер"
