"""Chapter and paragraph splitting over normalized text (roadmap 1.3)."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from frank.domain.model.book import (
    Book,
    BookStatus,
    BookStructure,
    Chapter,
    Paragraph,
    ParagraphStatus,
)
from frank.domain.model.source import FetchedSource


class ChapterDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    title: str
    body: str


def split_chapters(
    text: str, heading_pattern: str, fallback_title: str
) -> tuple[ChapterDraft, ...]:
    """Split on heading regex; a book with no headings is one chapter.

    German: `^# Erstes Kapitel` starts a chapter.
    Hungarian: `^# Első fejezet` likewise.
    """
    pattern = re.compile(heading_pattern, re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return (ChapterDraft(index=1, title=fallback_title, body=text.strip()),)
    drafts: list[ChapterDraft] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        drafts.append(ChapterDraft(index=0, title=fallback_title, body=preamble))
    for i, match in enumerate(matches):
        title = _heading_title(match, fallback_title)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        drafts.append(ChapterDraft(index=len(drafts) + 1, title=title, body=body))
    return _reindex(tuple(drafts))


def split_paragraphs(body: str) -> tuple[str, ...]:
    """Blank-line paragraph split; empty chunks dropped."""
    parts = [chunk.strip() for chunk in re.split(r"\n\s*\n", body)]
    return tuple(part for part in parts if part)


def build_structure(
    fetched: FetchedSource,
    normalized: str,
    slug: str,
) -> BookStructure:
    drafts = split_chapters(normalized, fetched.heading_pattern, fetched.title)
    book = Book(
        id=slug,
        slug=slug,
        lang=fetched.lang,
        title=fetched.title,
        author=fetched.author,
        source_url=fetched.location,
        license_note=fetched.license_note,
        status=BookStatus.NEEDS_REVIEW,
    )
    chapters, paragraphs = _materialize(book.id, drafts)
    return BookStructure(book=book, chapters=chapters, paragraphs=paragraphs)


def _heading_title(match: re.Match[str], fallback: str) -> str:
    if match.lastindex:
        return match.group(1).strip() or fallback
    line = match.group(0).strip()
    return line.lstrip("# ").strip() or fallback


def _reindex(drafts: Sequence[ChapterDraft]) -> tuple[ChapterDraft, ...]:
    return tuple(
        ChapterDraft(index=i, title=draft.title, body=draft.body)
        for i, draft in enumerate(drafts, start=1)
    )


def _materialize(
    book_id: str,
    drafts: Sequence[ChapterDraft],
) -> tuple[tuple[Chapter, ...], tuple[Paragraph, ...]]:
    chapters: list[Chapter] = []
    paragraphs: list[Paragraph] = []
    for draft in drafts:
        chapter_id = f"{book_id}-c{draft.index}"
        chapters.append(
            Chapter(
                id=chapter_id,
                book_id=book_id,
                index=draft.index,
                title=draft.title,
            )
        )
        for p_index, text in enumerate(split_paragraphs(draft.body), start=1):
            paragraphs.append(
                Paragraph(
                    id=f"{chapter_id}-p{p_index}",
                    chapter_id=chapter_id,
                    passage_id=None,
                    index=p_index,
                    raw_text=text,
                    hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    status=ParagraphStatus.RAW,
                )
            )
    return tuple(chapters), tuple(paragraphs)
