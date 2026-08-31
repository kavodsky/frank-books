"""close_run_after_crash classifies, persists, and notifies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from frank.application.close_run import SessionPorts, close_run_after_crash
from frank.domain.errors import ErrorClass, ModelUnreachable
from frank.domain.model.run import Run, RunFailure, RunStatus, RunTally


@dataclass
class FakeRuns:
    stored: dict[str, Run] = field(default_factory=dict)

    def start(self, book_id: str) -> Run:
        run = _running(book_id)
        self.stored[run.id] = run
        return run

    def record_success(self, tally: RunTally) -> Run:
        del tally
        raise AssertionError

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


@dataclass
class FakeNotifier:
    seen: list[Run] = field(default_factory=list)

    def notify_completion(self, run: Run) -> None:
        self.seen.append(run)


def _running(book_id: str) -> Run:
    return Run(
        id="run-1",
        book_id=book_id,
        started_at=datetime.now(UTC),
        ended_at=None,
        status=RunStatus.RUNNING,
        passages_done=0,
        last_passage_id=None,
        error_class=None,
        error_msg=None,
    )


@pytest.mark.unit
def test_crash_records_classified_run_and_notifies() -> None:
    runs = FakeRuns()
    notifier = FakeNotifier()
    run = runs.start("book-1")
    error = ModelUnreachable("connection refused")
    closed = close_run_after_crash(
        SessionPorts(runs=runs, notifier=notifier),
        RunFailure(
            tally=RunTally(run_id=run.id, passages_done=3, last_passage_id="p-3"),
            error=error,
        ),
    )
    assert closed.error_class is ErrorClass.MODEL_UNREACHABLE
    assert closed.status is RunStatus.FAILED
    assert notifier.seen[0].error_class is ErrorClass.MODEL_UNREACHABLE
