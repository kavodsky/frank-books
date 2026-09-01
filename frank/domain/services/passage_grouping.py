"""Group paragraphs into Passage doubling units (roadmap 2.5). No LLM."""

from __future__ import annotations

from frank.domain.model.book import (
    BookStructure,
    Chapter,
    Paragraph,
    Passage,
    PassageGroupingConfig,
)

_SPEECH_OPENERS = ("—", "–", "-", "«", "»", "„", "“", '"', "'")


def group_passages(
    structure: BookStructure, config: PassageGroupingConfig
) -> BookStructure:
    """Pack consecutive paragraphs up to ``max_chars``; never split or cross chapters.

    German: a run of ``— Guten Tag.`` / ``— Guten Abend.`` stays one passage even
    when the sum exceeds ``max_chars``. Hungarian: ``— Hol vagy?`` likewise.
    After such a run, if the passage already meets ``min_chars``, it is closed so
    following narrative does not join it. A single oversized paragraph is its own
    passage.
    """
    passages: list[Passage] = []
    updated: list[Paragraph] = []
    for chapter in structure.chapters:
        paras = tuple(
            item for item in structure.paragraphs if item.chapter_id == chapter.id
        )
        bundles = _bundles(paras, config)
        chapter_passages, rewritten = _assign(chapter, bundles)
        passages.extend(chapter_passages)
        updated.extend(rewritten)
    return structure.model_copy(
        update={"passages": tuple(passages), "paragraphs": tuple(updated)}
    )


def _assign(
    chapter: Chapter, bundles: tuple[tuple[Paragraph, ...], ...]
) -> tuple[tuple[Passage, ...], tuple[Paragraph, ...]]:
    passages: list[Passage] = []
    paragraphs: list[Paragraph] = []
    for index, bundle in enumerate(bundles, start=1):
        passage = Passage(
            id=f"{chapter.id}-pass{index}",
            chapter_id=chapter.id,
            index=index,
        )
        passages.append(passage)
        paragraphs.extend(
            item.model_copy(update={"passage_id": passage.id}) for item in bundle
        )
    return tuple(passages), tuple(paragraphs)


def _bundles(
    paragraphs: tuple[Paragraph, ...], config: PassageGroupingConfig
) -> tuple[tuple[Paragraph, ...], ...]:
    found: list[tuple[Paragraph, ...]] = []
    current: list[Paragraph] = []
    current_len = 0
    index = 0
    while index < len(paragraphs):
        run = _dialogue_run(paragraphs, index, config)
        if run:
            current, current_len, flushed = _absorb_run(
                current, current_len, run, config.max_chars
            )
            found.extend(flushed)
            if current_len >= config.min_chars:
                found.append(tuple(current))
                current, current_len = [], 0
            index += len(run)
            continue
        paragraph = paragraphs[index]
        length = _chars(paragraph)
        if current and current_len + length > config.max_chars:
            found.append(tuple(current))
            current, current_len = [], 0
        current.append(paragraph)
        current_len += length
        index += 1
    if current:
        found.append(tuple(current))
    return tuple(found)


def _absorb_run(
    current: list[Paragraph],
    current_len: int,
    run: tuple[Paragraph, ...],
    max_chars: int,
) -> tuple[list[Paragraph], int, tuple[tuple[Paragraph, ...], ...]]:
    run_len = sum(_chars(item) for item in run)
    flushed: list[tuple[Paragraph, ...]] = []
    if current and current_len + run_len > max_chars:
        flushed.append(tuple(current))
        current, current_len = [], 0
    current.extend(run)
    return current, current_len + run_len, tuple(flushed)


def _dialogue_run(
    paragraphs: tuple[Paragraph, ...],
    start: int,
    config: PassageGroupingConfig,
) -> tuple[Paragraph, ...]:
    if not _is_short_dialogue(paragraphs[start], config):
        return ()
    end = start + 1
    while end < len(paragraphs) and _is_short_dialogue(paragraphs[end], config):
        end += 1
    return paragraphs[start:end]


def _is_short_dialogue(paragraph: Paragraph, config: PassageGroupingConfig) -> bool:
    text = paragraph.raw_text.strip()
    if len(text) > config.dialogue_max_chars:
        return False
    return text.startswith(_SPEECH_OPENERS)


def _chars(paragraph: Paragraph) -> int:
    return len(paragraph.raw_text)
