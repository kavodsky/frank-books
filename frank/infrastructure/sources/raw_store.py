"""Untouched raw bytes under books/{slug}/raw/."""

from __future__ import annotations

from pathlib import Path


class FilesystemRawStore:
    def __init__(self, books_dir: Path) -> None:
        self._books_dir = books_dir

    def write(self, slug: str, filename: str, data: bytes) -> Path:
        path = self._books_dir / slug / "raw" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path
