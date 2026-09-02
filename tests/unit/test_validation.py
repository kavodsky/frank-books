"""Phase 5.2 predicates: coverage, termbase, Ukrainian, length, T/V."""

from __future__ import annotations

import pytest

from frank.domain.model.annotation import Morphology, SenseUnit, Token
from frank.domain.model.book import Sentence
from frank.domain.model.frank import (
    CheckName,
    FrankRecord,
    ModelTier,
    SenseUnitTranslation,
    SentenceCheckSpec,
    ValidationConfig,
    WordNote,
)
from frank.domain.model.termbase import Term, TermKind, TvForm
from frank.domain.services.validation import failed_checks, validate_record

_CFG = ValidationConfig(
    length_ratio_min=0.6,
    length_ratio_max=2.0,
    ukrainian_marker_min_chars=20,
    calques=("получити", "приймати участь"),
)


def _sentence(text: str = "Oliver kommt.") -> Sentence:
    return Sentence(id="s1", paragraph_id="p1", index=1, text=text)


def _unit() -> SenseUnit:
    return SenseUnit(id="u1", sentence_id="s1", index=1, start_index=0, end_index=2)


def _token(row: tuple[int, str, str, str], reunited: str | None = None) -> Token:
    index, surface, lemma, upos = row
    return Token(
        id=f"t{index}",
        sentence_id="s1",
        index=index,
        surface=surface,
        lemma=lemma,
        upos=upos,
        morph=Morphology(),
        reunited_lemma=reunited,
    )


def _term(lemma: str, uk: str, *surfaces: str) -> Term:
    forms = surfaces if surfaces else (lemma,)
    return Term(
        id=f"b-{lemma}",
        book_id="b",
        kind=TermKind.PERSON,
        surface_forms=forms,
        lemma=lemma,
        translation_uk=uk,
        approved=True,
    )


def _record(
    *,
    natural: str = "Олівер іде",
    idiomatic: str = "Олівер іде.",
    notes: tuple[WordNote, ...] = (),
    span: tuple[int, int] = (0, 2),
) -> FrankRecord:
    return FrankRecord(
        sentence_id="s1",
        units=(
            SenseUnitTranslation(
                source_span=span, natural_uk=natural, word_for_word_uk=None
            ),
        ),
        idiomatic_uk=idiomatic,
        word_notes=notes,
        tier=ModelTier.FAST,
    )


def _spec(
    *,
    text: str = "Oliver kommt.",
    gloss: tuple[Token, ...] = (),
    terms: tuple[Term, ...] = (),
    tv: TvForm | None = None,
) -> SentenceCheckSpec:
    return SentenceCheckSpec(
        sentence=_sentence(text),
        sense_units=(_unit(),),
        gloss_tokens=gloss,
        terms=terms,
        tv_form=tv,
        config=_CFG,
    )


@pytest.mark.unit
def test_oliver_term_must_appear_as_oliver_uk() -> None:
    spec = _spec(terms=(_term("Oliver", "Олівер", "Oliver"),))
    ok = validate_record(_record(), spec)
    assert failed_checks(ok) == ()
    bad = _record(natural="він іде", idiomatic="Він іде додому вже зараз.")
    names = {item.name for item in failed_checks(validate_record(bad, spec))}
    assert CheckName.TERMBASE in names


@pytest.mark.unit
def test_sandor_term_must_appear_as_sandor_uk() -> None:
    spec = _spec(
        text="Sándor nevet.",
        terms=(_term("Sándor", "Шандор", "Sándor"),),
    )
    ok = _record(natural="Шандор сміється", idiomatic="Шандор сміється.")
    assert failed_checks(validate_record(ok, spec)) == ()
    bad = _record(natural="він сміється", idiomatic="Він сміється з цього вже зараз.")
    names = {item.name for item in failed_checks(validate_record(bad, spec))}
    assert CheckName.TERMBASE in names


@pytest.mark.unit
def test_russian_yer_letter_fails_ukrainian_guard() -> None:
    record = _record(natural="Олівер идёт", idiomatic="Олівер идёт.")
    names = {item.name for item in failed_checks(validate_record(record, _spec()))}
    assert CheckName.UKRAINIAN in names


@pytest.mark.unit
def test_calque_fails_ukrainian_guard() -> None:
    blob = "Олівер хоче получити роботу в місті вже зараз."
    record = _record(natural="Олівер хоче получити роботу", idiomatic=blob)
    names = {item.name for item in failed_checks(validate_record(record, _spec()))}
    assert CheckName.UKRAINIAN in names


@pytest.mark.unit
def test_length_ratio_out_of_range_fails() -> None:
    record = _record(idiomatic="Так.")
    names = {item.name for item in failed_checks(validate_record(record, _spec()))}
    assert CheckName.LENGTH_RATIO in names


@pytest.mark.unit
def test_tv_t_rejects_capital_vy() -> None:
    record = _record(idiomatic="Олівер, Ви йдете?")
    names = {
        item.name for item in failed_checks(validate_record(record, _spec(tv=TvForm.T)))
    }
    assert CheckName.TV in names


@pytest.mark.unit
def test_tv_v_rejects_ty() -> None:
    record = _record(idiomatic="Олівер, ти йдеш?")
    names = {
        item.name for item in failed_checks(validate_record(record, _spec(tv=TvForm.V)))
    }
    assert CheckName.TV in names


@pytest.mark.unit
def test_tv_mixed_is_skipped() -> None:
    record = _record(idiomatic="Олівер, ти й Ви.")
    assert failed_checks(validate_record(record, _spec(tv=TvForm.MIXED))) == ()


@pytest.mark.unit
def test_gloss_uses_reunited_lemma() -> None:
    token = _token((1, "ruft", "rufen", "VERB"), reunited="anrufen")
    note = WordNote(
        surface="ruft", lemma="anrufen", morph_note_uk="префікс", gloss_uk="телефонує"
    )
    record = _record(notes=(note,))
    spec = _spec(gloss=(token,))
    assert failed_checks(validate_record(record, spec)) == ()
    wrong = _record(
        notes=(
            WordNote(surface="ruft", lemma="rufen", morph_note_uk="", gloss_uk="кличе"),
        )
    )
    names = {item.name for item in failed_checks(validate_record(wrong, spec))}
    assert CheckName.GLOSS_COVERAGE in names


@pytest.mark.unit
def test_empty_natural_uk_fails_coverage() -> None:
    record = _record(natural="  ")
    names = {item.name for item in failed_checks(validate_record(record, _spec()))}
    assert CheckName.SENSE_UNIT_COVERAGE in names
