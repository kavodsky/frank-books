"""spaCy adapters split sentences and emit tokens (roadmap 2.1–2.2)."""

from __future__ import annotations

import pytest
import spacy

from frank.config import NlpSettings
from frank.domain.errors import UnknownError
from frank.infrastructure.nlp.german import GermanAnalyzer
from frank.infrastructure.nlp.hungarian import HungarianAnalyzer
from frank.infrastructure.nlp.load import load_analyzer


def _senter(lang: str):
    nlp = spacy.blank(lang)
    nlp.add_pipe("sentencizer")
    return nlp


def _has_model(name: str) -> bool:
    try:
        spacy.load(name)
    except OSError:
        return False
    return True


@pytest.mark.integration
def test_german_senter_splits_two_sentences() -> None:
    parsed = GermanAnalyzer(_senter("de")).analyze("Es war einmal. Am Morgen ging er.")
    assert tuple(item.text for item in parsed) == (
        "Es war einmal.",
        "Am Morgen ging er.",
    )
    assert parsed[0].tokens[0].surface == "Es"
    assert all(token.lemma for token in parsed[0].tokens)


@pytest.mark.integration
def test_hungarian_senter_splits_two_sentences() -> None:
    parsed = HungarianAnalyzer(_senter("hu")).analyze(
        "Egyszer volt, hol nem volt. A királyfi elindult."
    )
    assert len(parsed) == 2
    assert parsed[0].text.startswith("Egyszer volt")
    assert parsed[1].text.startswith("A királyfi")
    assert all(token.lemma for token in parsed[1].tokens)


@pytest.mark.integration
def test_german_second_lemma_uses_simplemma() -> None:
    analyzer = GermanAnalyzer(_senter("de"))
    assert analyzer.second_lemma("sah", "VERB") == "sehen"


@pytest.mark.integration
def test_blank_paragraph_is_zero_sentences() -> None:
    assert GermanAnalyzer(_senter("de")).analyze("   ") == ()


@pytest.mark.integration
def test_load_analyzer_rejects_unknown_language() -> None:
    settings = NlpSettings(
        german_model="de_core_news_lg",
        hungarian_model="x",
        lemma_batch_size=50,
        short_sentence_max_tokens=8,
        sense_unit_min_tokens=3,
        sense_unit_max_tokens=8,
        heavy_pp_min_tokens=6,
    )
    with pytest.raises(UnknownError, match="unsupported source language"):
        load_analyzer("fr", settings)


@pytest.mark.integration
@pytest.mark.skipif(
    not _has_model("de_core_news_lg"), reason="de_core_news_lg not installed"
)
def test_german_lg_keeps_abbreviation_in_one_sentence() -> None:
    parsed = GermanAnalyzer(spacy.load("de_core_news_lg")).analyze(
        "Dr. Müller ging nach Hause. Es schneite."
    )
    assert len(parsed) == 2
    assert parsed[0].text.startswith("Dr. Müller")


@pytest.mark.integration
@pytest.mark.skipif(
    not _has_model("de_core_news_lg"), reason="de_core_news_lg not installed"
)
def test_german_lg_tokens_carry_lemma_upos_and_case() -> None:
    parsed = GermanAnalyzer(spacy.load("de_core_news_lg")).analyze(
        "Der Arzt sah das Kind."
    )
    tokens = parsed[0].tokens
    det = next(token for token in tokens if token.surface == "Der")
    verb = next(token for token in tokens if token.surface == "sah")
    assert all(token.lemma for token in tokens)
    assert det.upos == "DET"
    assert det.morph.value_of("Case") == "Nom"
    assert verb.upos == "VERB"
    assert verb.lemma == "sehen"


@pytest.mark.integration
@pytest.mark.skipif(
    not _has_model("de_core_news_lg"), reason="de_core_news_lg not installed"
)
def test_german_lg_tags_person_and_place() -> None:
    parsed = GermanAnalyzer(spacy.load("de_core_news_lg")).analyze(
        "Dr. Müller fuhr nach Berlin."
    )
    tokens = parsed[0].tokens
    person = next(token for token in tokens if token.surface == "Müller")
    place = next(token for token in tokens if token.surface == "Berlin")
    assert person.ent_type in {"PER", "PERSON"}
    assert place.ent_type in {"LOC", "GPE", "PLACE"}


@pytest.mark.integration
@pytest.mark.skipif(
    not _has_model("hu_core_news_lg"), reason="hu_core_news_lg not installed"
)
def test_hungarian_lg_keeps_abbreviation_in_one_sentence() -> None:
    parsed = HungarianAnalyzer(spacy.load("hu_core_news_lg")).analyze(
        "Dr. Kovács elindult. Havazott."
    )
    assert len(parsed) == 2
    assert parsed[0].text.startswith("Dr. Kovács")


@pytest.mark.integration
@pytest.mark.skipif(
    not _has_model("hu_core_news_lg"), reason="hu_core_news_lg not installed"
)
def test_hungarian_lg_tokens_carry_lemma_and_possessive() -> None:
    parsed = HungarianAnalyzer(spacy.load("hu_core_news_lg")).analyze("A háza üres.")
    noun = next(token for token in parsed[0].tokens if token.surface == "háza")
    assert noun.lemma
    assert noun.upos in {"NOUN", "PROPN"}
    assert noun.morph.value_of("Number[psor]") or noun.morph.value_of("Person[psor]")
