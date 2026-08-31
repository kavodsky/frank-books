"""Session-end notice. Implementation is a five-line osascript helper."""

from __future__ import annotations

from typing import Protocol

from frank.domain.model.run import Run


class Notifier(Protocol):
    def notify_completion(self, run: Run) -> None: ...
