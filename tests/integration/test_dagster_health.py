"""Dagster asset graph, partitions, and classified failures (roadmap Phase 7)."""

from __future__ import annotations

from pathlib import Path

import pytest
from dagster import DagsterInstance, RunConfig, materialize
from typer.main import get_command

from frank.application.generate_paragraph import GeneratePorts
from frank.domain.errors import ErrorClass, ModelUnreachable
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
from frank.domain.model.frank import FrankRecord, ModelTier
from frank.domain.model.termbase import Term, TermKind
from frank.domain.ports.translator import ParagraphGenerationRequest
from frank.infrastructure.persistence.cache import StepCache
from frank.infrastructure.persistence.generation_cache import StepGenerationCache
from frank.infrastructure.persistence.repositories import (
    SqliteBookRepository,
    SqliteRunRepository,
)
from frank.infrastructure.persistence.tables import create_book_db
from frank.interfaces.cli import app
from frank.interfaces.dagster_defs import (
    BookRunConfig,
    FrankResource,
    defs,
    generate,
    ingest,
)
from tests.integration.test_generation_session import CountingGenerator, FakeNotifier

REPO = Path(__file__).resolve().parents[2]
_SLUG = "oliver-de"
_SOURCE = REPO / "tests" / "fixtures" / "sources" / "sample.txt"


@pytest.mark.integration
def test_cli_has_no_generate_command() -> None:
    names = set(get_command(app).commands)
    assert "generate" not in names
    assert "report" in names
    assert "status" in names
    assert "render" in names


@pytest.mark.integration
def test_definitions_load() -> None:
    repo = defs.get_repository_def()
    keys = {key.to_user_string() for key in repo.asset_graph.get_all_asset_keys()}
    assert keys == {"ingest", "segment", "analyze", "generate", "render"}
    checks = {node.key.name for node in repo.asset_graph.asset_check_nodes}
    assert "termbase_consistency" in checks
    assert "lemmas_present" in checks
    assert "back_translation" in checks


@pytest.mark.integration
def test_ingest_registers_chapter_partitions(tmp_path) -> None:
    instance = DagsterInstance.ephemeral()
    result = materialize(
        [ingest],
        instance=instance,
        resources={
            "frank": FrankResource(
                config_path=str(REPO / "config.example.toml"),
                books_dir=str(tmp_path),
            )
        },
        run_config=RunConfig(
            ops={"ingest": BookRunConfig(slug="hu-txt", source=str(_SOURCE), lang="hu")}
        ),
    )
    assert result.success
    keys = instance.get_dynamic_partitions("chapter")
    assert "hu-txt:1" in keys
    assert "hu-txt:2" in keys


@pytest.mark.integration
def test_generate_partition_stops_and_skips_on_rerun(tmp_path, monkeypatch) -> None:
    _seed(tmp_path)
    generator = CountingGenerator()
    monkeypatch.setattr(
        "frank.interfaces.wiring.generate_ports",
        lambda _settings, slug, _books_dir: _ports(tmp_path, slug, generator),
    )
    instance = DagsterInstance.ephemeral()
    instance.add_dynamic_partitions("chapter", [f"{_SLUG}:1"])
    resources = {
        "frank": FrankResource(
            config_path=str(REPO / "config.example.toml"),
            books_dir=str(tmp_path),
        )
    }
    config = RunConfig(ops={"generate": BookRunConfig(slug=_SLUG, max_passages=3)})
    first = materialize(
        [generate],
        instance=instance,
        resources=resources,
        partition_key=f"{_SLUG}:1",
        run_config=config,
    )
    assert first.success
    assert generator.calls == 3
    second = materialize(
        [generate],
        instance=instance,
        resources=resources,
        partition_key=f"{_SLUG}:1",
        run_config=config,
    )
    assert second.success
    assert generator.calls == 4


@pytest.mark.integration
def test_model_unreachable_records_error_class(tmp_path, monkeypatch) -> None:
    _seed(tmp_path)
    monkeypatch.setattr(
        "frank.interfaces.wiring.generate_ports",
        lambda _settings, slug, _books_dir: _ports(tmp_path, slug, _Boom()),
    )
    instance = DagsterInstance.ephemeral()
    instance.add_dynamic_partitions("chapter", [f"{_SLUG}:1"])
    result = materialize(
        [generate],
        instance=instance,
        resources={
            "frank": FrankResource(
                config_path=str(REPO / "config.example.toml"),
                books_dir=str(tmp_path),
            )
        },
        partition_key=f"{_SLUG}:1",
        run_config=RunConfig(ops={"generate": BookRunConfig(slug=_SLUG)}),
        raise_on_error=False,
    )
    assert not result.success
    engine = create_book_db(tmp_path / _SLUG / "book.db")
    runs = SqliteRunRepository(engine).list_for_book("b")
    assert runs[-1].error_class is ErrorClass.MODEL_UNREACHABLE


def _ports(tmp_path: Path, slug: str, generator: object) -> GeneratePorts:
    engine = create_book_db(tmp_path / slug / "book.db")
    books = SqliteBookRepository(engine)
    return GeneratePorts(
        open_books=lambda _s: books,
        open_terms=lambda _s: books,
        open_records=lambda _s: books,
        open_runs=lambda _s: SqliteRunRepository(engine),
        generator=generator,  # type: ignore[arg-type]
        cache=StepGenerationCache(StepCache(tmp_path / slug / "cache"), slug),
        notifier=FakeNotifier(),
        score_chrf=lambda _h, _r: 100.0,
        monotonic=lambda: 0.0,
    )


class _Boom:
    def generate_fast(
        self, _request: ParagraphGenerationRequest
    ) -> tuple[FrankRecord, ...]:
        raise ModelUnreachable("connection refused")

    def generate_smart(
        self, _request: ParagraphGenerationRequest
    ) -> tuple[FrankRecord, ...]:
        raise ModelUnreachable("connection refused")

    def back_translate(self, text: str, source_lang: str, producer: ModelTier) -> str:
        _ = text, source_lang, producer
        raise ModelUnreachable("connection refused")

    def update_scene_brief(self, source_so_far: str, lang: str) -> str:
        _ = source_so_far, lang
        raise ModelUnreachable("connection refused")


def _seed(tmp_path: Path) -> None:
    engine = create_book_db(tmp_path / _SLUG / "book.db")
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
    books.save_structure(
        BookStructure(
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
    )
    books.replace_passages(
        _SLUG,
        books.get_structure(_SLUG).model_copy(update={"passages": tuple(passages)}),
    )
    books.replace_annotation(
        _SLUG,
        Annotation(
            sentences=tuple(sentences),
            tokens=tuple(tokens),
            sense_units=tuple(units),
            gloss_plan=tuple(plan),
        ),
    )
    books.replace_terms(
        _SLUG,
        (
            Term(
                id="t-oliver",
                book_id="b",
                kind=TermKind.PERSON,
                surface_forms=("Oliver",),
                lemma="Oliver",
                translation_uk="Олівер",
                approved=True,
            ),
        ),
    )
