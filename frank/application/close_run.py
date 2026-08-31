"""Classify, persist, and announce a session that stopped (roadmap 0.5)."""

from __future__ import annotations

from dataclasses import dataclass

from frank.domain.model.run import Run, RunFailure
from frank.domain.ports.notifier import Notifier
from frank.domain.ports.repositories import RunRepository


@dataclass(frozen=True)
class SessionPorts:
    runs: RunRepository
    notifier: Notifier


def close_run_after_crash(ports: SessionPorts, failure: RunFailure) -> Run:
    """Write a classified `run` row and fire a notification, including error_class."""
    run = ports.runs.record_failure(failure)
    ports.notifier.notify_completion(run)
    return run
