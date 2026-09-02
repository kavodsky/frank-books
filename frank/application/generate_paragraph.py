"""One paragraph: cache, FAST retries, SMART escalation, advisory chrF (5.1–5.4)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from frank.domain.errors import ValidationExhausted
from frank.domain.model.annotation import GlossDecision, SenseUnit, Token
from frank.domain.model.book import BookStructure, Paragraph, ParagraphStatus, Sentence
from frank.domain.model.context import (
    ContextAssemblyConfig,
    ContextAssemblyRequest,
    PromptContext,
    RollingSentence,
)
from frank.domain.model.frank import (
    CheckName,
    CheckResult,
    FrankRecord,
    ModelTier,
    ParagraphOutput,
    QaResult,
    SentenceCheckSpec,
    ValidationConfig,
)
from frank.domain.model.termbase import StyleCard, Term, TermbaseSnapshot, TvForm
from frank.domain.ports.notifier import Notifier
from frank.domain.ports.repositories import (
    BookRepository,
    FrankRecordRepository,
    RunRepository,
    TermbaseRepository,
)
from frank.domain.ports.translator import (
    FrankGenerator,
    GenerationCache,
    ParagraphGenerationRequest,
)
from frank.domain.services.address_detect import (
    characters_in_tokens,
    is_dialogue_paragraph,
)
from frank.domain.services.context_assembly import assemble_context
from frank.domain.services.hard_sentences import hard_sentence_ids
from frank.domain.services.validation import failed_checks, validate_record


@dataclass(frozen=True)
class SessionBudget:
    max_passages: int
    max_minutes: float


@dataclass(frozen=True)
class GenerateConfig:
    session: SessionBudget
    context: ContextAssemblyConfig
    validation: ValidationConfig
    fast_retry_attempts: int
    backtranslation_sample_rate: float
    backtranslation_chrf_min: float
    hard_sentence_min_tokens: int
    scene_brief_every_paragraphs: int
    prompt_version: str
    models: str
    termbase_version: str
    instruction: str


@dataclass(frozen=True)
class GeneratePorts:
    open_books: Callable[[str], BookRepository]
    open_terms: Callable[[str], TermbaseRepository]
    open_records: Callable[[str], FrankRecordRepository]
    open_runs: Callable[[str], RunRepository]
    generator: FrankGenerator
    cache: GenerationCache
    notifier: Notifier
    score_chrf: Callable[[str, str], float]
    monotonic: Callable[[], float]


@dataclass
class SessionTally:
    passages_done: int = 0
    last_passage_id: str | None = None
    records: list[FrankRecord] = field(default_factory=list)
    scene_brief: str = ""


@dataclass(frozen=True)
class LoadedBook:
    slug: str
    structure: BookStructure
    snapshot: TermbaseSnapshot


class AnnotationView(BaseModel):
    model_config = ConfigDict(frozen=True)

    sentences: tuple[Sentence, ...]
    tokens: tuple[Token, ...]
    units: tuple[SenseUnit, ...]
    plan: tuple[GlossDecision, ...]


@dataclass(frozen=True)
class ParagraphWork:
    ports: GeneratePorts
    loaded: LoadedBook
    config: GenerateConfig
    tally: SessionTally


def termbase_version(terms: tuple[Term, ...]) -> str:
    """Stable hash of approved renderings; a termbase edit busts the cache."""
    lines = [f"{item.id}\t{item.lemma}\t{item.translation_uk}" for item in terms]
    blob = "\n".join(sorted(lines))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def generate_paragraph(
    work: ParagraphWork, paragraph: Paragraph, view: AnnotationView
) -> None:
    """Fill one paragraph from cache or FAST/SMART; persist COMPLETE records."""
    piece = _slice(paragraph.id, view)
    draft = _Draft(
        work=work,
        paragraph=paragraph,
        piece=piece,
        context=_context(work, paragraph, piece.tokens),
    )
    key = _cache_key(paragraph.hash, work.config, draft.context.rolling_window_text)
    cached = work.ports.cache.get_records(key)
    if cached is None:
        chosen, qa = _produce(draft)
        work.ports.cache.put_records(key, chosen)
    else:
        chosen, qa = cached, ()
    _store(draft, chosen, qa)
    work.tally.records.extend(chosen)
    _maybe_brief(work, paragraph)


class _Slice(BaseModel):
    model_config = ConfigDict(frozen=True)

    sentences: tuple[Sentence, ...]
    tokens: tuple[Token, ...]
    units: tuple[SenseUnit, ...]
    gloss_tokens: tuple[Token, ...]


@dataclass(frozen=True)
class _Draft:
    work: ParagraphWork
    paragraph: Paragraph
    piece: _Slice
    context: PromptContext


def _slice(paragraph_id: str, view: AnnotationView) -> _Slice:
    sentences = tuple(
        item for item in view.sentences if item.paragraph_id == paragraph_id
    )
    ids = {item.id for item in sentences}
    tokens = tuple(item for item in view.tokens if item.sentence_id in ids)
    units = tuple(item for item in view.units if item.sentence_id in ids)
    wanted = {item.token_id for item in view.plan if item.gloss}
    gloss = tuple(item for item in tokens if item.id in wanted)
    return _Slice(sentences=sentences, tokens=tokens, units=units, gloss_tokens=gloss)


def _context(
    work: ParagraphWork, paragraph: Paragraph, tokens: tuple[Token, ...]
) -> PromptContext:
    chapter = next(
        item
        for item in work.loaded.structure.chapters
        if item.id == paragraph.chapter_id
    )
    return assemble_context(
        ContextAssemblyRequest(
            paragraph=paragraph,
            tokens=tokens,
            terms=work.loaded.snapshot.terms,
            characters=work.loaded.snapshot.characters,
            address_pairs=work.loaded.snapshot.address_pairs,
            rolling_window=_window(work, paragraph),
            scene_brief=work.tally.scene_brief,
            chapter_summary=chapter.summary_uk or "",
            style_card=_style(work.loaded.slug, work.ports),
            task_instruction=work.config.instruction,
            config=work.config.context,
        )
    )


def _style(slug: str, ports: GeneratePorts) -> StyleCard | None:
    return ports.open_terms(slug).get_style_card(slug)


def _window(work: ParagraphWork, paragraph: Paragraph) -> tuple[RollingSentence, ...]:
    books = work.ports.open_books(work.loaded.slug)
    by_id = {item.sentence_id: item for item in work.tally.records}
    found: list[RollingSentence] = []
    for sentence in books.get_sentences(work.loaded.slug):
        if not _is_prior(work, sentence, paragraph):
            continue
        record = by_id.get(sentence.id)
        if record is None:
            continue
        found.append(
            RollingSentence(source=sentence.text, idiomatic_uk=record.idiomatic_uk)
        )
    return tuple(found)


def _is_prior(work: ParagraphWork, sentence: Sentence, paragraph: Paragraph) -> bool:
    paras = {item.id: item for item in work.loaded.structure.paragraphs}
    owner = paras.get(sentence.paragraph_id)
    if owner is None or owner.chapter_id != paragraph.chapter_id:
        return False
    return owner.index < paragraph.index


def _produce(
    draft: _Draft,
) -> tuple[tuple[FrankRecord, ...], tuple[QaResult, ...]]:
    records = draft.work.ports.generator.generate_fast(_request(draft, draft.piece, ""))
    records = _retry_fast(draft, records)
    smart_ids = _smart_ids(draft, records)
    if smart_ids:
        records = _apply_smart(draft, records, smart_ids)
    leftover = frozenset(_failures(draft, records))
    if leftover:
        raise ValidationExhausted(
            "validation exhausted: " + ", ".join(sorted(leftover))
        )
    return records, _backtranslate(draft, records, smart_ids)


def _retry_fast(
    draft: _Draft, records: tuple[FrankRecord, ...]
) -> tuple[FrankRecord, ...]:
    current = records
    attempts = 0
    while attempts < draft.work.config.fast_retry_attempts:
        failed = _failures(draft, current)
        if not failed:
            return current
        current = draft.work.ports.generator.generate_fast(
            _request(draft, draft.piece, _correction_text(failed))
        )
        attempts += 1
    return current


def _smart_ids(draft: _Draft, records: tuple[FrankRecord, ...]) -> frozenset[str]:
    hard = hard_sentence_ids(
        draft.piece.sentences,
        draft.piece.tokens,
        draft.work.loaded.snapshot.terms,
        draft.work.config.hard_sentence_min_tokens,
    )
    return hard | frozenset(_failures(draft, records))


def _apply_smart(
    draft: _Draft,
    records: tuple[FrankRecord, ...],
    smart_ids: frozenset[str],
) -> tuple[FrankRecord, ...]:
    subset = _Slice(
        sentences=tuple(item for item in draft.piece.sentences if item.id in smart_ids),
        tokens=tuple(
            item for item in draft.piece.tokens if item.sentence_id in smart_ids
        ),
        units=tuple(
            item for item in draft.piece.units if item.sentence_id in smart_ids
        ),
        gloss_tokens=tuple(
            item for item in draft.piece.gloss_tokens if item.sentence_id in smart_ids
        ),
    )
    smart = draft.work.ports.generator.generate_smart(_request(draft, subset, ""))
    by_id = {item.sentence_id: item for item in records}
    for item in smart:
        by_id[item.sentence_id] = item
    return tuple(by_id[item.id] for item in draft.piece.sentences if item.id in by_id)


def _request(
    draft: _Draft, piece: _Slice, correction: str
) -> ParagraphGenerationRequest:
    return ParagraphGenerationRequest(
        context=draft.context,
        sentences=piece.sentences,
        sense_units=piece.units,
        gloss_tokens=piece.gloss_tokens,
        lang=draft.work.loaded.structure.book.lang,
        correction=correction,
    )


def _failures(
    draft: _Draft, records: tuple[FrankRecord, ...]
) -> dict[str, tuple[CheckResult, ...]]:
    by_id = {item.sentence_id: item for item in records}
    found: dict[str, tuple[CheckResult, ...]] = {}
    for sentence in draft.piece.sentences:
        record = by_id.get(sentence.id)
        if record is None:
            found[sentence.id] = (
                CheckResult(
                    name=CheckName.SCHEMA, passed=False, detail="missing record"
                ),
            )
            continue
        checks = failed_checks(validate_record(record, _spec(draft, sentence.id)))
        if checks:
            found[sentence.id] = checks
    return found


def _spec(draft: _Draft, sentence_id: str) -> SentenceCheckSpec:
    sentence = next(item for item in draft.piece.sentences if item.id == sentence_id)
    tokens = tuple(
        item for item in draft.piece.tokens if item.sentence_id == sentence_id
    )
    return SentenceCheckSpec(
        sentence=sentence,
        sense_units=tuple(
            item for item in draft.piece.units if item.sentence_id == sentence_id
        ),
        gloss_tokens=tuple(
            item for item in draft.piece.gloss_tokens if item.sentence_id == sentence_id
        ),
        terms=_terms_for(tokens, draft.work.loaded.snapshot.terms),
        tv_form=_tv(draft.paragraph, tokens, draft.work.loaded.snapshot),
        config=draft.work.config.validation,
    )


def _terms_for(tokens: tuple[Token, ...], terms: tuple[Term, ...]) -> tuple[Term, ...]:
    keys = _token_keys(tokens)
    return tuple(item for item in terms if _term_hit(item, keys))


def _token_keys(tokens: tuple[Token, ...]) -> set[str]:
    keys: set[str] = set()
    for token in tokens:
        keys.add(token.lemma.casefold())
        keys.add(token.surface.casefold())
        if token.reunited_lemma:
            keys.add(token.reunited_lemma.casefold())
    return keys


def _term_hit(term: Term, keys: set[str]) -> bool:
    if term.lemma.casefold() in keys:
        return True
    return any(form.casefold() in keys for form in term.surface_forms)


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


def _correction_text(failed: dict[str, tuple[CheckResult, ...]]) -> str:
    lines: list[str] = []
    for sentence_id, checks in failed.items():
        for check in checks:
            lines.append(f"{sentence_id}: {check.name.value}: {check.detail}")
    return "\n".join(lines)


def _backtranslate(
    draft: _Draft,
    records: tuple[FrankRecord, ...],
    smart_ids: frozenset[str],
) -> tuple[QaResult, ...]:
    found: list[QaResult] = []
    for record in records:
        if not _sample(
            record, draft.work.config.backtranslation_sample_rate, smart_ids
        ):
            continue
        sentence = next(
            item for item in draft.piece.sentences if item.id == record.sentence_id
        )
        hyp = draft.work.ports.generator.back_translate(
            record.idiomatic_uk,
            draft.work.loaded.structure.book.lang,
            record.tier,
        )
        score = draft.work.ports.score_chrf(hyp, sentence.text)
        found.append(
            QaResult(
                id=f"{draft.paragraph.id}-chrf-{record.sentence_id}",
                paragraph_id=draft.paragraph.id,
                check_name="back_translation",
                passed=score >= draft.work.config.backtranslation_chrf_min,
                detail=f"{score:.1f}",
                attempt=0,
            )
        )
    return tuple(found)


def _sample(record: FrankRecord, rate: float, smart_ids: frozenset[str]) -> bool:
    if record.tier is ModelTier.SMART or record.sentence_id in smart_ids:
        return True
    digest = hashlib.sha256(record.sentence_id.encode("utf-8")).digest()
    return digest[0] / 255 < rate


def _store(
    draft: _Draft,
    records: tuple[FrankRecord, ...],
    qa: tuple[QaResult, ...],
) -> None:
    draft.work.ports.open_records(draft.work.loaded.slug).save_paragraph_output(
        draft.work.loaded.slug,
        ParagraphOutput(
            paragraph_id=draft.paragraph.id,
            records=records,
            qa=qa,
            status=ParagraphStatus.COMPLETE,
        ),
    )


def _maybe_brief(work: ParagraphWork, paragraph: Paragraph) -> None:
    every = work.config.scene_brief_every_paragraphs
    if paragraph.index % every != 0:
        return
    source = _chapter_source(work, paragraph)
    key = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    hit = work.ports.cache.get_brief(key)
    if hit is None:
        hit = work.ports.generator.update_scene_brief(
            source, work.loaded.structure.book.lang
        )
        work.ports.cache.put_brief(key, hit)
    work.tally.scene_brief = hit


def _chapter_source(work: ParagraphWork, paragraph: Paragraph) -> str:
    rows = [
        item
        for item in work.loaded.structure.paragraphs
        if item.chapter_id == paragraph.chapter_id and item.index <= paragraph.index
    ]
    rows.sort(key=lambda item: item.index)
    return "\n".join(item.raw_text for item in rows)


def _cache_key(paragraph_hash: str, config: GenerateConfig, rolling: str) -> str:
    blob = "\n".join(
        (
            paragraph_hash,
            config.prompt_version,
            config.models,
            config.termbase_version,
            rolling,
        )
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
