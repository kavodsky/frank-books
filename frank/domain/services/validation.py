"""Named predicates for generation and Dagster asset checks. No LLM.

German: ``Oliver`` in the source with termbase ``Олівер`` fails unless ``Олівер``
appears in ``idiomatic_uk`` / unit renderings. Hungarian: ``Sándor`` / ``Шандор``.
Russian-only letters (``ы``) fail the Ukrainian guard; ``ти`` vs ``Ви`` follows
the address matrix in dialogue.
"""

from __future__ import annotations

import re

from frank.domain.model.annotation import SenseUnit, Token
from frank.domain.model.frank import (
    CheckName,
    CheckResult,
    FrankRecord,
    SenseUnitTranslation,
    SentenceCheckSpec,
    ValidationConfig,
    WordNote,
)
from frank.domain.model.termbase import Term, TvForm

_RUSSIAN_ONLY = re.compile(r"[ыэъёЫЭЪЁ]")
_UK_MARKERS = re.compile(r"[ієїґІЄЇҐ]")
_TY = re.compile(r"\bти\b", re.IGNORECASE)
_VY = re.compile(r"\bВи\b")


def validate_record(
    record: FrankRecord, spec: SentenceCheckSpec
) -> tuple[CheckResult, ...]:
    """Run every 5.2 predicate; order is stable for retries and asset checks."""
    return (
        schema_valid(record, spec.sense_units),
        sense_units_covered(record, spec.sense_units),
        glosses_covered(record, spec.gloss_tokens),
        termbase_consistent(record, spec.terms),
        ukrainian_output(record, spec.config),
        length_in_range(record, spec.sentence.text, spec.config),
        tv_matches(record, spec.tv_form),
    )


def schema_valid(record: FrankRecord, units: tuple[SenseUnit, ...]) -> CheckResult:
    if record.sentence_id == "":
        return _fail(CheckName.SCHEMA, "empty sentence_id")
    if len(record.units) != len(units):
        return _fail(CheckName.SCHEMA, "unit count does not match sense units")
    return _ok(CheckName.SCHEMA)


def sense_units_covered(
    record: FrankRecord, units: tuple[SenseUnit, ...]
) -> CheckResult:
    if any(not item.natural_uk.strip() for item in record.units):
        return _fail(CheckName.SENSE_UNIT_COVERAGE, "empty natural_uk")
    if len(record.units) != len(units):
        return _fail(CheckName.SENSE_UNIT_COVERAGE, "unit count does not match")
    for got, expected in zip(record.units, units, strict=True):
        span = (expected.start_index, expected.end_index)
        if got.source_span != span:
            return _fail(CheckName.SENSE_UNIT_COVERAGE, "source_span mismatch")
    return _ok(CheckName.SENSE_UNIT_COVERAGE)


def glosses_covered(record: FrankRecord, tokens: tuple[Token, ...]) -> CheckResult:
    notes = {_note_lemma(item): item for item in record.word_notes}
    missing = tuple(_missing_gloss(token, notes) for token in tokens)
    gaps = tuple(item for item in missing if item)
    if gaps:
        return _fail(CheckName.GLOSS_COVERAGE, "missing notes: " + ", ".join(gaps))
    return _ok(CheckName.GLOSS_COVERAGE)


def termbase_consistent(record: FrankRecord, terms: tuple[Term, ...]) -> CheckResult:
    blob = _output_blob(record).casefold()
    missing = [
        term.lemma
        for term in terms
        if term.translation_uk and term.translation_uk.casefold() not in blob
    ]
    if missing:
        return _fail(CheckName.TERMBASE, "missing renderings: " + ", ".join(missing))
    return _ok(CheckName.TERMBASE)


def ukrainian_output(record: FrankRecord, config: ValidationConfig) -> CheckResult:
    blob = _output_blob(record)
    if _RUSSIAN_ONLY.search(blob):
        return _fail(CheckName.UKRAINIAN, "Russian-only letters")
    if (
        len(blob) >= config.ukrainian_marker_min_chars
        and _UK_MARKERS.search(blob) is None
    ):
        return _fail(CheckName.UKRAINIAN, "no Ukrainian markers")
    hit = _calque_hit(blob, config.calques)
    if hit is not None:
        return _fail(CheckName.UKRAINIAN, f"calque: {hit}")
    return _ok(CheckName.UKRAINIAN)


def length_in_range(
    record: FrankRecord, source: str, config: ValidationConfig
) -> CheckResult:
    if not source.strip():
        return _ok(CheckName.LENGTH_RATIO)
    ratio = len(record.idiomatic_uk) / len(source)
    low, high = config.length_ratio_min, config.length_ratio_max
    if ratio < low or ratio > high:
        return _fail(CheckName.LENGTH_RATIO, f"ratio {ratio:.2f}")
    return _ok(CheckName.LENGTH_RATIO)


def tv_matches(record: FrankRecord, form: TvForm | None) -> CheckResult:
    if form is None or form is TvForm.MIXED:
        return _ok(CheckName.TV)
    blob = _output_blob(record)
    if form is TvForm.T and _VY.search(blob):
        return _fail(CheckName.TV, "expected ти, found Ви")
    if form is TvForm.V and _TY.search(blob):
        return _fail(CheckName.TV, "expected Ви, found ти")
    return _ok(CheckName.TV)


def failed_checks(results: tuple[CheckResult, ...]) -> tuple[CheckResult, ...]:
    return tuple(item for item in results if not item.passed)


def named_check(
    record: FrankRecord, spec: SentenceCheckSpec, name: CheckName
) -> CheckResult:
    """Pick one 5.2 predicate out of ``validate_record`` for an asset check."""
    return next(item for item in validate_record(record, spec) if item.name is name)


def lemmas_present(tokens: tuple[Token, ...]) -> CheckResult:
    """Every token has a non-empty lemma (roadmap 7.2).

    German ``kam`` must carry lemma ``kommen``; Hungarian ``elindult`` must
    carry ``elindul``. Empty lemmas fail the segmentation asset check.
    """
    missing = tuple(item.surface for item in tokens if not item.lemma.strip())
    if missing:
        return _fail(CheckName.LEMMAS, "empty lemma: " + ", ".join(missing[:8]))
    return _ok(CheckName.LEMMAS)


def _ok(name: CheckName) -> CheckResult:
    return CheckResult(name=name, passed=True)


def _fail(name: CheckName, detail: str) -> CheckResult:
    return CheckResult(name=name, passed=False, detail=detail)


def _output_blob(record: FrankRecord) -> str:
    parts = [record.idiomatic_uk]
    parts.extend(_unit_text(item) for item in record.units)
    parts.extend(item.gloss_uk for item in record.word_notes)
    return "\n".join(parts)


def _unit_text(item: SenseUnitTranslation) -> str:
    extra = item.word_for_word_uk or ""
    return f"{item.natural_uk}\n{extra}"


def _token_lemma(token: Token) -> str:
    return (token.reunited_lemma or token.lemma).casefold()


def _note_lemma(note: WordNote) -> str:
    return note.lemma.casefold()


def _calque_hit(blob: str, calques: tuple[str, ...]) -> str | None:
    folded = blob.casefold()
    return next((item for item in calques if item.casefold() in folded), None)


def _missing_gloss(token: Token, notes: dict[str, WordNote]) -> str:
    lemma = _token_lemma(token)
    note = notes.get(lemma)
    if note is None or not note.gloss_uk.strip():
        return lemma
    return ""
