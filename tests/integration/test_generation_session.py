"""SQLite generation session: budget, resume, termbase (roadmap 5.5)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from frank.application.generate_paragraph import (
    GenerateConfig,
    GeneratePorts,
    SessionBudget,
    termbase_version,
)
from frank.application.generate_passages import generate_passages
from frank.domain.model.annotation import (
    Annotation,
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
    SenseUnitTranslation,
    ValidationConfig,
    WordNote,
)
from frank.domain.model.run import Run
from frank.domain.model.termbase import Term, TermKind
from frank.domain.ports.translator import ParagraphGenerationRequest
from frank.infrastructure.persistence.cache import StepCache
from frank.infrastructure.persistence.generation_cache import StepGenerationCache
from frank.infrastructure.persistence.repositories import (
    SqliteBookRepository,
    SqliteRunRepository,
)
from frank.infrastructure.persistence.tables import create_book_db

_SLUG = "oliver-de"


@dataclass
class CountingGenerator:
    calls: int = 0

    def generate_fast(
        self, request: ParagraphGenerationRequest
    ) -> tuple[FrankRecord, ...]:
        self.calls += 1
        return tuple(_good(item, request) for item in request.sentences)

    def generate_smart(
        self, request: ParagraphGenerationRequest
    ) -> tuple[FrankRecord, ...]:
        self.calls += 1
        return tuple(_good(item, request) for item in request.sentences)

    def back_translate(self, text: str, source_lang: str, producer: ModelTier) -> str:
        _ = text, source_lang, producer
        return "Oliver kommt."

    def update_scene_brief(self, source_so_far: str, lang: str) -> str:
        _ = source_so_far, lang
        return "Олівер іде."


@dataclass
class FakeNotifier:
    seen: list[Run] = field(default_factory=list)

    def notify_completion(self, run: Run) -> None:
        self.seen.append(run)


def _good(sentence: Sentence, request: ParagraphGenerationRequest) -> FrankRecord:
    units = tuple(
        item for item in request.sense_units if item.sentence_id == sentence.id
    )
    gloss = tuple(
        item for item in request.gloss_tokens if item.sentence_id == sentence.id
    )
    return FrankRecord(
        sentence_id=sentence.id,
        units=tuple(
            SenseUnitTranslation(
                source_span=(item.start_index, item.end_index),
                natural_uk="Олівер іде",
            )
            for item in units
        ),
        idiomatic_uk="Олівер іде.",
        word_notes=tuple(
            WordNote(
                surface=item.surface,
                lemma=item.reunited_lemma or item.lemma,
                morph_note_uk="",
                gloss_uk="Олівер",
            )
            for item in gloss
        ),
        tier=ModelTier.FAST,
    )


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


def _seed(engine) -> None:
    books = SqliteBookRepository(engine)
    chapter = Chapter(
        id="c1", book_id="b", index=1, title="I", summary_uk="Олівер іде."
    )
    passages: list[Passage] = []
    paragraphs: list[Paragraph] = []
    sentences: list[Sentence] = []
    tokens: list[Token] = []
    units: list[SenseUnit] = []
    plan: list[GlossDecision] = []
    for index in range(1, 5):
        passage = Passage(id=f"pass-{index}", chapter_id="c1", index=index)
        passages.append(passage)
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
                id=f"{sid}-u1", sentence_id=sid, index=1, start_index=1, end_index=3
            )
        )
        plan.append(
            GlossDecision(
                token_id=token.id, gloss=True, reason=GlossReason.FIRST_OCCURRENCE
            )
        )
    structure = BookStructure(
        book=Book(
            id="b",
            slug=_SLUG,
            lang="de",
            title="Oliver",
            author="",
            source_url="file.txt",
            license_note="",
            status=BookStatus.INGESTED,
        ),
        chapters=(chapter,),
        paragraphs=tuple(paragraphs),
        passages=tuple(passages),
    )
    books.save_structure(structure)
    books.replace_passages(_SLUG, structure)
    books.replace_annotation(
        _SLUG,
        Annotation(
            sentences=tuple(sentences),
            tokens=tuple(tokens),
            sense_units=tuple(units),
            gloss_plan=tuple(plan),
        ),
    )
    books.replace_terms(_SLUG, (_term(),))


def _config(terms: tuple[Term, ...]) -> GenerateConfig:
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
        termbase_version=termbase_version(terms),
        instruction="You produce Ilya Frank data for one paragraph.",
    )


def _ports(engine, generator: CountingGenerator, tmp_path) -> GeneratePorts:
    books = SqliteBookRepository(engine)
    runs = SqliteRunRepository(engine)
    return GeneratePorts(
        open_books=lambda _slug: books,
        open_terms=lambda _slug: books,
        open_records=lambda _slug: books,
        open_runs=lambda _slug: runs,
        generator=generator,
        cache=StepGenerationCache(StepCache(tmp_path / "cache"), _SLUG),
        notifier=FakeNotifier(),
        score_chrf=lambda _hyp, _ref: 100.0,
        monotonic=lambda: 0.0,
    )


@pytest.mark.integration
def test_sqlite_session_stops_at_three_passages_and_skips_on_rerun(tmp_path) -> None:
    engine = create_book_db(tmp_path / "book.db")
    _seed(engine)
    books = SqliteBookRepository(engine)
    generator = CountingGenerator()
    ports = _ports(engine, generator, tmp_path)
    config = _config(books.get_terms(_SLUG))
    first = generate_passages(ports, _SLUG, config)
    assert first.passages_done == 3
    assert first.passages_total == 4
    assert generator.calls == 3
    records = books.get_records(_SLUG)
    assert len(records) == 3
    assert all("Олівер" in item.idiomatic_uk for item in records)
    leftover = [
        item
        for item in books.get_structure(_SLUG).paragraphs
        if item.status is ParagraphStatus.RAW
    ]
    assert len(leftover) == 1
    second = generate_passages(ports, _SLUG, config)
    assert second.passages_done == 4
    assert generator.calls == 4
    leftover = [
        item
        for item in books.get_structure(_SLUG).paragraphs
        if item.status is ParagraphStatus.RAW
    ]
    assert leftover == []
