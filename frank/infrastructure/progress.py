"""Live passage progress: chapter/passage, elapsed, passages/hour (roadmap 0.5.2)."""

from __future__ import annotations

import time

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)


class PassageProgress:
    def __init__(self, total_passages: int) -> None:
        self._started = time.monotonic()
        self._done = 0
        self._progress = Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TextColumn("{task.fields[rate]}"),
        )
        self._task_id = self._progress.add_task(
            "passages",
            total=total_passages,
            rate="0/h",
        )

    def start(self) -> None:
        self._progress.start()

    def stop(self) -> None:
        self._progress.stop()

    def mark_passage_done(self, chapter: str, passage: str) -> None:
        self._done += 1
        elapsed_h = (time.monotonic() - self._started) / 3600
        rate = f"{self._done / elapsed_h:.1f}/h" if elapsed_h > 0 else "—"
        self._progress.update(
            self._task_id,
            advance=1,
            description=f"{chapter} / {passage}",
            rate=rate,
        )
