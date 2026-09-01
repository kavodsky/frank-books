"""Build chapter lead/tail briefs for SMART summaries (roadmap 3.5)."""

from __future__ import annotations

from dataclasses import dataclass

from frank.domain.model.book import BookStructure, Paragraph, Sentence
from frank.domain.model.termbase import (
    BriefCharacter,
    ChapterBrief,
    ChapterBriefConfig,
    Character,
)

_SKIP_NAMES = frozenset({"mrs", "mr", "herr", "frau", "úr", "miss"})


@dataclass(frozen=True)
class ChapterBriefRequest:
    structure: BookStructure
    sentences: tuple[Sentence, ...]
    characters: tuple[Character, ...]
    config: ChapterBriefConfig


def collect_chapter_briefs(request: ChapterBriefRequest) -> tuple[ChapterBrief, ...]:
    """Lead and tail sentences per chapter, never the middle (ADR 0017).

    German: a 20-sentence chapter with ``lead_sentences=8`` keeps the workhouse
    opening and the last eight lines; a dump in sentence 10 is dropped.
    Hungarian: a short chapter (≤ lead+tail) sends every sentence as ``lead``.
    """
    paragraphs = {item.id: item for item in request.structure.paragraphs}
    lang = request.structure.book.lang
    found: list[ChapterBrief] = []
    for chapter in request.structure.chapters:
        texts = _sentence_texts(chapter.id, request.sentences, paragraphs)
        if not texts:
            continue
        lead, tail = _lead_tail(texts, request.config)
        found.append(
            ChapterBrief(
                chapter_id=chapter.id,
                index=chapter.index,
                title=chapter.title,
                lang=lang,
                lead=lead,
                tail=tail,
                characters=_mentioned(lead + tail, request.characters),
            )
        )
    return tuple(found)


def _lead_tail(
    texts: tuple[str, ...], config: ChapterBriefConfig
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if len(texts) <= config.lead_sentences + config.tail_sentences:
        return texts, ()
    return texts[: config.lead_sentences], texts[-config.tail_sentences :]


def _sentence_texts(
    chapter_id: str,
    sentences: tuple[Sentence, ...],
    paragraphs: dict[str, Paragraph],
) -> tuple[str, ...]:
    return tuple(
        item.text
        for item in sentences
        if paragraphs[item.paragraph_id].chapter_id == chapter_id
    )


def _mentioned(
    texts: tuple[str, ...], characters: tuple[Character, ...]
) -> tuple[BriefCharacter, ...]:
    blob = " ".join(texts).casefold()
    found: list[BriefCharacter] = []
    for character in characters:
        if not _name_in_blob(character, blob):
            continue
        found.append(
            BriefCharacter(
                canonical_name=character.canonical_name,
                translation_uk=character.translation_uk,
            )
        )
    return tuple(found)


def _name_in_blob(character: Character, blob: str) -> bool:
    names = (character.canonical_name, *character.aliases)
    return any(_needle(name) in blob for name in names if _needle(name))


def _needle(name: str) -> str:
    text = name.casefold().strip()
    if not text or text in _SKIP_NAMES:
        return ""
    return text
