"""Sanity checks on ingested paragraphs (roadmap 1.4)."""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from frank.domain.model.book import BookStatus, BookStructure, Paragraph

_MARKUP = re.compile(r"</?[a-zA-Z][^>]*>|&[a-zA-Z]+;")
_DE_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzäöüß")
_HU_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzáéíóöőúüű")
_ALPHABET = {"de": _DE_LETTERS, "hu": _HU_LETTERS}


class SuspicionKind(StrEnum):
    TOO_LONG = "too_long"
    MARKUP = "markup"
    FOREIGN_SCRIPT = "foreign_script"


class InspectRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_paragraph_chars: int
    foreign_script_ratio: float
    whitelist_hashes: tuple[str, ...]


class SuspiciousParagraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    paragraph_id: str
    chapter_index: int
    paragraph_index: int
    kind: SuspicionKind
    detail: str


class InspectReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    chapter_count: int
    paragraph_count: int
    suspicions: tuple[SuspiciousParagraph, ...]
    clean: bool
    status: BookStatus


def inspect_structure(structure: BookStructure, rules: InspectRules) -> InspectReport:
    """Flag overlong, markup-stained, or foreign-script paragraphs.

    German: leftover `<p>` or a 2000-char blob is suspicious.
    Hungarian: a Cyrillic-heavy paragraph is foreign_script.
    """
    chapter_index = {chapter.id: chapter.index for chapter in structure.chapters}
    allowed = set(rules.whitelist_hashes)
    findings: list[SuspiciousParagraph] = []
    for paragraph in structure.paragraphs:
        if paragraph.hash in allowed:
            continue
        findings.extend(
            _findings_for(paragraph, chapter_index, structure.book.lang, rules)
        )
    clean = not findings
    return InspectReport(
        slug=structure.book.slug,
        chapter_count=len(structure.chapters),
        paragraph_count=len(structure.paragraphs),
        suspicions=tuple(findings),
        clean=clean,
        status=BookStatus.INGESTED if clean else BookStatus.NEEDS_REVIEW,
    )


def _findings_for(
    paragraph: Paragraph,
    chapter_index: dict[str, int],
    lang: str,
    rules: InspectRules,
) -> tuple[SuspiciousParagraph, ...]:
    ch = chapter_index[paragraph.chapter_id]
    hits: list[SuspiciousParagraph] = []
    if len(paragraph.raw_text) > rules.max_paragraph_chars:
        hits.append(
            _finding(
                paragraph, ch, SuspicionKind.TOO_LONG, str(len(paragraph.raw_text))
            )
        )
    if _MARKUP.search(paragraph.raw_text):
        hits.append(_finding(paragraph, ch, SuspicionKind.MARKUP, "html"))
    ratio = _foreign_ratio(paragraph.raw_text, lang)
    if ratio > rules.foreign_script_ratio:
        hits.append(
            _finding(paragraph, ch, SuspicionKind.FOREIGN_SCRIPT, f"{ratio:.2f}")
        )
    return tuple(hits)


def _finding(
    paragraph: Paragraph,
    chapter_index: int,
    kind: SuspicionKind,
    detail: str,
) -> SuspiciousParagraph:
    return SuspiciousParagraph(
        paragraph_id=paragraph.id,
        chapter_index=chapter_index,
        paragraph_index=paragraph.index,
        kind=kind,
        detail=detail,
    )


def _foreign_ratio(text: str, lang: str) -> float:
    letters = [char for char in text if unicodedata.category(char).startswith("L")]
    if not letters:
        return 0.0
    allowed = _ALPHABET.get(lang, _DE_LETTERS | _HU_LETTERS)
    foreign = sum(1 for char in letters if char.casefold() not in allowed)
    return foreign / len(letters)
