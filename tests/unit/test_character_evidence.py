"""PERSON evidence sentences per chapter (roadmap 3.3)."""

from __future__ import annotations

import pytest

from frank.domain.model.annotation import Morphology, Token
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
    CharacterEvidenceConfig,
    Term,
    TermKind,
)
from frank.domain.services.character_evidence import (
    CharacterEvidenceRequest,
    collect_chapter_evidence,
)

_CFG = CharacterEvidenceConfig(evidence_sentences_per_person=3)
_CUES = frozenset({"frau", "úr"})


def _book() -> Book:
    return Book(
        id="b",
        slug="s",
        lang="de",
        title="T",
        author="",
        source_url="file.txt",
        license_note="",
        status=BookStatus.INGESTED,
    )


def _paragraph(chapter_id: str, index: int) -> Paragraph:
    return Paragraph(
        id=f"{chapter_id}-p{index}",
        chapter_id=chapter_id,
        passage_id=None,
        index=index,
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


def _token(sentence_id: str, index: int, surface: str, *, cue: bool = False) -> Token:
    lemma = "frau" if cue else surface
    return Token(
        id=f"{sentence_id}-t{index}",
        sentence_id=sentence_id,
        index=index,
        surface=surface,
        lemma=lemma,
        upos="PROPN",
        morph=Morphology(),
        ent_type="PER",
    )


def _person(lemma: str, surfaces: tuple[str, ...]) -> Term:
    return Term(
        id=f"b-PERSON-{lemma}",
        book_id="b",
        kind=TermKind.PERSON,
        surface_forms=surfaces,
        lemma=lemma,
        translation_uk="Олівер" if lemma == "oliver" else "",
    )


def _lemmas(
    request: CharacterEvidenceRequest,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    evidence = collect_chapter_evidence(request)
    return tuple(
        (item.chapter_id, tuple(person.lemma for person in item.persons))
        for item in evidence
    )


@pytest.mark.unit
def test_gender_cue_sentence_outranks_bare_mention() -> None:
    chapter = Chapter(id="b-c1", book_id="b", index=1, title="K")
    paragraph = _paragraph("b-c1", 1)
    bare = _sentence(paragraph.id, 1, "Oliver ging.")
    cued = _sentence(paragraph.id, 2, "Frau Oliver sprach.")
    extra = _sentence(paragraph.id, 3, "Oliver rief.")
    tokens = (
        _token(bare.id, 1, "Oliver"),
        _token(cued.id, 1, "Frau", cue=True),
        _token(cued.id, 2, "Oliver"),
        _token(extra.id, 1, "Oliver"),
    )
    evidence = collect_chapter_evidence(
        CharacterEvidenceRequest(
            structure=BookStructure(
                book=_book(), chapters=(chapter,), paragraphs=(paragraph,)
            ),
            sentences=(bare, cued, extra),
            tokens=tokens,
            persons=(_person("oliver", ("Oliver",)),),
            gender_cues=_CUES,
            config=CharacterEvidenceConfig(evidence_sentences_per_person=2),
        )
    )
    assert evidence[0].persons[0].sentences == ("Frau Oliver sprach.", "Oliver ging.")


@pytest.mark.unit
def test_nickname_stays_separate_person_evidence() -> None:
    chapter = Chapter(id="b-c1", book_id="b", index=1, title="K")
    paragraph = _paragraph("b-c1", 1)
    sanyi = _sentence(paragraph.id, 1, "Sanyi nevetett.")
    sandor = _sentence(paragraph.id, 2, "Sándor úr jött.")
    tokens = (
        _token(sanyi.id, 1, "Sanyi"),
        _token(sandor.id, 1, "Sándor"),
        Token(
            id=f"{sandor.id}-t2",
            sentence_id=sandor.id,
            index=2,
            surface="úr",
            lemma="úr",
            upos="NOUN",
            morph=Morphology(),
        ),
    )
    persons = (
        _person("sanyi", ("Sanyi",)),
        _person("sándor", ("Sándor",)),
    )
    found = _lemmas(
        CharacterEvidenceRequest(
            structure=BookStructure(
                book=_book(), chapters=(chapter,), paragraphs=(paragraph,)
            ),
            sentences=(sanyi, sandor),
            tokens=tokens,
            persons=persons,
            gender_cues=_CUES,
            config=_CFG,
        )
    )
    assert found == (("b-c1", ("sanyi", "sándor")),)


@pytest.mark.unit
def test_chapter_without_person_is_skipped() -> None:
    c1 = Chapter(id="b-c1", book_id="b", index=1, title="K1")
    c2 = Chapter(id="b-c2", book_id="b", index=2, title="K2")
    p1 = _paragraph("b-c1", 1)
    p2 = _paragraph("b-c2", 1)
    s1 = _sentence(p1.id, 1, "Oliver ging.")
    s2 = _sentence(p2.id, 1, "Berlin schlief.")
    tokens = (
        _token(s1.id, 1, "Oliver"),
        Token(
            id=f"{s2.id}-t1",
            sentence_id=s2.id,
            index=1,
            surface="Berlin",
            lemma="Berlin",
            upos="PROPN",
            morph=Morphology(),
            ent_type="LOC",
        ),
    )
    found = _lemmas(
        CharacterEvidenceRequest(
            structure=BookStructure(
                book=_book(), chapters=(c1, c2), paragraphs=(p1, p2)
            ),
            sentences=(s1, s2),
            tokens=tokens,
            persons=(_person("oliver", ("Oliver",)),),
            gender_cues=_CUES,
            config=_CFG,
        )
    )
    assert found == (("b-c1", ("oliver",)),)


@pytest.mark.unit
def test_place_terms_are_ignored() -> None:
    chapter = Chapter(id="b-c1", book_id="b", index=1, title="K")
    paragraph = _paragraph("b-c1", 1)
    sentence = _sentence(paragraph.id, 1, "Berlin.")
    token = Token(
        id=f"{sentence.id}-t1",
        sentence_id=sentence.id,
        index=1,
        surface="Berlin",
        lemma="berlin",
        upos="PROPN",
        morph=Morphology(),
        ent_type="LOC",
    )
    place = Term(
        id="b-PLACE-berlin",
        book_id="b",
        kind=TermKind.PLACE,
        surface_forms=("Berlin",),
        lemma="berlin",
    )
    assert (
        _lemmas(
            CharacterEvidenceRequest(
                structure=BookStructure(
                    book=_book(), chapters=(chapter,), paragraphs=(paragraph,)
                ),
                sentences=(sentence,),
                tokens=(token,),
                persons=(place,),
                gender_cues=_CUES,
                config=_CFG,
            )
        )
        == ()
    )
