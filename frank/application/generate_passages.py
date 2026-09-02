"""Sequential passage generation with a session budget (roadmap 5.5).

There is no CLI runner. Tests and the later Dagster asset call this use case.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from frank.application.close_run import SessionPorts, close_run_after_crash
from frank.application.generate_paragraph import (
    AnnotationView,
    GenerateConfig,
    GeneratePorts,
    LoadedBook,
    ParagraphWork,
    SessionBudget,
    SessionTally,
    generate_paragraph,
)
from frank.domain.errors import FrankError
from frank.domain.model.book import BookStructure, ParagraphStatus, Passage
from frank.domain.model.run import Run, RunFailure, RunTally
from frank.domain.model.termbase import TermbaseSnapshot
from frank.domain.ports.repositories import (
    BookRepository,
    FrankRecordRepository,
    RunRepository,
)
from frank.domain.services.termbase_review import require_approved_termbase

__all__ = [
    "GenerateConfig",
    "GeneratePorts",
    "GenerationReport",
    "SessionBudget",
    "StatusPorts",
    "StatusReport",
    "book_generation_status",
    "generate_passages",
    "render_generation_report",
    "render_status",
]


@dataclass(frozen=True)
class StatusPorts:
    open_books: Callable[[str], BookRepository]
    open_runs: Callable[[str], RunRepository]


class GenerationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    passages_done: int
    passages_total: int
    needs_human: int


class StatusReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    passages_done: int
    passages_total: int
    passages_per_hour: float | None


def generate_passages(
    ports: GeneratePorts, slug: str, config: GenerateConfig
) -> GenerationReport:
    """Generate unfinished passages in book order until the session budget."""
    books = ports.open_books(slug)
    terms = ports.open_terms(slug)
    store = ports.open_records(slug)
    structure = books.get_structure(slug)
    snapshot = TermbaseSnapshot(
        terms=terms.get_terms(slug),
        characters=terms.get_characters(slug),
        address_pairs=terms.get_address_pairs(slug),
    )
    require_approved_termbase(snapshot)
    runs = ports.open_runs(slug)
    run = runs.start(structure.book.id)
    tally = SessionTally(records=list(store.get_records(slug)))
    loaded = LoadedBook(slug=slug, structure=structure, snapshot=snapshot)
    work = ParagraphWork(ports=ports, loaded=loaded, config=config, tally=tally)
    started = ports.monotonic()
    try:
        _run_session(work, started)
        closed = runs.record_success(_as_tally(run.id, tally))
        ports.notifier.notify_completion(closed)
    except FrankError as exc:
        close_run_after_crash(
            SessionPorts(runs=runs, notifier=ports.notifier),
            RunFailure(tally=_as_tally(run.id, tally), error=exc),
        )
        raise
    return _report(slug, books.get_structure(slug), store)


def book_generation_status(ports: StatusPorts, slug: str) -> StatusReport:
    books = ports.open_books(slug)
    structure = books.get_structure(slug)
    done = _complete_count(structure)
    pace = _pace(ports.open_runs(slug).list_for_book(structure.book.id))
    return StatusReport(
        slug=slug,
        passages_done=done,
        passages_total=len(structure.passages),
        passages_per_hour=pace,
    )


def render_status(report: StatusReport) -> str:
    if report.passages_per_hour is None:
        pace = "—"
    else:
        pace = f"{report.passages_per_hour:.1f}"
    return (
        f"passages: {report.passages_done}/{report.passages_total}\n"
        f"pace: {pace} passages/hour\n"
    )


def render_generation_report(report: GenerationReport) -> str:
    return (
        f"passages: {report.passages_done}/{report.passages_total}\n"
        f"needs_human: {report.needs_human}\n"
    )


def _run_session(work: ParagraphWork, started: float) -> None:
    config = work.config
    tally = work.tally
    structure = work.loaded.structure
    for passage in _ordered_passages(structure):
        if _passage_complete(structure, passage):
            continue
        if tally.passages_done >= config.session.max_passages:
            return
        if (work.ports.monotonic() - started) / 60 >= config.session.max_minutes:
            return
        _fill_passage(work, passage)
        tally.passages_done += 1
        tally.last_passage_id = passage.id


def _fill_passage(work: ParagraphWork, passage: Passage) -> None:
    books = work.ports.open_books(work.loaded.slug)
    view = AnnotationView(
        sentences=books.get_sentences(work.loaded.slug),
        tokens=books.get_tokens(work.loaded.slug),
        units=books.get_sense_units(work.loaded.slug),
        plan=books.get_gloss_plan(work.loaded.slug),
    )
    paragraphs = [
        item
        for item in work.loaded.structure.paragraphs
        if item.passage_id == passage.id
    ]
    paragraphs.sort(key=lambda item: item.index)
    for paragraph in paragraphs:
        if paragraph.status is ParagraphStatus.COMPLETE:
            continue
        generate_paragraph(work, paragraph, view)


def _ordered_passages(structure: BookStructure) -> tuple[Passage, ...]:
    chapters = {item.id: item.index for item in structure.chapters}
    return tuple(
        sorted(
            structure.passages,
            key=lambda item: (chapters[item.chapter_id], item.index),
        )
    )


def _passage_complete(structure: BookStructure, passage: Passage) -> bool:
    rows = [item for item in structure.paragraphs if item.passage_id == passage.id]
    return bool(rows) and all(item.status is ParagraphStatus.COMPLETE for item in rows)


def _complete_count(structure: BookStructure) -> int:
    return sum(1 for item in structure.passages if _passage_complete(structure, item))


def _report(
    slug: str, structure: BookStructure, store: FrankRecordRepository
) -> GenerationReport:
    needs = sum(1 for item in store.get_qa(slug) if not item.passed)
    return GenerationReport(
        slug=slug,
        passages_done=_complete_count(structure),
        passages_total=len(structure.passages),
        needs_human=needs,
    )


def _as_tally(run_id: str, tally: SessionTally) -> RunTally:
    return RunTally(
        run_id=run_id,
        passages_done=tally.passages_done,
        last_passage_id=tally.last_passage_id,
    )


def _pace(runs: tuple[Run, ...]) -> float | None:
    hours = 0.0
    done = 0
    for item in runs:
        if item.ended_at is None:
            continue
        hours += (item.ended_at - item.started_at).total_seconds() / 3600
        done += item.passages_done
    if hours <= 0 or done <= 0:
        return None
    return done / hours
