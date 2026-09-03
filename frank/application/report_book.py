"""Cumulative book-level session picture (roadmap 7.4)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from frank.application.generate_passages import StatusPorts, book_generation_status
from frank.domain.model.frank import CheckName, FrankRecord, ModelTier, QaResult
from frank.domain.model.run import Run
from frank.domain.ports.repositories import (
    BookRepository,
    FrankRecordRepository,
    RunRepository,
)


@dataclass(frozen=True)
class ReportPorts:
    open_books: Callable[[str], BookRepository]
    open_runs: Callable[[str], RunRepository]
    open_records: Callable[[str], FrankRecordRepository]


class BookReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    passages_done: int
    passages_total: int
    passages_per_hour: float | None
    eta_hours: float | None
    sessions: int
    fast_pct: float | None
    smart_pct: float | None
    failed_checks: int
    needs_human: int
    needs_human_previews: tuple[str, ...]
    last_error_class: str | None
    output_tokens: int


def book_report(ports: ReportPorts, slug: str) -> BookReport:
    """Aggregate runs, records, and QA into the cumulative book picture."""
    status = book_generation_status(
        StatusPorts(open_books=ports.open_books, open_runs=ports.open_runs), slug
    )
    books = ports.open_books(slug)
    store = ports.open_records(slug)
    structure = books.get_structure(slug)
    runs = ports.open_runs(slug).list_for_book(structure.book.id)
    records = store.get_records(slug)
    qa = store.get_qa(slug)
    needs = tuple(item for item in qa if not item.passed)
    return BookReport(
        slug=slug,
        passages_done=status.passages_done,
        passages_total=status.passages_total,
        passages_per_hour=status.passages_per_hour,
        eta_hours=status.eta_hours,
        sessions=len(runs),
        fast_pct=_pct(records, ModelTier.FAST),
        smart_pct=_pct(records, ModelTier.SMART),
        failed_checks=sum(
            1 for item in needs if item.check_name != CheckName.BACK_TRANSLATION
        ),
        needs_human=len(needs),
        needs_human_previews=_previews(needs),
        last_error_class=_last_error(runs),
        output_tokens=sum(len(item.idiomatic_uk.split()) for item in records),
    )


def render_book_report(report: BookReport) -> str:
    if report.passages_per_hour is None:
        pace = "—"
    else:
        pace = f"{report.passages_per_hour:.1f}"
    eta = "—" if report.eta_hours is None else f"{report.eta_hours:.1f} h"
    fast = "—" if report.fast_pct is None else f"{report.fast_pct:.0f}%"
    smart = "—" if report.smart_pct is None else f"{report.smart_pct:.0f}%"
    error = report.last_error_class or "—"
    previews = "\n".join(f"- {item}" for item in report.needs_human_previews)
    extra = f"\n{previews}\n" if previews else "\n"
    return (
        f"passages: {report.passages_done}/{report.passages_total}\n"
        f"pace: {pace} passages/hour\n"
        f"eta: {eta}\n"
        f"sessions: {report.sessions}\n"
        f"tier: FAST {fast} / SMART {smart}\n"
        f"failed_checks: {report.failed_checks}\n"
        f"needs_human: {report.needs_human}{extra}"
        f"output_tokens: {report.output_tokens}\n"
        f"last_error: {error}\n"
    )


def _pct(records: tuple[FrankRecord, ...], tier: ModelTier) -> float | None:
    if not records:
        return None
    hits = sum(1 for item in records if item.tier is tier)
    return 100.0 * hits / len(records)


def _previews(needs: tuple[QaResult, ...]) -> tuple[str, ...]:
    return tuple(f"{item.check_name}: {item.detail}" for item in needs[:5])


def _last_error(runs: tuple[Run, ...]) -> str | None:
    for item in reversed(runs):
        if item.error_class is not None:
            return item.error_class.value
    return None
