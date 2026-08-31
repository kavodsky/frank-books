"""A generation session, independent of any orchestrator's own run log."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from frank.domain.errors import ErrorClass, FrankError


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Run(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    book_id: str
    started_at: datetime
    ended_at: datetime | None
    status: RunStatus
    passages_done: int
    last_passage_id: str | None
    error_class: ErrorClass | None
    error_msg: str | None


class RunTally(BaseModel):
    """How far a session got; passed into success/failure recording."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    passages_done: int
    last_passage_id: str | None


class RunFailure(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    tally: RunTally
    error: FrankError
