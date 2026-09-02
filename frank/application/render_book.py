"""Write a completed-passage LayoutBook to disk (roadmap 6.2)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from frank.domain.model.layout import LayoutBook, LayoutRequest
from frank.domain.ports.repositories import BookRepository, FrankRecordRepository
from frank.domain.services.layout import build_layout

__all__ = ["RenderPorts", "RenderReport", "format_render_report", "render_book"]


@dataclass(frozen=True)
class RenderPorts:
    open_books: Callable[[str], BookRepository]
    open_records: Callable[[str], FrankRecordRepository]
    write_docx: Callable[[LayoutBook, Path], None]


class RenderReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    path: str
    passages: int


def render_book(ports: RenderPorts, slug: str, out_path: Path) -> RenderReport:
    """Load completed passages and write a partial or full Frank .docx."""
    books = ports.open_books(slug)
    store = ports.open_records(slug)
    layout = build_layout(
        LayoutRequest(
            structure=books.get_structure(slug),
            sentences=books.get_sentences(slug),
            tokens=books.get_tokens(slug),
            units=books.get_sense_units(slug),
            records=store.get_records(slug),
        )
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ports.write_docx(layout, out_path)
    return RenderReport(
        slug=slug,
        path=str(out_path),
        passages=sum(len(item.passages) for item in layout.chapters),
    )


def format_render_report(report: RenderReport) -> str:
    return f"wrote {report.path} ({report.passages} passages)\n"
