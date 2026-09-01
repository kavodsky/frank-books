"""Lead/tail chapter briefs, never the middle (roadmap 3.5)."""

from __future__ import annotations

import pytest

from frank.domain.model.book import (
    Book,
    BookStatus,
    BookStructure,
    Chapter,
    Paragraph,
    ParagraphStatus,
    Sentence,
)
from frank.domain.model.termbase import (
    ChapterBriefConfig,
    Character,
    Gender,
)
from frank.domain.services.chapter_briefs import (
    ChapterBriefRequest,
    collect_chapter_briefs,
)

_CFG = ChapterBriefConfig(
    lead_sentences=3,
    tail_sentences=3,
    summary_sentence_min=3,
    summary_sentence_max=5,
)


def _book(lang: str = "de") -> Book:
    return Book(
        id="b",
        slug="s",
        lang=lang,
        title="T",
        author="A",
        source_url="file.txt",
        license_note="",
        status=BookStatus.INGESTED,
    )


def _paragraph(chapter_id: str) -> Paragraph:
    return Paragraph(
        id=f"{chapter_id}-p1",
        chapter_id=chapter_id,
        passage_id=None,
        index=1,
        raw_text="x",
        hash="h",
        status=ParagraphStatus.RAW,
    )


def _sentence(paragraph_id: str, index: int, text: str) -> Sentence:
    return Sentence(
        id=f"{paragraph_id}-s{index}",
        paragraph_id=paragraph_id,
        index=index,
        text=text,
    )


def _oliver() -> Character:
    return Character(
        id="c-oliver",
        book_id="b",
        canonical_name="Oliver",
        translation_uk="Олівер",
        gender=Gender.MALE,
    )


def _bumble() -> Character:
    return Character(
        id="c-bumble",
        book_id="b",
        canonical_name="Bumble",
        translation_uk="Бамбл",
        gender=Gender.MALE,
    )


@pytest.mark.unit
def test_long_german_chapter_drops_the_middle() -> None:
    chapter_id = "b-c1"
    para = _paragraph(chapter_id)
    texts = [f"Oliver satz {index}." for index in range(1, 21)]
    texts[9] = "CHAPTER_DUMP in der Mitte."
    sentences = tuple(
        _sentence(para.id, index, text) for index, text in enumerate(texts, start=1)
    )
    briefs = collect_chapter_briefs(
        ChapterBriefRequest(
            structure=BookStructure(
                book=_book(),
                chapters=(Chapter(id=chapter_id, book_id="b", index=1, title="I"),),
                paragraphs=(para,),
            ),
            sentences=sentences,
            characters=(_oliver(), _bumble()),
            config=_CFG,
        )
    )
    assert len(briefs) == 1
    brief = briefs[0]
    assert brief.lead == tuple(texts[:3])
    assert brief.tail == tuple(texts[-3:])
    blob = " ".join(brief.lead + brief.tail)
    assert "CHAPTER_DUMP" not in blob
    assert brief.characters[0].canonical_name == "Oliver"
    assert brief.characters[0].translation_uk == "Олівер"
    assert all(item.canonical_name != "Bumble" for item in brief.characters)


@pytest.mark.unit
def test_short_hungarian_chapter_is_all_lead() -> None:
    chapter_id = "b-c1"
    para = _paragraph(chapter_id)
    sentences = (
        _sentence(para.id, 1, "Sándor belépett."),
        _sentence(para.id, 2, "Gábor köszönt."),
        _sentence(para.id, 3, "Leültek."),
        _sentence(para.id, 4, "Csend lett."),
    )
    briefs = collect_chapter_briefs(
        ChapterBriefRequest(
            structure=BookStructure(
                book=_book("hu"),
                chapters=(Chapter(id=chapter_id, book_id="b", index=1, title="1"),),
                paragraphs=(para,),
            ),
            sentences=sentences,
            characters=(),
            config=_CFG,
        )
    )
    assert briefs[0].lead == (
        "Sándor belépett.",
        "Gábor köszönt.",
        "Leültek.",
        "Csend lett.",
    )
    assert briefs[0].tail == ()
    assert briefs[0].lang == "hu"
