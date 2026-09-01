"""Dialogue T/V heuristics (roadmap 3.4)."""

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
from frank.domain.model.termbase import AddressCues, Character, Gender, TvForm
from frank.domain.services.address_detect import (
    AddressDetectRequest,
    collect_address_observations,
)

_DE = AddressCues(
    t_lemmas=("du", "dich", "dir", "dein"),
    v_lemmas=("sie", "ihnen", "ihr"),
    v_surfaces=("Sie", "Ihnen", "Ihrer"),
    speech_lemmas=("sagen", "reden", "fragen"),
)
_HU = AddressCues(
    t_lemmas=("te", "téged", "neked"),
    v_lemmas=("ön", "maga", "tetszik"),
    v_surfaces=(),
    speech_lemmas=("mond", "kérdez"),
)


def _book(lang: str = "de") -> Book:
    return Book(
        id="b",
        slug="s",
        lang=lang,
        title="T",
        author="",
        source_url="file.txt",
        license_note="",
        status=BookStatus.INGESTED,
    )


def _para(text: str) -> Paragraph:
    return Paragraph(
        id="b-c1-p1",
        chapter_id="b-c1",
        passage_id=None,
        index=1,
        raw_text=text,
        hash="h",
        status=ParagraphStatus.RAW,
    )


def _sent(text: str) -> Sentence:
    return Sentence(id="s1", paragraph_id="b-c1-p1", index=1, text=text)


def _tok(index: int, surface: str, lemma: str, upos: str = "PRON") -> Token:
    return Token(
        id=f"s1-t{index}",
        sentence_id="s1",
        index=index,
        surface=surface,
        lemma=lemma,
        upos=upos,
        morph=Morphology(),
    )


def _char(name: str, aliases: tuple[str, ...] = ()) -> Character:
    slug = name.casefold().replace(" ", "-")
    return Character(
        id=f"b-char-{slug}",
        book_id="b",
        canonical_name=name,
        translation_uk=name,
        gender=Gender.MALE,
        aliases=aliases,
    )


def _obs(text: str, tokens: tuple[Token, ...], *, lang: str = "de"):
    cues = _DE if lang == "de" else _HU
    return collect_address_observations(
        AddressDetectRequest(
            structure=BookStructure(
                book=_book(lang),
                chapters=(Chapter(id="b-c1", book_id="b", index=1, title="K"),),
                paragraphs=(_para(text),),
            ),
            sentences=(_sent(text),),
            tokens=tokens,
            characters=(
                _char("Oliver"),
                _char("Bumble", ("Mr. Bumble",)),
                _char("Sándor"),
                _char("Gábor"),
            ),
            cues=cues,
        )
    )


@pytest.mark.unit
def test_german_du_with_vocative_and_speech_verb() -> None:
    text = "«Willst du mit mir gehen, Oliver?» redete ihn Mr. Bumble an."
    tokens = (
        _tok(0, "Willst", "wollen", "VERB"),
        _tok(1, "du", "du"),
        _tok(2, "mit", "mit", "ADP"),
        _tok(3, "mir", "ich", "PRON"),
        _tok(4, "gehen", "gehen", "VERB"),
        _tok(5, "Oliver", "Oliver", "PROPN"),
        _tok(6, "redete", "reden", "VERB"),
        _tok(7, "ihn", "er", "PRON"),
        _tok(8, "Mr.", "Mr.", "PROPN"),
        _tok(9, "Bumble", "Bumble", "PROPN"),
        _tok(10, "an", "an", "ADP"),
    )
    found = _obs(text, tokens)
    assert len(found) == 1
    assert found[0].speaker_id == "b-char-bumble"
    assert found[0].addressee_id == "b-char-oliver"
    assert found[0].tv_form is TvForm.T


@pytest.mark.unit
def test_german_sie_in_dialogue_is_v() -> None:
    text = "«Sie sind ein Gelehrter, Mr. Bumble», sagte Oliver."
    tokens = (
        _tok(0, "Sie", "sie"),
        _tok(1, "sind", "sein", "VERB"),
        _tok(2, "ein", "ein", "DET"),
        _tok(3, "Gelehrter", "Gelehrter", "NOUN"),
        _tok(4, "Mr.", "Mr.", "PROPN"),
        _tok(5, "Bumble", "Bumble", "PROPN"),
        _tok(6, "sagte", "sagen", "VERB"),
        _tok(7, "Oliver", "Oliver", "PROPN"),
    )
    found = _obs(text, tokens)
    assert found[0].speaker_id == "b-char-oliver"
    assert found[0].addressee_id == "b-char-bumble"
    assert found[0].tv_form is TvForm.V


@pytest.mark.unit
def test_narrative_sie_is_ignored() -> None:
    text = "Sie gingen nach Hause."
    tokens = (_tok(0, "Sie", "sie"), _tok(1, "gingen", "gehen", "VERB"))
    assert _obs(text, tokens) == ()


@pytest.mark.unit
def test_hungarian_te_is_t() -> None:
    text = "— Te vagy az, Sándor — mondta Gábor."
    tokens = (
        _tok(0, "Te", "te"),
        _tok(1, "vagy", "van", "VERB"),
        _tok(2, "az", "az", "PRON"),
        _tok(3, "Sándor", "Sándor", "PROPN"),
        _tok(4, "mondta", "mond", "VERB"),
        _tok(5, "Gábor", "Gábor", "PROPN"),
    )
    found = _obs(text, tokens, lang="hu")
    assert found[0].speaker_id == "b-char-gábor"
    assert found[0].addressee_id == "b-char-sándor"
    assert found[0].tv_form is TvForm.T


@pytest.mark.unit
def test_unattributed_address_is_dropped_from_roles() -> None:
    text = "— Du kommst mit."
    tokens = (
        _tok(0, "Du", "du"),
        _tok(1, "kommst", "kommen", "VERB"),
        _tok(2, "mit", "mit", "ADP"),
    )
    found = _obs(text, tokens)
    assert found[0].speaker_id is None
    assert found[0].addressee_id is None
    assert found[0].tv_form is TvForm.T
