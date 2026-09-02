"""Frank layout: adapted/unadapted doubling per completed passage (roadmap 6.2)."""

from __future__ import annotations

import pytest

from frank.domain.model.annotation import Morphology, SenseUnit, Token
from frank.domain.model.book import (
    Book,
    BookStatus,
    BookStructure,
    Chapter,
    Paragraph,
    ParagraphStatus,
    Passage,
    Sentence,
)
from frank.domain.model.frank import (
    FrankRecord,
    ModelTier,
    SenseUnitTranslation,
    WordNote,
)
from frank.domain.model.layout import LayoutRequest, RunStyle
from frank.domain.services.layout import apply_uk_typography, build_layout


def _book(status: ParagraphStatus = ParagraphStatus.COMPLETE) -> BookStructure:
    return BookStructure(
        book=Book(
            id="b",
            slug="oliver-de",
            lang="de",
            title="Oliver Twist",
            author="Charles Dickens",
            source_url="https://example.test/oliver",
            license_note="public domain",
            status=BookStatus.INGESTED,
        ),
        chapters=(Chapter(id="c1", book_id="b", index=1, title="I"),),
        passages=(Passage(id="pass-1", chapter_id="c1", index=1),),
        paragraphs=(
            Paragraph(
                id="p1",
                chapter_id="c1",
                passage_id="pass-1",
                index=1,
                raw_text="Oliver kommt.",
                hash="h1",
                status=status,
            ),
        ),
    )


def _tokens() -> tuple[Token, ...]:
    rows = (
        (1, "Oliver", "Oliver", "PROPN"),
        (2, "kommt", "kommen", "VERB"),
        (3, ".", ".", "PUNCT"),
    )
    return tuple(
        Token(
            id=f"t{index}",
            sentence_id="s1",
            index=index,
            surface=surface,
            lemma=lemma,
            upos=upos,
            morph=Morphology(),
        )
        for index, surface, lemma, upos in rows
    )


def _record() -> FrankRecord:
    return FrankRecord(
        sentence_id="s1",
        units=(
            SenseUnitTranslation(
                source_span=(1, 3),
                natural_uk='Олівер "іде"',
            ),
        ),
        idiomatic_uk="Олівер іде.",
        word_notes=(
            WordNote(
                surface="Oliver",
                lemma="Oliver",
                morph_note_uk="",
                gloss_uk="Олівер",
            ),
        ),
        tier=ModelTier.FAST,
    )


def _request(status: ParagraphStatus = ParagraphStatus.COMPLETE) -> LayoutRequest:
    return LayoutRequest(
        structure=_book(status),
        sentences=(
            Sentence(id="s1", paragraph_id="p1", index=1, text="Oliver kommt."),
        ),
        tokens=_tokens(),
        units=(
            SenseUnit(id="u1", sentence_id="s1", index=1, start_index=1, end_index=3),
        ),
        records=(_record(),),
    )


def _plain(runs) -> str:
    return "".join(item.text for item in runs)


@pytest.mark.unit
def test_oliver_adapted_then_unadapted_with_punct_after_paren() -> None:
    layout = build_layout(_request())
    adapted = layout.chapters[0].passages[0].adapted[0]
    assert _plain(adapted.runs) == "Oliver kommt (Олівер «іде»; Oliver – Олівер)."
    styles = [item.style for item in adapted.runs]
    assert RunStyle.ORIGINAL in styles
    assert RunStyle.TRANSLATION in styles
    assert RunStyle.GLOSS in styles
    unadapted = layout.chapters[0].passages[0].unadapted[0]
    assert _plain(unadapted.runs) == "Oliver kommt."
    assert unadapted.runs[0].style is RunStyle.UNADAPTED
    assert layout.marker == "— згенеровано до пасажу 1 —"


