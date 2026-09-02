"""Assemble a Frank layout from completed passages (roadmap 6.2).

German: ``Oliver kommt.`` with natural ``Олівер іде`` becomes
``Oliver kommt (Олівер іде; Oliver – Олівер).`` — original punct after the
paren. Hungarian: ``Sándor nevet.`` with a non-null ``word_for_word_uk`` inserts
``: «…»`` inside the green paren. Source typography stays in original runs;
Ukrainian runs get guillemets and em dashes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from frank.domain.model.annotation import SenseUnit, Token
from frank.domain.model.book import (
    BookStructure,
    Paragraph,
    ParagraphStatus,
    Passage,
    Sentence,
)
from frank.domain.model.frank import FrankRecord, SenseUnitTranslation, WordNote
from frank.domain.model.layout import (
    LayoutBook,
    LayoutChapter,
    LayoutParagraph,
    LayoutPassage,
    LayoutRequest,
    LayoutRun,
    RunStyle,
)

_TRAIL = re.compile(r"([ \t]*[.!?…]+)$")
_MARKER = "— згенеровано до пасажу {n} —"


@dataclass(frozen=True)
class _Paint:
    source: str
    unit: SenseUnit
    record: FrankRecord
    tokens: tuple[Token, ...]
    last_index: int


def build_layout(request: LayoutRequest) -> LayoutBook:
    """Build title page, completed passages doubled, and the partial-book marker."""
    book = request.structure.book
    complete = completed_passages(request.structure)
    return LayoutBook(
        title=book.title,
        author=book.author,
        source_url=book.source_url,
        license_note=book.license_note,
        chapters=_chapters(request, complete),
        marker=_marker(request.structure, complete),
    )


def completed_passages(structure: BookStructure) -> tuple[Passage, ...]:
    """Passages whose every paragraph is COMPLETE, in book order."""
    return tuple(
        item for item in _ordered_passages(structure) if _is_complete(structure, item)
    )


def apply_uk_typography(text: str) -> str:
    """Guillemets and em dashes in Ukrainian runs only; source runs stay intact."""
    swapped = text.replace("--", "—").replace(" - ", " — ")
    return _guillemets(swapped)


def _chapters(
    request: LayoutRequest, passages: tuple[Passage, ...]
) -> tuple[LayoutChapter, ...]:
    found: list[LayoutChapter] = []
    for chapter in request.structure.chapters:
        rows = tuple(item for item in passages if item.chapter_id == chapter.id)
        if not rows:
            continue
        found.append(
            LayoutChapter(
                title=chapter.title,
                passages=tuple(_passage(request, item) for item in rows),
            )
        )
    return tuple(found)


def _passage(request: LayoutRequest, passage: Passage) -> LayoutPassage:
    paras = [
        item for item in request.structure.paragraphs if item.passage_id == passage.id
    ]
    paras.sort(key=lambda item: item.index)
    return LayoutPassage(
        adapted=tuple(_adapted(request, item) for item in paras),
        unadapted=tuple(_unadapted(item) for item in paras),
    )


def _adapted(request: LayoutRequest, paragraph: Paragraph) -> LayoutParagraph:
    sentences = [
        item for item in request.sentences if item.paragraph_id == paragraph.id
    ]
    sentences.sort(key=lambda item: item.index)
    runs: list[LayoutRun] = []
    for sentence in sentences:
        if runs:
            runs.append(LayoutRun(text=" ", style=RunStyle.ORIGINAL))
        runs.extend(_sentence_runs(request, sentence))
    return LayoutParagraph(runs=tuple(runs))


def _unadapted(paragraph: Paragraph) -> LayoutParagraph:
    return LayoutParagraph(
        runs=(LayoutRun(text=paragraph.raw_text, style=RunStyle.UNADAPTED),)
    )


def _sentence_runs(request: LayoutRequest, sentence: Sentence) -> tuple[LayoutRun, ...]:
    record = _record_for(request.records, sentence.id)
    tokens = tuple(item for item in request.tokens if item.sentence_id == sentence.id)
    units = tuple(item for item in request.units if item.sentence_id == sentence.id)
    if record is None or not units:
        return (LayoutRun(text=sentence.text, style=RunStyle.ORIGINAL),)
    bounds = _unit_bounds(sentence.text, tokens, units)
    last = max(item.index for item in units)
    found: list[LayoutRun] = []
    for unit, source in zip(units, bounds, strict=True):
        found.extend(
            _painted(
                _Paint(
                    source=source,
                    unit=unit,
                    record=record,
                    tokens=tokens,
                    last_index=last,
                )
            )
        )
    return tuple(found)


def _painted(paint: _Paint) -> tuple[LayoutRun, ...]:
    body, trail = _split_end(paint.source, paint.unit.index, paint.last_index)
    found: list[LayoutRun] = []
    if body:
        found.append(LayoutRun(text=body, style=RunStyle.ORIGINAL))
    found.extend(
        _paren_runs(
            _unit_translation(paint.record, paint.unit),
            _notes_for(paint.record, paint.tokens, paint.unit),
        )
    )
    if trail:
        found.append(LayoutRun(text=trail, style=RunStyle.ORIGINAL))
    return tuple(found)


def _paren_runs(
    item: SenseUnitTranslation, notes: tuple[WordNote, ...]
) -> tuple[LayoutRun, ...]:
    found = [
        LayoutRun(text=" (", style=RunStyle.TRANSLATION),
        LayoutRun(
            text=apply_uk_typography(item.natural_uk),
            style=RunStyle.TRANSLATION,
        ),
    ]
    if item.word_for_word_uk:
        found.append(
            LayoutRun(text=_literal(item.word_for_word_uk), style=RunStyle.TRANSLATION)
        )
    for note in notes:
        found.append(
            LayoutRun(
                text=f"; {note.lemma} – {apply_uk_typography(note.gloss_uk)}",
                style=RunStyle.GLOSS,
            )
        )
        if note.morph_note_uk.strip():
            found.append(
                LayoutRun(
                    text=f", {apply_uk_typography(note.morph_note_uk.strip())}",
                    style=RunStyle.NOTE,
                )
            )
    found.append(LayoutRun(text=")", style=RunStyle.TRANSLATION))
    return tuple(found)


def _split_end(source: str, index: int, last_index: int) -> tuple[str, str]:
    stripped = source.rstrip()
    if index != last_index:
        return stripped, ""
    hit = _TRAIL.search(stripped)
    if hit is None:
        return stripped, ""
    return stripped[: hit.start()].rstrip(), hit.group(1)


def _literal(text: str) -> str:
    stripped = apply_uk_typography(text.strip())
    if stripped.startswith("«") and stripped.endswith("»"):
        return f": {stripped}"
    return f": «{stripped}»"


def _notes_for(
    record: FrankRecord, tokens: tuple[Token, ...], unit: SenseUnit
) -> tuple[WordNote, ...]:
    piece = tuple(
        item for item in tokens if unit.start_index <= item.index <= unit.end_index
    )
    keys = _token_keys(piece)
    return tuple(
        item
        for item in record.word_notes
        if item.lemma.casefold() in keys or item.surface.casefold() in keys
    )


def _token_keys(tokens: tuple[Token, ...]) -> set[str]:
    keys: set[str] = set()
    for token in tokens:
        keys.add(token.lemma.casefold())
        keys.add(token.surface.casefold())
        if token.reunited_lemma:
            keys.add(token.reunited_lemma.casefold())
    return keys


def _unit_translation(record: FrankRecord, unit: SenseUnit) -> SenseUnitTranslation:
    span = (unit.start_index, unit.end_index)
    for item in record.units:
        if item.source_span == span:
            return item
    if unit.index <= len(record.units):
        return record.units[unit.index - 1]
    return SenseUnitTranslation(source_span=span, natural_uk="")


def _unit_bounds(
    text: str, tokens: tuple[Token, ...], units: tuple[SenseUnit, ...]
) -> tuple[str, ...]:
    spans = _token_chars(text, tokens)
    by_index = {token.index: span for token, span in zip(tokens, spans, strict=True)}
    found: list[str] = []
    for offset, unit in enumerate(units):
        start = 0 if offset == 0 else by_index[unit.start_index][0]
        if offset + 1 < len(units):
            nxt = units[offset + 1]
            end = by_index[nxt.start_index][0]
        else:
            end = len(text)
        found.append(text[start:end])
    return tuple(found)


def _token_chars(text: str, tokens: tuple[Token, ...]) -> tuple[tuple[int, int], ...]:
    cursor = 0
    found: list[tuple[int, int]] = []
    for token in tokens:
        start = text.find(token.surface, cursor)
        if start < 0:
            start = cursor
            stop = cursor
        else:
            stop = start + len(token.surface)
        found.append((start, stop))
        cursor = stop
    return tuple(found)


def _record_for(
    records: tuple[FrankRecord, ...], sentence_id: str
) -> FrankRecord | None:
    return next((item for item in records if item.sentence_id == sentence_id), None)


def _ordered_passages(structure: BookStructure) -> tuple[Passage, ...]:
    chapters = {item.id: item.index for item in structure.chapters}
    return tuple(
        sorted(
            structure.passages,
            key=lambda item: (chapters[item.chapter_id], item.index),
        )
    )


def _is_complete(structure: BookStructure, passage: Passage) -> bool:
    rows = [item for item in structure.paragraphs if item.passage_id == passage.id]
    return bool(rows) and all(item.status is ParagraphStatus.COMPLETE for item in rows)


def _marker(structure: BookStructure, complete: tuple[Passage, ...]) -> str:
    if not complete:
        return _MARKER.format(n=0)
    ordered = _ordered_passages(structure)
    return _MARKER.format(n=ordered.index(complete[-1]) + 1)


def _guillemets(text: str) -> str:
    chars: list[str] = []
    opening = True
    for char in text:
        if char in {'"', "“", "”", "„"}:
            chars.append("«" if opening else "»")
            opening = not opening
        else:
            chars.append(char)
    return "".join(chars)
