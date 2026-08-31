"""macOS completion notice (roadmap 0.5.3)."""

from __future__ import annotations

import json
import subprocess

from frank.domain.model.run import Run, RunStatus


def notify_macos(title: str, body: str) -> None:
    script = f"display notification {json.dumps(body)} with title {json.dumps(title)}"
    subprocess.run(["osascript", "-e", script], check=False)


class MacosNotifier:
    def notify_completion(self, run: Run) -> None:
        notify_macos("frank-books", _body_for(run))


def _body_for(run: Run) -> str:
    if run.status is RunStatus.COMPLETED:
        return f"session complete: {run.passages_done} passages"
    error_class = run.error_class.value if run.error_class is not None else "unknown"
    return f"session {run.status.value}: {error_class}"
