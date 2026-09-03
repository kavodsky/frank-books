"""Cumulative book report (roadmap 7.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from frank.application.report_book import ReportPorts, book_report, render_book_report
from frank.domain.model.book import (
    Book,
    BookStatus,
    BookStructure,
    Chapter,
    Paragraph,
    ParagraphStatus,
    Passage,
)
from frank.domain.model.frank import CheckName, FrankRecord, ModelTier, QaResult
from frank.domain.model.run import Run, RunStatus


class _Books:
    def get_structure(self, slug: str) -> BookStructure:
        _ = slug
        return BookStructure(
            book=Book(
                id="b",
                slug="oliver-de",
                lang="de",
                title="Oliver",
                author="",
                source_url="file.txt",
                license_note="",
                status=BookStatus.INGESTED,
            ),
            chapters=(Chapter(id="c1", book_id="b", index=1, title="I"),),
            paragraphs=(
                Paragraph(
                    id="p1",
                    chapter_id="c1",
                    passage_id="pass-1",
                    index=1,
                    raw_text="Oliver kommt.",
                    hash="h",
                    status=ParagraphStatus.COMPLETE,
                ),
            ),
            passages=(Passage(id="pass-1", chapter_id="c1", index=1),),
        )


class _Runs:
    def list_for_book(self, book_id: str) -> tuple[Run, ...]:
        _ = book_id
        start = datetime.now(UTC)
        return (
            Run(
                id="run-1",
                book_id="b",
                started_at=start,
                ended_at=start + timedelta(hours=1),
                status=RunStatus.COMPLETED,
                passages_done=1,
                last_passage_id="pass-1",
                error_class=None,
                error_msg=None,
            ),
        )


class _Records:
    def get_records(self, slug: str) -> tuple[FrankRecord, ...]:
        _ = slug
        return (
            FrankRecord(
                sentence_id="s1",
                units=(),
                idiomatic_uk="Олівер іде.",
                word_notes=(),
                tier=ModelTier.FAST,
            ),
        )

    def get_qa(self, slug: str) -> tuple[QaResult, ...]:
        _ = slug
        return (
            QaResult(
                id="q1",
                paragraph_id="p1",
                check_name=CheckName.BACK_TRANSLATION.value,
                passed=False,
                detail="12.0",
                attempt=0,
            ),
        )


@pytest.mark.unit
def test_book_report_lists_tier_split_and_needs_human() -> None:
    report = book_report(
        ReportPorts(
            open_books=lambda _s: _Books(),
            open_runs=lambda _s: _Runs(),
            open_records=lambda _s: _Records(),
        ),
        "oliver-de",
    )
    assert report.passages_done == 1
    assert report.fast_pct == 100.0
    assert report.needs_human == 1
    assert report.failed_checks == 0
    text = render_book_report(report)
    assert "FAST 100%" in text
    assert "needs_human: 1" in text
    assert report.last_error_class is None
