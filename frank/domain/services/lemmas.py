"""Dual-lemmatizer disagreement and OOV collection (roadmap 2.2b)."""

from __future__ import annotations

from collections.abc import Sequence

from frank.domain.model.annotation import Annotation, Token
from frank.domain.model.lemma import (
    DisputedLemma,
    LemmaOverride,
    LemmaPair,
    LemmaPartition,
    LemmaType,
)
from frank.domain.ports.linguistics import LemmaLexicon

_SKIP_UPOS = frozenset({"PUNCT", "SYM", "NUM", "SPACE"})


def lemma_types(annotation: Annotation) -> tuple[LemmaType, ...]:
    """One type per (surface, UPOS) in reading order, with one example sentence.

    German: every ``sah`` / VERB shares one type, example ``Der Arzt sah das Kind.``
    Hungarian: every ``felállt`` / VERB likewise.
    """
    texts = {sentence.id: sentence.text for sentence in annotation.sentences}
    seen: dict[tuple[str, str], LemmaType] = {}
    for token in annotation.tokens:
        if token.upos in _SKIP_UPOS:
            continue
        key = (token.surface, token.upos)
        if key in seen:
            continue
        seen[key] = LemmaType(
            surface=token.surface,
            upos=token.upos,
            example_sentence=texts[token.sentence_id],
            analyzer_lemma=token.lemma,
        )
    return tuple(seen.values())


def partition_lemmas(
    pairs: Sequence[LemmaPair], lexicon: LemmaLexicon
) -> LemmaPartition:
    """Dispute analyzer/second disagreements and OOV forms; never send punctuation.

    German: ``sah`` vs simplemma ``sehen`` is disputed.
    Hungarian: a form missing from ``data/hu_frequency_top.txt`` is disputed even
    when both lemmatizers agree.
    """
    disputed = tuple(
        _as_dispute(pair) for pair in pairs if _needs_arbitration(pair, lexicon)
    )
    return LemmaPartition(disputed=disputed)


def apply_overrides(
    tokens: tuple[Token, ...], overrides: Sequence[LemmaOverride]
) -> tuple[Token, ...]:
    """Write chosen lemmas onto matching (surface, UPOS) tokens."""
    chosen = {(item.surface, item.upos): item.lemma for item in overrides}
    return tuple(
        token.model_copy(update={"lemma": chosen[token.surface, token.upos]})
        if (token.surface, token.upos) in chosen
        else token
        for token in tokens
    )


def _needs_arbitration(pair: LemmaPair, lexicon: LemmaLexicon) -> bool:
    if pair.analyzer_lemma.casefold() != pair.second_lemma.casefold():
        return True
    known = lexicon.contains(pair.analyzer_lemma) or lexicon.contains(pair.surface)
    return not known


def _as_dispute(pair: LemmaPair) -> DisputedLemma:
    return DisputedLemma(
        surface=pair.surface,
        upos=pair.upos,
        example_sentence=pair.example_sentence,
        analyzer_lemma=pair.analyzer_lemma,
        second_lemma=pair.second_lemma,
    )
