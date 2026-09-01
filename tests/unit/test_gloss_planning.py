"""Sequential gloss planning (roadmap 2.4)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from frank.domain.model.annotation import (
    Annotation,
    GlossLists,
    GlossPlanConfig,
    GlossPlanRequest,
    GlossReason,
    MorphFeature,
    Morphology,
    SentencePlacement,
    Token,
)
from frank.domain.model.book import Sentence
from frank.domain.services.gloss_planning import plan_glosses

_CFG = GlossPlanConfig(
    frequency_top_n=4,
    function_word_top_n=2,
    reminder_gap_sentences=2,
    reminder_max_occurrences=4,
    quota_chapter_start=6,
    quota_last_third=2,
    rare_morph_max_count=2,
)
_RANKED = ("der", "und", "ist", "mann")


@dataclass(frozen=True)
class _Case:
    tokens: tuple[Token, ...]
    sentences: tuple[Sentence, ...]
    placements: tuple[SentencePlacement, ...]
    lists: GlossLists | None = None
    config: GlossPlanConfig = _CFG
    lang: str = "de"
    chapter_count: int = 1


def _token(
    spec: tuple[str, int, str, str],
    morph: Morphology | None = None,
    reunited: str | None = None,
) -> Token:
    sentence_id, index, lemma, upos = spec
    return Token(
        id=f"{sentence_id}-t{index}",
        sentence_id=sentence_id,
        index=index,
        surface=lemma,
        lemma=lemma,
        upos=upos,
        morph=morph or Morphology(),
        reunited_lemma=reunited,
    )


def _noun(sentence_id: str, index: int, lemma: str) -> Token:
    return _token((sentence_id, index, lemma, "NOUN"))


def _sentence(sentence_id: str, index: int = 1) -> Sentence:
    return Sentence(id=sentence_id, paragraph_id="p1", index=index, text=sentence_id)


def _place(sentence_id: str, ordinal: int, chapter_index: int = 1) -> SentencePlacement:
    return SentencePlacement(
        sentence_id=sentence_id, ordinal=ordinal, chapter_index=chapter_index
    )


def _plan(case: _Case) -> tuple[tuple[str, GlossReason], ...]:
    found = plan_glosses(
        GlossPlanRequest(
            annotation=Annotation(sentences=case.sentences, tokens=case.tokens),
            placements=case.placements,
            chapter_count=case.chapter_count,
            lang=case.lang,
            lists=case.lists or GlossLists(ranked=_RANKED),
            config=case.config,
        )
    )
    return tuple((item.token_id, item.reason) for item in found)


def _reasons(pairs: tuple[tuple[str, GlossReason], ...]) -> dict[str, GlossReason]:
    return dict(pairs)


def _one(tokens: tuple[Token, ...]) -> _Case:
    return _Case(tokens, (_sentence("s1"),), (_place("s1", 1),))


@pytest.mark.unit
def test_punctuation_is_never_glossed() -> None:
    tokens = (_noun("s1", 1, "wald"), _token(("s1", 2, ".", "PUNCT")))
    found = _reasons(_plan(_one(tokens)))
    assert found == {"s1-t1": GlossReason.FIRST_OCCURRENCE}


@pytest.mark.unit
def test_function_words_are_never_glossed() -> None:
    tokens = (_token(("s1", 1, "der", "DET")), _noun("s1", 2, "wald"))
    found = _reasons(_plan(_one(tokens)))
    assert "s1-t1" not in found
    assert found["s1-t2"] is GlossReason.FIRST_OCCURRENCE


@pytest.mark.unit
def test_frequent_lemma_is_not_first_occurrence() -> None:
    assert _plan(_one((_noun("s1", 1, "mann"),))) == ()


@pytest.mark.unit
def test_proper_name_glosses_once_even_if_frequent() -> None:
    tokens = (
        _token(("s1", 1, "mann", "PROPN")),
        _token(("s2", 1, "mann", "PROPN")),
    )
    found = _reasons(
        _plan(
            _Case(
                tokens,
                (_sentence("s1"), _sentence("s2", 2)),
                (_place("s1", 1), _place("s2", 2)),
            )
        )
    )
    assert found == {"s1-t1": GlossReason.FIRST_OCCURRENCE}


@pytest.mark.unit
def test_proper_name_glosses_even_if_listed_as_function_word() -> None:
    tokens = (
        _token(("s1", 1, "der", "PROPN")),
        _token(("s2", 1, "der", "PROPN")),
    )
    found = _reasons(
        _plan(
            _Case(
                tokens,
                (_sentence("s1"), _sentence("s2", 2)),
                (_place("s1", 1), _place("s2", 2)),
            )
        )
    )
    assert found == {"s1-t1": GlossReason.FIRST_OCCURRENCE}


@pytest.mark.unit
def test_reminder_after_gap_when_lemma_is_rare_in_the_book() -> None:
    tokens = (_noun("s1", 1, "wald"), _noun("s2", 1, "bach"), _noun("s3", 1, "wald"))
    found = _reasons(
        _plan(
            _Case(
                tokens,
                (_sentence("s1"), _sentence("s2", 2), _sentence("s3", 3)),
                (_place("s1", 1), _place("s2", 2), _place("s3", 3)),
            )
        )
    )
    assert found["s1-t1"] is GlossReason.FIRST_OCCURRENCE
    assert found["s3-t1"] is GlossReason.REMINDER


@pytest.mark.unit
def test_no_reminder_when_lemma_is_common_in_the_book() -> None:
    tokens = tuple(_noun(f"s{n}", 1, "wald") for n in range(1, 5))
    sentences = tuple(_sentence(f"s{n}", n) for n in range(1, 5))
    placements = tuple(_place(f"s{n}", n) for n in range(1, 5))
    found = _reasons(_plan(_Case(tokens, sentences, placements)))
    assert found["s1-t1"] is GlossReason.FIRST_OCCURRENCE
    assert "s3-t1" not in found
    assert "s4-t1" not in found


@pytest.mark.unit
def test_false_friend_is_always_glossed() -> None:
    found = _reasons(
        _plan(
            _Case(
                (_noun("s1", 1, "gift"),),
                (_sentence("s1"),),
                (_place("s1", 1),),
                lists=GlossLists(ranked=_RANKED, false_friends=("gift",)),
            )
        )
    )
    assert found == {"s1-t1": GlossReason.FALSE_FRIEND}


@pytest.mark.unit
def test_idiom_survives_quota() -> None:
    found = _reasons(
        _plan(
            _Case(
                (
                    _noun("s1", 1, "kutyabol"),
                    _noun("s1", 2, "wald"),
                    _noun("s1", 3, "bach"),
                ),
                (_sentence("s1"),),
                (_place("s1", 1),),
                lists=GlossLists(ranked=_RANKED, idioms=("kutyabol",)),
                config=_CFG.model_copy(update={"quota_chapter_start": 1}),
            )
        )
    )
    assert found == {"s1-t1": GlossReason.IDIOM}


@pytest.mark.unit
def test_reunited_lemma_is_morph_trap() -> None:
    tokens = (
        _token(("s1", 1, "rufen", "VERB"), reunited="anrufen"),
        _token(("s2", 1, "rufen", "VERB"), reunited="anrufen"),
    )
    found = _reasons(
        _plan(
            _Case(
                tokens,
                (_sentence("s1"), _sentence("s2", 2)),
                (_place("s1", 1), _place("s2", 2)),
            )
        )
    )
    assert found["s1-t1"] is GlossReason.MORPH_TRAP
    assert "s2-t1" not in found


@pytest.mark.unit
def test_hungarian_rare_morph_is_trap_once() -> None:
    rare = Morphology(features=(MorphFeature(key="Person", value="1"),))
    common = Morphology(features=(MorphFeature(key="Number", value="Sing"),))
    tokens = (
        _token(("s1", 1, "haz", "NOUN"), morph=rare),
        _token(("s1", 2, "haz", "NOUN"), morph=rare),
        _token(("s1", 3, "kert", "NOUN"), morph=common),
        _token(("s1", 4, "fa", "NOUN"), morph=common),
        _token(("s1", 5, "to", "NOUN"), morph=common),
    )
    found = _reasons(
        _plan(_Case(tokens, (_sentence("s1"),), (_place("s1", 1),), lang="hu"))
    )
    assert found["s1-t1"] is GlossReason.MORPH_TRAP
    assert "s1-t2" not in found
    assert found["s1-t3"] is GlossReason.FIRST_OCCURRENCE


@pytest.mark.unit
def test_quota_drops_reminders_before_first_occurrences() -> None:
    tokens = (
        _noun("s1", 1, "wald"),
        _noun("s1", 2, "bach"),
        _noun("s2", 1, "wald"),
        _noun("s2", 2, "stein"),
        _noun("s2", 3, "moos"),
    )
    found = _reasons(
        _plan(
            _Case(
                tokens,
                (_sentence("s1"), _sentence("s2", 2)),
                (_place("s1", 1), _place("s2", 2)),
                config=_CFG.model_copy(
                    update={"quota_chapter_start": 2, "reminder_gap_sentences": 1}
                ),
            )
        )
    )
    assert found["s2-t2"] is GlossReason.FIRST_OCCURRENCE
    assert found["s2-t3"] is GlossReason.FIRST_OCCURRENCE
    assert "s2-t1" not in found


@pytest.mark.unit
def test_quota_drops_frequent_first_occurrences_first() -> None:
    found = _reasons(
        _plan(
            _Case(
                (_noun("s1", 1, "ist"), _noun("s1", 2, "wald")),
                (_sentence("s1"),),
                (_place("s1", 1),),
                lists=GlossLists(ranked=("der", "ist", "wald")),
                config=_CFG.model_copy(
                    update={
                        "quota_chapter_start": 1,
                        "frequency_top_n": 1,
                        "function_word_top_n": 1,
                    }
                ),
            )
        )
    )
    assert found == {"s1-t2": GlossReason.FIRST_OCCURRENCE}


@pytest.mark.unit
def test_last_third_uses_smaller_quota() -> None:
    tokens = tuple(_noun("s3", index, f"n{index}") for index in range(1, 7))
    found = _plan(
        _Case(
            tokens,
            (_sentence("s3"),),
            (_place("s3", 1, chapter_index=3),),
            lists=GlossLists(),
            chapter_count=3,
        )
    )
    assert len(found) == 2


@pytest.mark.unit
def test_single_chapter_keeps_start_quota() -> None:
    tokens = tuple(_noun("s1", index, f"n{index}") for index in range(1, 8))
    found = _plan(
        _Case(tokens, (_sentence("s1"),), (_place("s1", 1),), lists=GlossLists())
    )
    assert len(found) == 6


@pytest.mark.unit
def test_short_ranked_list_uses_every_entry() -> None:
    found = _reasons(
        _plan(
            _Case(
                (_token(("s1", 1, "der", "DET")), _noun("s1", 2, "wald")),
                (_sentence("s1"),),
                (_place("s1", 1),),
                lists=GlossLists(ranked=("der",)),
                config=_CFG.model_copy(
                    update={"frequency_top_n": 1000, "function_word_top_n": 300}
                ),
            )
        )
    )
    assert "s1-t1" not in found
    assert found["s1-t2"] is GlossReason.FIRST_OCCURRENCE


@pytest.mark.unit
def test_rerun_is_byte_identical() -> None:
    tokens = (
        _noun("s1", 1, "wald"),
        _token(("s1", 2, "anrufen", "VERB"), reunited="anrufen"),
        _token(("s1", 3, ".", "PUNCT")),
    )
    request = GlossPlanRequest(
        annotation=Annotation(sentences=(_sentence("s1"),), tokens=tokens),
        placements=(_place("s1", 1),),
        chapter_count=1,
        lang="de",
        lists=GlossLists(ranked=_RANKED, false_friends=("gift",)),
        config=_CFG,
    )
    assert plan_glosses(request) == plan_glosses(request)


@pytest.mark.unit
def test_quota_dropped_first_occurrence_retries() -> None:
    found = _reasons(
        _plan(
            _Case(
                (
                    _noun("s1", 1, "wald"),
                    _noun("s1", 2, "bach"),
                    _noun("s2", 1, "wald"),
                ),
                (_sentence("s1"), _sentence("s2", 2)),
                (_place("s1", 1), _place("s2", 2)),
                lists=GlossLists(ranked=("der", "wald", "bach")),
                config=_CFG.model_copy(
                    update={
                        "quota_chapter_start": 1,
                        "frequency_top_n": 1,
                        "function_word_top_n": 1,
                    }
                ),
            )
        )
    )
    assert "s1-t1" not in found
    assert found["s1-t2"] is GlossReason.FIRST_OCCURRENCE
    assert found["s2-t1"] is GlossReason.FIRST_OCCURRENCE
