"""Re-run stored FrankRecords through 5.2 predicates (roadmap 7.2)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from frank.application.generate_paragraph import AnnotationView
from frank.domain.model.annotation import Token
from frank.domain.model.book import BookStructure, Paragraph, Sentence
from frank.domain.model.frank import (
    CheckName,
    CheckResult,
    FrankRecord,
    QaResult,
    SentenceCheckSpec,
    ValidationConfig,
)
from frank.domain.model.termbase import Term, TermbaseSnapshot, TvForm
from frank.domain.ports.repositories import (
    BookRepository,
    FrankRecordRepository,
    TermbaseRepository,
)
from frank.domain.services.address_detect import (
    characters_in_tokens,
    is_dialogue_paragraph,
)
from frank.domain.services.validation import lemmas_present, named_check


@dataclass(frozen=True)
class CheckPorts:
    open_books: Callable[[str], BookRepository]
    open_terms: Callable[[str], TermbaseRepository]
    open_records: Callable[[str], FrankRecordRepository]


class StoredCheckReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    failed_count: int
    detail: str


class ChapterCheckRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    chapter_index: int
    name: CheckName
    validation: ValidationConfig


@dataclass(frozen=True)
class _Loaded:
    structure: BookStructure
    view: AnnotationView
    snapshot: TermbaseSnapshot


def check_lemmas(ports: CheckPorts, slug: str) -> StoredCheckReport:
    tokens = ports.open_books(slug).get_tokens(slug)
    return _from_result(lemmas_present(tokens))


def check_named_records(
    ports: CheckPorts, request: ChapterCheckRequest
) -> StoredCheckReport:
    failed = tuple(
        f"{record.sentence_id}: {hit.detail}"
        for record, spec in _pairs(ports, request)
        if not (hit := named_check(record, spec, request.name)).passed
    )
    return _summary(request.name, failed)


def check_back_translation(
    ports: CheckPorts, slug: str, chapter_index: int
) -> StoredCheckReport:
    failed = tuple(
        f"{item.paragraph_id}: {item.detail}"
        for item in _chapter_qa(ports, slug, chapter_index)
        if not item.passed
    )
    return _summary(CheckName.BACK_TRANSLATION, failed)


def _summary(name: CheckName, failed: tuple[str, ...]) -> StoredCheckReport:
    if not failed:
        return StoredCheckReport(
            name=name.value, passed=True, failed_count=0, detail=""
        )
    return StoredCheckReport(
        name=name.value,
        passed=False,
        failed_count=len(failed),
        detail="; ".join(failed[:8]),
    )


def _from_result(result: CheckResult) -> StoredCheckReport:
    return StoredCheckReport(
        name=result.name.value,
        passed=result.passed,
        failed_count=0 if result.passed else 1,
        detail=result.detail,
    )


def _pairs(
    ports: CheckPorts, request: ChapterCheckRequest
) -> tuple[tuple[FrankRecord, SentenceCheckSpec], ...]:
    loaded = _load(ports, request.slug)
    wanted = _chapter_sentence_ids(
        loaded.structure, loaded.view.sentences, request.chapter_index
    )
    found: list[tuple[FrankRecord, SentenceCheckSpec]] = []
    for record in ports.open_records(request.slug).get_records(request.slug):
        if record.sentence_id not in wanted:
            continue
        found.append((record, _spec(record.sentence_id, loaded, request.validation)))
    return tuple(found)


def _load(ports: CheckPorts, slug: str) -> _Loaded:
    books = ports.open_books(slug)
    terms = ports.open_terms(slug)
    return _Loaded(
        structure=books.get_structure(slug),
        view=AnnotationView(
            sentences=books.get_sentences(slug),
            tokens=books.get_tokens(slug),
            units=books.get_sense_units(slug),
            plan=books.get_gloss_plan(slug),
        ),
        snapshot=TermbaseSnapshot(
            terms=terms.get_terms(slug),
            characters=terms.get_characters(slug),
            address_pairs=terms.get_address_pairs(slug),
        ),
    )


def _chapter_qa(
    ports: CheckPorts, slug: str, chapter_index: int
) -> tuple[QaResult, ...]:
    structure = ports.open_books(slug).get_structure(slug)
    wanted = _chapter_paragraph_ids(structure, chapter_index)
    return tuple(
        item
        for item in ports.open_records(slug).get_qa(slug)
        if item.paragraph_id in wanted and item.check_name == CheckName.BACK_TRANSLATION
    )


def _chapter_paragraph_ids(structure: BookStructure, chapter_index: int) -> set[str]:
    chapters = {item.id for item in structure.chapters if item.index == chapter_index}
    return {item.id for item in structure.paragraphs if item.chapter_id in chapters}


def _chapter_sentence_ids(
    structure: BookStructure, sentences: tuple[Sentence, ...], chapter_index: int
) -> set[str]:
    paragraphs = _chapter_paragraph_ids(structure, chapter_index)
    return {item.id for item in sentences if item.paragraph_id in paragraphs}


def _spec(
    sentence_id: str, loaded: _Loaded, config: ValidationConfig
) -> SentenceCheckSpec:
    sentence = next(item for item in loaded.view.sentences if item.id == sentence_id)
    tokens = tuple(
        item for item in loaded.view.tokens if item.sentence_id == sentence_id
    )
    paragraph = next(
        item for item in loaded.structure.paragraphs if item.id == sentence.paragraph_id
    )
    gloss_ids = {item.token_id for item in loaded.view.plan if item.gloss}
    return SentenceCheckSpec(
        sentence=sentence,
        sense_units=tuple(
            item for item in loaded.view.units if item.sentence_id == sentence_id
        ),
        gloss_tokens=tuple(item for item in tokens if item.id in gloss_ids),
        terms=_terms_for(tokens, loaded.snapshot.terms),
        tv_form=_tv(paragraph, tokens, loaded.snapshot),
        config=config,
    )


def _terms_for(tokens: tuple[Token, ...], terms: tuple[Term, ...]) -> tuple[Term, ...]:
    keys = {item.lemma.casefold() for item in tokens}
    keys.update(item.surface.casefold() for item in tokens)
    keys.update(
        item.reunited_lemma.casefold() for item in tokens if item.reunited_lemma
    )
    return tuple(
        item
        for item in terms
        if item.lemma.casefold() in keys
        or any(form.casefold() in keys for form in item.surface_forms)
    )


def _tv(
    paragraph: Paragraph, tokens: tuple[Token, ...], snapshot: TermbaseSnapshot
) -> TvForm | None:
    if not is_dialogue_paragraph(paragraph):
        return None
    involved = {item.id for item in characters_in_tokens(tokens, snapshot.characters)}
    forms = [
        item.tv_form
        for item in snapshot.address_pairs
        if item.speaker_id in involved and item.addressee_id in involved
    ]
    if not forms or any(item is TvForm.MIXED for item in forms):
        return None
    first = forms[0]
    if any(item is not first for item in forms):
        return None
    return first
