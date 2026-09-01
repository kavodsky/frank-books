"""Chapter summaries and the book StyleCard (roadmap 3.5)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from frank.domain.model.book import Book, Chapter
from frank.domain.model.termbase import (
    ChapterBrief,
    ChapterBriefConfig,
    ChapterSummary,
    StyleReduceInput,
)
from frank.domain.ports.linguistics import ChapterSummarizer, StyleComposer
from frank.domain.ports.repositories import BookRepository, TermbaseRepository
from frank.domain.services.chapter_briefs import (
    ChapterBriefRequest,
    collect_chapter_briefs,
)
from frank.domain.services.style_card import clamp_summary, render_style_card_markdown


@dataclass(frozen=True)
class StylePorts:
    open_books: Callable[[str], BookRepository]
    open_terms: Callable[[str], TermbaseRepository]
    summarizer: ChapterSummarizer
    composer: StyleComposer
    write_markdown: Callable[[str, str], None]


class StyleReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    chapter_count: int
    summarized_count: int
    style_card: bool


def build_style_card(
    ports: StylePorts, slug: str, config: ChapterBriefConfig
) -> StyleReport:
    books = ports.open_books(slug)
    terms = ports.open_terms(slug)
    structure = books.get_structure(slug)
    briefs = collect_chapter_briefs(
        ChapterBriefRequest(
            structure=structure,
            sentences=books.get_sentences(slug),
            characters=terms.get_characters(slug),
            config=config,
        )
    )
    texts = {item.chapter_id: _summarize(ports, item, config) for item in briefs}
    chapters = tuple(_with_summary(item, texts) for item in structure.chapters)
    books.set_chapter_summaries(slug, chapters)
    slices = _slices(chapters)
    if not slices:
        return StyleReport(
            slug=slug,
            chapter_count=len(structure.chapters),
            summarized_count=0,
            style_card=False,
        )
    card = ports.composer.compose(_reduce_input(structure.book, slices))
    terms.replace_style_card(slug, card)
    ports.write_markdown(slug, render_style_card_markdown(card))
    return StyleReport(
        slug=slug,
        chapter_count=len(structure.chapters),
        summarized_count=len(slices),
        style_card=True,
    )


def render_style_report(report: StyleReport) -> str:
    flag = "yes" if report.style_card else "no"
    return (
        f"summaries: {report.summarized_count}/{report.chapter_count}\n"
        f"style_card: {flag}\n"
    )


def _summarize(
    ports: StylePorts, brief: ChapterBrief, config: ChapterBriefConfig
) -> str:
    return clamp_summary(ports.summarizer.summarize(brief), config)


def _with_summary(chapter: Chapter, texts: dict[str, str]) -> Chapter:
    text = texts.get(chapter.id, "")
    if not text:
        return chapter
    return chapter.model_copy(update={"summary_uk": text})


def _slices(chapters: tuple[Chapter, ...]) -> tuple[ChapterSummary, ...]:
    found: list[ChapterSummary] = []
    for item in chapters:
        if not item.summary_uk:
            continue
        found.append(
            ChapterSummary(
                index=item.index, title=item.title, summary_uk=item.summary_uk
            )
        )
    return tuple(found)


def _reduce_input(book: Book, slices: tuple[ChapterSummary, ...]) -> StyleReduceInput:
    return StyleReduceInput(
        book_id=book.id,
        title=book.title,
        author=book.author,
        lang=book.lang,
        summaries=slices,
    )
