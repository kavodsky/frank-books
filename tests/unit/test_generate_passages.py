"""Session budget, cache skip, and termbase-by-construction (roadmap 5.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from frank.application.generate_paragraph import (
    GenerateConfig,
    GeneratePorts,
    SessionBudget,
    termbase_version,
)
from frank.application.generate_passages import (
    StatusPorts,
    book_generation_status,
    generate_chapter,
    generate_passages,
    render_status,
)
from frank.domain.errors import TermbaseNotApproved, ValidationExhausted
from frank.domain.model.annotation import (
    GlossDecision,
    GlossReason,
    Morphology,
    SenseUnit,
    Token,
)
from frank.domain.model.book import (
    Book,
    BookStatus,
    BookStructure,
    Chapter,
    Paragraph,
    ParagraphStatus,
    Passage,
    Sentence,
)
from frank.domain.model.context import ContextAssemblyConfig
from frank.domain.model.frank import (
    FrankRecord,
    ModelTier,
    ParagraphOutput,
    QaResult,
    SenseUnitTranslation,
    SentenceCheckSpec,
    ValidationConfig,
    WordNote,
)
from frank.domain.model.run import Run, RunFailure, RunStatus, RunTally
from frank.domain.model.termbase import Term, TermKind
from frank.domain.ports.translator import ParagraphGenerationRequest
from frank.domain.services.validation import failed_checks, validate_record

_SLUG = "oliver-de"


@dataclass
class CountingGenerator:
    calls: int = 0
    smart_calls: int = 0

    def generate_fast(
        self, request: ParagraphGenerationRequest
    ) -> tuple[FrankRecord, ...]:
        self.calls += 1
        return tuple(_good(item, request) for item in request.sentences)

    def generate_smart(
        self, request: ParagraphGenerationRequest
    ) -> tuple[FrankRecord, ...]:
        self.calls += 1
        self.smart_calls += 1
        return tuple(_good(item, request) for item in request.sentences)

    def back_translate(self, text: str, source_lang: str, producer: ModelTier) -> str:
        self.calls += 1
        _ = text, source_lang, producer
        return "Oliver kommt."

    def update_scene_brief(self, source_so_far: str, lang: str) -> str:
        self.calls += 1
        _ = source_so_far, lang
        return "Олівер іде."


@dataclass
class MemoryCache:
    records: dict[str, tuple[FrankRecord, ...]] = field(default_factory=dict)
    briefs: dict[str, str] = field(default_factory=dict)

    def get_records(self, key: str) -> tuple[FrankRecord, ...] | None:
        return self.records.get(key)

    def put_records(self, key: str, records: tuple[FrankRecord, ...]) -> None:
        self.records[key] = records

    def get_brief(self, key: str) -> str | None:
        return self.briefs.get(key)

    def put_brief(self, key: str, brief: str) -> None:
        self.briefs[key] = brief


@dataclass
class FakeNotifier:
    seen: list[Run] = field(default_factory=list)

    def notify_completion(self, run: Run) -> None:
        self.seen.append(run)


@dataclass
class FakeRuns:
    stored: dict[str, Run] = field(default_factory=dict)
    n: int = 0

    def start(self, book_id: str) -> Run:
        self.n += 1
        run = Run(
            id=f"run-{self.n}",
            book_id=book_id,
            started_at=datetime.now(UTC),
            ended_at=None,
            status=RunStatus.RUNNING,
            passages_done=0,
            last_passage_id=None,
            error_class=None,
            error_msg=None,
        )
        self.stored[run.id] = run
        return run

    def record_success(self, tally: RunTally) -> Run:
        run = self.stored[tally.run_id]
        closed = run.model_copy(
            update={
                "status": RunStatus.COMPLETED,
                "ended_at": datetime.now(UTC),
                "passages_done": tally.passages_done,
                "last_passage_id": tally.last_passage_id,
            }
        )
        self.stored[closed.id] = closed
        return closed

    def record_failure(self, failure: RunFailure) -> Run:
        run = self.stored[failure.tally.run_id]
        closed = run.model_copy(
            update={
                "status": RunStatus.FAILED,
                "ended_at": datetime.now(UTC),
                "passages_done": failure.tally.passages_done,
                "last_passage_id": failure.tally.last_passage_id,
                "error_class": failure.error.error_class,
                "error_msg": failure.error.message,
            }
        )
        self.stored[closed.id] = closed
        return closed

    def get(self, run_id: str) -> Run:
        return self.stored[run_id]

    def list_for_book(self, book_id: str) -> tuple[Run, ...]:
        return tuple(item for item in self.stored.values() if item.book_id == book_id)


@dataclass
class FakeStore:
    structure: BookStructure
    sentences: tuple[Sentence, ...]
    tokens: tuple[Token, ...]
    units: tuple[SenseUnit, ...]
    plan: tuple[GlossDecision, ...]
    terms: tuple[Term, ...]
    records: list[FrankRecord] = field(default_factory=list)
    qa: list[QaResult] = field(default_factory=list)

    def get_structure(self, slug: str) -> BookStructure:
        _ = slug
        return self.structure

    def get_sentences(self, slug: str) -> tuple[Sentence, ...]:
        _ = slug
        return self.sentences

    def get_tokens(self, slug: str) -> tuple[Token, ...]:
        _ = slug
        return self.tokens

    def get_sense_units(self, slug: str) -> tuple[SenseUnit, ...]:
        _ = slug
        return self.units

    def get_gloss_plan(self, slug: str) -> tuple[GlossDecision, ...]:
        _ = slug
        return self.plan

    def get_terms(self, slug: str) -> tuple[Term, ...]:
        _ = slug
        return self.terms

    def get_characters(self, slug: str) -> tuple:
        _ = slug
        return ()

    def get_address_pairs(self, slug: str) -> tuple:
        _ = slug
        return ()

    def get_style_card(self, slug: str):
        _ = slug
        return

    def save_paragraph_output(self, slug: str, output: ParagraphOutput) -> None:
        _ = slug
        gone = {item.sentence_id for item in output.records}
        self.records = [item for item in self.records if item.sentence_id not in gone]
        self.records.extend(output.records)
        self.qa = [item for item in self.qa if item.paragraph_id != output.paragraph_id]
        self.qa.extend(output.qa)
        paras = []
        for paragraph in self.structure.paragraphs:
            if paragraph.id == output.paragraph_id:
                paras.append(
                    paragraph.model_copy(update={"status": ParagraphStatus.COMPLETE})
                )
            else:
                paras.append(paragraph)
        self.structure = self.structure.model_copy(update={"paragraphs": tuple(paras)})

    def get_records(self, slug: str) -> tuple[FrankRecord, ...]:
        _ = slug
        return tuple(self.records)

    def get_qa(self, slug: str) -> tuple[QaResult, ...]:
        _ = slug
        return tuple(self.qa)


def _term() -> Term:
    return Term(
        id="t-oliver",
        book_id="b",
        kind=TermKind.PERSON,
        surface_forms=("Oliver",),
        lemma="Oliver",
        translation_uk="Олівер",
        approved=True,
    )


def _book(passages: int = 4) -> FakeStore:
    return _store(passages, _term())


def _pending_book() -> FakeStore:
    pending = _term().model_copy(update={"approved": False})
    return _store(4, pending)


def _store(passages: int, term: Term) -> FakeStore:
    book = Book(
        id="b",
        slug=_SLUG,
        lang="de",
        title="Oliver",
        author="",
        source_url="file.txt",
        license_note="",
        status=BookStatus.INGESTED,
    )
    chapter = Chapter(
        id="c1", book_id="b", index=1, title="I", summary_uk="Олівер іде."
    )
    found_passages: list[Passage] = []
    paragraphs: list[Paragraph] = []
    sentences: list[Sentence] = []
    tokens: list[Token] = []
    units: list[SenseUnit] = []
    plan: list[GlossDecision] = []
    for index in range(1, passages + 1):
        passage = Passage(id=f"pass-{index}", chapter_id="c1", index=index)
        found_passages.append(passage)
        paragraph = Paragraph(
            id=f"p{index}",
            chapter_id="c1",
            passage_id=passage.id,
            index=index,
            raw_text="Oliver kommt.",
            hash=f"h{index}",
            status=ParagraphStatus.RAW,
        )
        paragraphs.append(paragraph)
        sid = f"s{index}"
        sentences.append(
            Sentence(id=sid, paragraph_id=paragraph.id, index=1, text="Oliver kommt.")
        )
        token = Token(
            id=f"{sid}-t1",
            sentence_id=sid,
            index=1,
            surface="Oliver",
            lemma="Oliver",
            upos="PROPN",
            morph=Morphology(),
        )
        tokens.append(token)
        units.append(
            SenseUnit(
                id=f"{sid}-u1",
                sentence_id=sid,
                index=1,
                start_index=1,
                end_index=3,
            )
        )
        plan.append(
            GlossDecision(
                token_id=token.id,
                gloss=True,
                reason=GlossReason.FIRST_OCCURRENCE,
            )
        )
    return FakeStore(
        structure=BookStructure(
            book=book,
            chapters=(chapter,),
            paragraphs=tuple(paragraphs),
            passages=tuple(found_passages),
        ),
        sentences=tuple(sentences),
        tokens=tuple(tokens),
        units=tuple(units),
        plan=tuple(plan),
        terms=(term,),
    )


class BrokenFast(CountingGenerator):
    def generate_fast(
        self, request: ParagraphGenerationRequest
    ) -> tuple[FrankRecord, ...]:
        self.calls += 1
        return tuple(_record(item.id, "ы", request) for item in request.sentences)


class DeadGenerator(CountingGenerator):
    def generate_fast(
        self, request: ParagraphGenerationRequest
    ) -> tuple[FrankRecord, ...]:
        self.calls += 1
        return tuple(_record(item.id, "ы", request) for item in request.sentences)

    def generate_smart(
        self, request: ParagraphGenerationRequest
    ) -> tuple[FrankRecord, ...]:
        self.calls += 1
        self.smart_calls += 1
        return tuple(_record(item.id, "ы", request) for item in request.sentences)


def _good(sentence: Sentence, request: ParagraphGenerationRequest) -> FrankRecord:
    return _record(sentence.id, "Олівер іде.", request)


def _record(
    sentence_id: str, idiomatic: str, request: ParagraphGenerationRequest
) -> FrankRecord:
    units = tuple(
        item for item in request.sense_units if item.sentence_id == sentence_id
    )
    gloss = tuple(
        item for item in request.gloss_tokens if item.sentence_id == sentence_id
    )
    return FrankRecord(
        sentence_id=sentence_id,
        units=tuple(
            SenseUnitTranslation(
                source_span=(item.start_index, item.end_index),
                natural_uk="Олівер іде",
            )
            for item in units
        ),
        idiomatic_uk=idiomatic,
        word_notes=tuple(_note(item) for item in gloss),
        tier=ModelTier.FAST,
    )


def _note(token: Token) -> WordNote:
    return WordNote(
        surface=token.surface,
        lemma=token.reunited_lemma or token.lemma,
        morph_note_uk="",
        gloss_uk="Олівер",
    )


def _config(store: FakeStore) -> GenerateConfig:
    return GenerateConfig(
        session=SessionBudget(max_passages=3, max_minutes=60),
        context=ContextAssemblyConfig(
            max_tokens=1800,
            rolling_window_sentences=3,
            scene_brief_sentences=2,
            style_card_digest_lines=5,
        ),
        validation=ValidationConfig(
            length_ratio_min=0.6,
            length_ratio_max=2.0,
            ukrainian_marker_min_chars=20,
            calques=(),
        ),
        fast_retry_attempts=2,
        backtranslation_sample_rate=0.0,
        backtranslation_chrf_min=40,
        hard_sentence_min_tokens=99,
        scene_brief_every_paragraphs=99,
        prompt_version="pv1",
        models="fast|smart",
        termbase_version=termbase_version(store.terms),
        instruction="You produce Ilya Frank data for one paragraph.",
    )


def _ports(
    store: FakeStore,
    generator: CountingGenerator,
    cache: MemoryCache,
    runs: FakeRuns,
) -> GeneratePorts:
    return GeneratePorts(
        open_books=lambda _slug: store,
        open_terms=lambda _slug: store,
        open_records=lambda _slug: store,
        open_runs=lambda _slug: runs,
        generator=generator,
        cache=cache,
        notifier=FakeNotifier(),
        score_chrf=lambda _hyp, _ref: 100.0,
        monotonic=lambda: 0.0,
    )


@pytest.mark.unit
def test_budget_of_three_passages_stops_cleanly() -> None:
    store = _book()
    generator = CountingGenerator()
    report = generate_passages(
        _ports(store, generator, MemoryCache(), FakeRuns()), _SLUG, _config(store)
    )
    assert report.passages_done == 3
    assert report.passages_total == 4
    assert generator.calls == 3
    complete = [
        item
        for item in store.structure.paragraphs
        if item.status is ParagraphStatus.COMPLETE
    ]
    assert len(complete) == 3


@pytest.mark.unit
def test_rerun_skips_llm_for_finished_paragraphs() -> None:
    store = _book(passages=3)
    generator = CountingGenerator()
    cache = MemoryCache()
    runs = FakeRuns()
    ports = _ports(store, generator, cache, runs)
    config = _config(store)
    generate_passages(ports, _SLUG, config)
    first = generator.calls
    generate_passages(ports, _SLUG, config)
    assert first == 3
    assert generator.calls == first


@pytest.mark.unit
def test_next_session_continues_unfinished_passages() -> None:
    store = _book()
    generator = CountingGenerator()
    ports = _ports(store, generator, MemoryCache(), FakeRuns())
    config = _config(store)
    generate_passages(ports, _SLUG, config)
    generate_passages(ports, _SLUG, config)
    assert generator.calls == 4


@pytest.mark.unit
def test_cache_skips_llm_when_paragraph_is_still_raw() -> None:
    store = _book(passages=1)
    generator = CountingGenerator()
    cache = MemoryCache()
    ports = _ports(store, generator, cache, FakeRuns())
    generate_passages(ports, _SLUG, _config(store))
    store.structure = store.structure.model_copy(
        update={
            "paragraphs": tuple(
                item.model_copy(update={"status": ParagraphStatus.RAW})
                for item in store.structure.paragraphs
            )
        }
    )
    generate_passages(ports, _SLUG, _config(store))
    assert generator.calls == 1


@pytest.mark.unit
def test_termbase_has_zero_violations_by_construction() -> None:
    store = _book(passages=1)
    generate_passages(
        _ports(store, CountingGenerator(), MemoryCache(), FakeRuns()),
        _SLUG,
        _config(store),
    )
    record = store.records[0]
    spec = SentenceCheckSpec(
        sentence=store.sentences[0],
        sense_units=tuple(
            item for item in store.units if item.sentence_id == record.sentence_id
        ),
        gloss_tokens=tuple(
            item for item in store.tokens if item.sentence_id == record.sentence_id
        ),
        terms=store.terms,
        tv_form=None,
        config=_config(store).validation,
    )
    assert failed_checks(validate_record(record, spec)) == ()
    assert "Олівер" in record.idiomatic_uk


@pytest.mark.unit
def test_unapproved_termbase_blocks_generation() -> None:
    store = _pending_book()
    with pytest.raises(TermbaseNotApproved):
        generate_passages(
            _ports(store, CountingGenerator(), MemoryCache(), FakeRuns()),
            _SLUG,
            _config(store),
        )


@pytest.mark.unit
def test_smart_repairs_after_fast_retries() -> None:
    store = _book(passages=1)
    generator = BrokenFast()
    generate_passages(
        _ports(store, generator, MemoryCache(), FakeRuns()), _SLUG, _config(store)
    )
    assert generator.smart_calls == 1
    assert store.records[0].idiomatic_uk == "Олівер іде."


@pytest.mark.unit
def test_validation_exhausted_when_smart_also_fails() -> None:
    store = _book(passages=1)

    with pytest.raises(ValidationExhausted):
        generate_passages(
            _ports(store, DeadGenerator(), MemoryCache(), FakeRuns()),
            _SLUG,
            _config(store),
        )


@pytest.mark.unit
def test_status_reports_pace_after_a_completed_run() -> None:
    store = _book()
    runs = FakeRuns()
    generate_passages(
        _ports(store, CountingGenerator(), MemoryCache(), runs), _SLUG, _config(store)
    )
    run = next(iter(runs.stored.values()))
    runs.stored[run.id] = run.model_copy(
        update={
            "ended_at": run.started_at + timedelta(hours=1),
            "passages_done": 3,
        }
    )
    report = book_generation_status(
        StatusPorts(open_books=lambda _s: store, open_runs=lambda _s: runs), _SLUG
    )
    assert report.passages_done == 3
    assert report.passages_total == 4
    assert report.passages_per_hour == 3.0
    assert report.eta_hours == pytest.approx(1 / 3)
    text = render_status(report)
    assert "3/4" in text
    assert "3.0" in text
    assert "0.3 h" in text


@pytest.mark.unit
def test_generate_chapter_only_fills_that_chapter() -> None:
    store = _two_chapters()
    generator = CountingGenerator()
    report = generate_chapter(
        _ports(store, generator, MemoryCache(), FakeRuns()),
        _SLUG,
        _config(store),
        1,
    )
    assert generator.calls == 2
    done = {
        item.id
        for item in store.structure.paragraphs
        if item.status is ParagraphStatus.COMPLETE
    }
    assert done == {"p1", "p2"}
    leftover = {
        item.id
        for item in store.structure.paragraphs
        if item.status is ParagraphStatus.RAW
    }
    assert leftover == {"c2-p1", "c2-p2"}
    assert report.session_passages == 2


def _two_chapters() -> FakeStore:
    first = _store(2, _term())
    extra_passages = []
    extra_paras = []
    extra_sentences = []
    extra_tokens = []
    extra_units = []
    extra_plan = []
    chapter = Chapter(id="c2", book_id="b", index=2, title="II", summary_uk="")
    for index in (1, 2):
        passage = Passage(id=f"c2-pass-{index}", chapter_id="c2", index=index)
        extra_passages.append(passage)
        paragraph = Paragraph(
            id=f"c2-p{index}",
            chapter_id="c2",
            passage_id=passage.id,
            index=index,
            raw_text="Oliver kommt.",
            hash=f"h2{index}",
            status=ParagraphStatus.RAW,
        )
        extra_paras.append(paragraph)
        sid = f"c2-s{index}"
        extra_sentences.append(
            Sentence(id=sid, paragraph_id=paragraph.id, index=1, text="Oliver kommt.")
        )
        token = Token(
            id=f"{sid}-t1",
            sentence_id=sid,
            index=1,
            surface="Oliver",
            lemma="Oliver",
            upos="PROPN",
            morph=Morphology(),
        )
        extra_tokens.append(token)
        extra_units.append(
            SenseUnit(
                id=f"{sid}-u1", sentence_id=sid, index=1, start_index=1, end_index=3
            )
        )
        extra_plan.append(
            GlossDecision(
                token_id=token.id, gloss=True, reason=GlossReason.FIRST_OCCURRENCE
            )
        )
    structure = first.structure.model_copy(
        update={
            "chapters": first.structure.chapters + (chapter,),
            "paragraphs": first.structure.paragraphs + tuple(extra_paras),
            "passages": first.structure.passages + tuple(extra_passages),
        }
    )
    return FakeStore(
        structure=structure,
        sentences=first.sentences + tuple(extra_sentences),
        tokens=first.tokens + tuple(extra_tokens),
        units=first.units + tuple(extra_units),
        plan=first.plan + tuple(extra_plan),
        terms=first.terms,
    )
