"""Attach analyzer strings to a paragraph (roadmap 2.1)."""

from __future__ import annotations

import pytest

from frank.domain.model.book import Paragraph, ParagraphStatus, Sentence
from frank.domain.services.sentences import sentences_for_paragraph


def _paragraph(text: str) -> Paragraph:
    return Paragraph(
        id="book-c1-p1",
        chapter_id="book-c1",
        passage_id=None,
        index=1,
        raw_text=text,
        hash="x",
        status=ParagraphStatus.RAW,
    )


@pytest.mark.unit
def test_sentences_index_german_and_hungarian() -> None:
    german = sentences_for_paragraph(
        _paragraph("Es war einmal. Am Morgen."),
        ("Es war einmal.", "Am Morgen."),
    )
    assert [item.index for item in german] == [1, 2]
    assert german[0].id == "book-c1-p1-s1"
    hungarian = sentences_for_paragraph(
        _paragraph("Egyszer volt."),
        ("Egyszer volt.", "A királyfi elindult."),
    )
    assert [item.text for item in hungarian] == [
        "Egyszer volt.",
        "A királyfi elindult.",
    ]


@pytest.mark.unit
def test_blank_strings_are_dropped() -> None:
    paragraph = _paragraph("Hallo.")
    assert sentences_for_paragraph(paragraph, ("  ", "Hallo.", "\n")) == (
        Sentence(
            id="book-c1-p1-s1",
            paragraph_id="book-c1-p1",
            index=1,
            text="Hallo.",
        ),
    )
