"""Ports for reading a local original and storing its raw bytes."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from frank.domain.model.source import FetchedSource


class SourceFetcher(Protocol):
    def fetch(self, location: str) -> FetchedSource: ...


class RawStore(Protocol):
    def write(self, slug: str, filename: str, data: bytes) -> Path: ...
