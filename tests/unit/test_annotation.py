"""Bind analyzer tokens to a sentence (roadmap 2.2)."""

from __future__ import annotations

import pytest

from frank.domain.model.annotation import (
    MorphFeature,
    Morphology,
    ParsedSentence,
    ParsedToken,
)
from frank.domain.model.book import Paragraph, ParagraphStatus
from frank.domain.services.annotation import annotate_paragraph


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


def _token(index: int, surface: str, lemma: str, upos: str) -> ParsedToken:
    return ParsedToken(
        index=index,
        surface=surface,
        lemma=lemma,
        upos=upos,
        morph=Morphology(),
    )


@pytest.mark.unit
def test_empty_lemma_falls_back_to_surface() -> None:
    parsed = (
        ParsedSentence(
            index=1,
            text="felállt.",
            tokens=(
                _token(1, "felállt", "", "VERB"),
                _token(2, ".", ".", "PUNCT"),
            ),
        ),
    )
    tokens = annotate_paragraph(_paragraph("felállt."), parsed).tokens
    assert tokens[0].lemma == "felállt"
    assert tokens[0].id == "book-c1-p1-s1-t1"


@pytest.mark.unit
def test_german_case_feature_is_kept() -> None:
    morph = Morphology(features=(MorphFeature(key="Case", value="Nom"),))
    det = ParsedToken(
        index=1,
        surface="Der",
        lemma="der",
        upos="DET",
        morph=morph,
    )
    parsed = (
        ParsedSentence(
            index=1,
            text="Der Arzt sah das Kind.",
            tokens=(det, _token(2, "Arzt", "Arzt", "NOUN")),
        ),
    )
    tokens = annotate_paragraph(_paragraph("Der Arzt sah das Kind."), parsed).tokens
    assert tokens[0].morph.value_of("Case") == "Nom"
    assert tokens[0].lemma == "der"


@pytest.mark.unit
def test_ent_type_is_copied() -> None:
    parsed = (
        ParsedSentence(
            index=1,
            text="Oliver ging.",
            tokens=(
                ParsedToken(
                    index=1,
                    surface="Oliver",
                    lemma="Oliver",
                    upos="PROPN",
                    morph=Morphology(),
                    ent_type="PER",
                ),
                _token(2, "ging", "gehen", "VERB"),
            ),
        ),
    )
    tokens = annotate_paragraph(_paragraph("Oliver ging."), parsed).tokens
    assert tokens[0].ent_type == "PER"
