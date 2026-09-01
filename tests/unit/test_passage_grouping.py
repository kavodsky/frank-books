"""Group paragraphs into Passage doubling units (roadmap 2.5)."""

from __future__ import annotations

import pytest

from frank.domain.model.book import (
    Book,
    BookStatus,
    BookStructure,
    Chapter,
    Paragraph,
    ParagraphStatus,
    PassageGroupingConfig,
)
from frank.domain.services.passage_grouping import group_passages

_CFG = PassageGroupingConfig(min_chars=20, max_chars=50, dialogue_max_chars=15)


def _structure(*chapters: tuple[str, ...]) -> BookStructure:
    book = Book(
        id="s",
        slug="s",
        lang="de",
        title="T",
        author="",
        source_url="file.txt",
        license_note="",
        status=BookStatus.INGESTED,
    )
    found_chapters: list[Chapter] = []
    paragraphs: list[Paragraph] = []
    for chapter_index, texts in enumerate(chapters, start=1):
        chapter = Chapter(
            id=f"s-c{chapter_index}",
            book_id="s",
            index=chapter_index,
            title=f"K{chapter_index}",
        )
        found_chapters.append(chapter)
        for para_index, text in enumerate(texts, start=1):
            paragraphs.append(
                Paragraph(
                    id=f"{chapter.id}-p{para_index}",
                    chapter_id=chapter.id,
                    passage_id=None,
                    index=para_index,
                    raw_text=text,
                    hash=f"h{chapter_index}-{para_index}",
                    status=ParagraphStatus.RAW,
                )
            )
    return BookStructure(
        book=book, chapters=tuple(found_chapters), paragraphs=tuple(paragraphs)
    )


def _ids(structure: BookStructure) -> tuple[tuple[str, ...], ...]:
    by_passage: dict[str, list[str]] = {item.id: [] for item in structure.passages}
    for paragraph in structure.paragraphs:
        assert paragraph.passage_id is not None
        by_passage[paragraph.passage_id].append(paragraph.id)
    return tuple(tuple(ids) for ids in by_passage.values())


@pytest.mark.unit
def test_does_not_cross_chapters() -> None:
    grouped = group_passages(_structure(("aaaa",), ("bbbb",)), _CFG)
    assert [item.chapter_id for item in grouped.passages] == ["s-c1", "s-c2"]
    assert grouped.paragraphs[0].passage_id != grouped.paragraphs[1].passage_id


@pytest.mark.unit
def test_does_not_split_a_paragraph() -> None:
    text = "x" * 80
    grouped = group_passages(_structure((text, "yy")), _CFG)
    assert grouped.paragraphs[0].raw_text == text
    assert _ids(grouped) == (("s-c1-p1",), ("s-c1-p2",))


@pytest.mark.unit
def test_packs_up_to_max_chars() -> None:
    grouped = group_passages(_structure(("a" * 20, "b" * 20, "c" * 20)), _CFG)
    assert _ids(grouped) == (("s-c1-p1", "s-c1-p2"), ("s-c1-p3",))


@pytest.mark.unit
def test_dialogue_run_stays_one_passage_over_max() -> None:
    lines = tuple(f"— Guten {index}." for index in range(8))
    grouped = group_passages(_structure(lines), _CFG)
    assert len(grouped.passages) == 1
    assert _ids(grouped) == (tuple(f"s-c1-p{i}" for i in range(1, 9)),)


@pytest.mark.unit
def test_hungarian_dialogue_run_stays_one_passage() -> None:
    lines = tuple("— Hol vagy?" for _ in range(8))
    grouped = group_passages(_structure(lines), _CFG)
    assert len(grouped.passages) == 1


@pytest.mark.unit
def test_short_non_speech_does_not_use_dialogue_rule() -> None:
    lines = tuple("Genau so." for _ in range(12))
    grouped = group_passages(_structure(lines), _CFG)
    assert len(grouped.passages) > 1
    lengths = [
        sum(len(item.raw_text) for item in grouped.paragraphs if item.passage_id == pid)
        for pid in (passage.id for passage in grouped.passages)
    ]
    assert all(length <= _CFG.max_chars for length in lengths)


@pytest.mark.unit
def test_rerun_is_byte_identical() -> None:
    source = _structure(("a" * 20, "— Hi.", "— Ho.", "b" * 20), ("c" * 40,))
    first = group_passages(source, _CFG)
    second = group_passages(source, _CFG)
    assert first.passages == second.passages
    assert first.paragraphs == second.paragraphs
