"""Simulated crash writes a classified run row and fires a notification."""

from __future__ import annotations

import subprocess

import pytest
from sqlalchemy import inspect

from frank.application.close_run import SessionPorts, close_run_after_crash
from frank.domain.errors import ErrorClass, ModelUnreachable
from frank.domain.model.run import RunFailure, RunStatus, RunTally
from frank.infrastructure.notify.macos import MacosNotifier
from frank.infrastructure.persistence.repositories import SqliteRunRepository
from frank.infrastructure.persistence.tables import create_book_db


@pytest.mark.integration
def test_phase0_ddl_creates_expected_tables(tmp_path) -> None:
    engine = create_book_db(tmp_path / "book.db")
    tables = set(inspect(engine).get_table_names())
    assert {
        "book",
        "run",
        "passage",
        "paragraph",
        "sentence",
        "token",
        "sense_unit",
        "gloss_plan",
        "sentence_output",
        "gloss_unit",
        "word_note",
        "qa_result",
    } <= tables


@pytest.mark.integration
def test_crash_writes_run_row_and_notifies(tmp_path, monkeypatch) -> None:
    engine = create_book_db(tmp_path / "book.db")
    repo = SqliteRunRepository(engine)
    seen: list[list[str]] = []

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        cmd = args[0] if args else kwargs["cmd"]
        seen.append(cmd)  # type: ignore[arg-type]
        return subprocess.CompletedProcess(cmd, 0)  # type: ignore[arg-type]

    monkeypatch.setattr("frank.infrastructure.notify.macos.subprocess.run", fake_run)
    run = repo.start("book-1")
    closed = close_run_after_crash(
        SessionPorts(runs=repo, notifier=MacosNotifier()),
        RunFailure(
            tally=RunTally(run_id=run.id, passages_done=2, last_passage_id="p-2"),
            error=ModelUnreachable("connection refused"),
        ),
    )
    loaded = repo.get(run.id)
    assert loaded.error_class is ErrorClass.MODEL_UNREACHABLE
    assert loaded.status is RunStatus.FAILED
    assert loaded.passages_done == 2
    assert seen[0][0] == "osascript"
    assert "model_unreachable" in seen[0][2]
    assert closed.ended_at is not None
