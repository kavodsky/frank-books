"""Read a local file into raw bytes. No HTTP (ADR 0013)."""

from __future__ import annotations

from pathlib import Path

from charset_normalizer import from_bytes

from frank.domain.errors import UnknownError


def load_bytes(location: str) -> tuple[bytes, str]:
    path = Path(location)
    if not path.is_file():
        raise UnknownError(f"source file not found: {location}")
    return path.read_bytes(), str(path.resolve())


def decode_bytes(raw: bytes) -> str:
    best = from_bytes(raw).best()
    if best is None:
        return raw.decode("utf-8", errors="replace")
    return str(best)