@pytest.mark.unit
def test_hungarian_word_for_word_uses_guillemets() -> None:
    structure = _book()
    structure = structure.model_copy(
        update={
            "book": structure.book.model_copy(
                update={"lang": "hu", "title": "Twist Olivér"}
            )
        }
    )
    record = FrankRecord(
        sentence_id="s1",
        units=(
            SenseUnitTranslation(
                source_span=(1, 3),
                natural_uk="Шандор сміється",
                word_for_word_uk="Шандор сміється з цього",
            ),
        ),
        idiomatic_uk="Шандор сміється.",
        word_notes=(),
        tier=ModelTier.FAST,
    )
    tokens = (
        Token(
            id="t1",
            sentence_id="s1",
            index=1,
            surface="Sándor",
            lemma="Sándor",
            upos="PROPN",
            morph=Morphology(),
        ),
        Token(
            id="t2",
            sentence_id="s1",
            index=2,
            surface="nevet",
            lemma="nevet",
            upos="VERB",
            morph=Morphology(),
        ),
        Token(
            id="t3",
            sentence_id="s1",
            index=3,
            surface=".",
            lemma=".",
            upos="PUNCT",
            morph=Morphology(),
        ),
    )
    layout = build_layout(
        LayoutRequest(
            structure=structure.model_copy(
                update={
                    "paragraphs": (
                        structure.paragraphs[0].model_copy(
                            update={"raw_text": "Sándor nevet."}
                        ),
                    )
                }
            ),
            sentences=(
                Sentence(id="s1", paragraph_id="p1", index=1, text="Sándor nevet."),
            ),
            tokens=tokens,
            units=(
                SenseUnit(
                    id="u1", sentence_id="s1", index=1, start_index=1, end_index=3
                ),
            ),
            records=(record,),
        )
    )
    text = _plain(layout.chapters[0].passages[0].adapted[0].runs)
    assert ": «Шандор сміється з цього»" in text
    assert text.endswith(").")


@pytest.mark.unit
def test_incomplete_passage_is_omitted() -> None:
    layout = build_layout(_request(ParagraphStatus.RAW))
    assert layout.chapters == ()
    assert layout.marker == "— згенеровано до пасажу 0 —"


@pytest.mark.unit
def test_reunited_lemma_in_gloss_and_morph_note() -> None:
    record = _record().model_copy(
        update={
            "word_notes": (
                WordNote(
                    surface="kommt",
                    lemma="ankommen",
                    morph_note_uk="відокремлюваний префікс",
                    gloss_uk="приходить",
                ),
            )
        }
    )
    tokens = (
        Token(
            id="t1",
            sentence_id="s1",
            index=1,
            surface="kommt",
            lemma="kommen",
            upos="VERB",
            morph=Morphology(),
            reunited_lemma="ankommen",
        ),
        Token(
            id="t2",
            sentence_id="s1",
            index=2,
            surface="an",
            lemma="an",
            upos="ADP",
            morph=Morphology(),
        ),
        Token(
            id="t3",
            sentence_id="s1",
            index=3,
            surface=".",
            lemma=".",
            upos="PUNCT",
            morph=Morphology(),
        ),
    )
    layout = build_layout(
        LayoutRequest(
            structure=_book(),
            sentences=(
                Sentence(id="s1", paragraph_id="p1", index=1, text="kommt an."),
            ),
            tokens=tokens,
            units=(
                SenseUnit(
                    id="u1", sentence_id="s1", index=1, start_index=1, end_index=3
                ),
            ),
            records=(record,),
        )
    )
    text = _plain(layout.chapters[0].passages[0].adapted[0].runs)
    assert "; ankommen – приходить" in text
    assert ", відокремлюваний префікс" in text
    note = next(
        item
        for item in layout.chapters[0].passages[0].adapted[0].runs
        if item.style is RunStyle.NOTE
    )
    assert "відокремлюваний префікс" in note.text


@pytest.mark.unit
def test_uk_typography_leaves_source_quotes_alone() -> None:
    assert apply_uk_typography('він сказав "так" -- ні') == "він сказав «так» — ні"
    layout = build_layout(_request())
    original = [
        item.text
        for item in layout.chapters[0].passages[0].adapted[0].runs
        if item.style is RunStyle.ORIGINAL
    ]
    assert any("Oliver" in item for item in original)
