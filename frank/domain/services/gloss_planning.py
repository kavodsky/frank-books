"""Sequential per-lemma gloss decisions (roadmap 2.4). No LLM."""

from __future__ import annotations

from dataclasses import dataclass, field

from frank.domain.model.annotation import (
    Annotation,
    GlossDecision,
    GlossPlanConfig,
    GlossPlanRequest,
    GlossReason,
    Morphology,
    SentencePlacement,
    Token,
)
from frank.domain.model.book import Sentence

_SKIP_UPOS = frozenset({"PUNCT", "SPACE", "SYM"})
_LOCKED = frozenset(
    {GlossReason.IDIOM, GlossReason.FALSE_FRIEND, GlossReason.MORPH_TRAP}
)


@dataclass
class _LemmaMemory:
    first_seen_ordinal: int
    gloss_count: int = 0
    last_glossed_ordinal: int | None = None


@dataclass
class _PassState:
    memory: dict[str, _LemmaMemory] = field(default_factory=dict)
    morph_seen: set[tuple[str, str]] = field(default_factory=set)
    reunited_seen: set[str] = field(default_factory=set)
    pending: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class _BookIndex:
    tokens_for: dict[str, tuple[Token, ...]]
    placement_for: dict[str, SentencePlacement]
    frequent: frozenset[str]
    function_words: frozenset[str]
    false_friends: frozenset[str]
    idioms: frozenset[str]
    ranked: tuple[str, ...]
    lemma_totals: dict[str, int]
    morph_totals: dict[str, int]
    lang: str
    chapter_count: int
    config: GlossPlanConfig


def plan_glosses(request: GlossPlanRequest) -> tuple[GlossDecision, ...]:
    """First successful gloss of a rare lemma; reminders after a long gap.

    German: ``anrufen`` (reunited) is a ``morph_trap`` on first sight, not
    ``rufen``. Hungarian: a rare possessive feature set is a ``morph_trap``;
    ``a`` / ``az`` never gloss. Quota-dropped first occurrences retry until kept.
    """
    index = _book_index(request)
    state = _PassState()
    found: list[GlossDecision] = []
    for sentence in request.annotation.sentences:
        found.extend(_plan_sentence(sentence, index, state))
    return tuple(found)


def _book_index(request: GlossPlanRequest) -> _BookIndex:
    config = request.config
    ranked = request.lists.ranked
    tokens = request.annotation.tokens
    return _BookIndex(
        tokens_for=_tokens_by_sentence(request.annotation),
        placement_for={item.sentence_id: item for item in request.placements},
        frequent=frozenset(ranked[: config.frequency_top_n]),
        function_words=frozenset(ranked[: config.function_word_top_n]),
        false_friends=frozenset(request.lists.false_friends),
        idioms=frozenset(request.lists.idioms),
        ranked=ranked,
        lemma_totals=_lemma_totals(tokens),
        morph_totals=_morph_totals(tokens),
        lang=request.lang,
        chapter_count=request.chapter_count,
        config=config,
    )


def _tokens_by_sentence(annotation: Annotation) -> dict[str, tuple[Token, ...]]:
    grouped: dict[str, list[Token]] = {}
    for token in annotation.tokens:
        grouped.setdefault(token.sentence_id, []).append(token)
    return {
        sentence_id: tuple(sorted(items, key=lambda token: token.index))
        for sentence_id, items in grouped.items()
    }


def _lemma_totals(tokens: tuple[Token, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        if token.upos in _SKIP_UPOS:
            continue
        key = _lemma_key(token)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _morph_totals(tokens: tuple[Token, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        signature = _morph_signature(token.morph)
        if not signature:
            continue
        counts[signature] = counts.get(signature, 0) + 1
    return counts


def _plan_sentence(
    sentence: Sentence, index: _BookIndex, state: _PassState
) -> tuple[GlossDecision, ...]:
    placement = index.placement_for[sentence.id]
    tokens = index.tokens_for.get(sentence.id, ())
    state.pending = set()
    proposed: list[GlossDecision] = []
    for token in tokens:
        reason = _propose(token, index, state, placement.ordinal)
        _remember_seen(state, token, placement.ordinal)
        if reason is None:
            continue
        proposed.append(GlossDecision(token_id=token.id, gloss=True, reason=reason))
        state.pending.add(_lemma_key(token))
    kept = _apply_quota(
        tuple(proposed),
        tokens,
        _sentence_quota(placement.chapter_index, index),
        index.ranked,
    )
    by_id = {token.id: token for token in tokens}
    for decision in kept:
        _remember_glossed(state, by_id[decision.token_id], placement.ordinal)
    return kept


def _propose(
    token: Token, index: _BookIndex, state: _PassState, ordinal: int
) -> GlossReason | None:
    if token.upos in _SKIP_UPOS:
        return None
    key = _lemma_key(token)
    if key in index.idioms:
        return GlossReason.IDIOM
    if key in index.false_friends:
        return GlossReason.FALSE_FRIEND
    trap = _morph_trap(token, index, state)
    if trap is not None:
        return trap
    if key in index.function_words and token.upos != "PROPN":
        return None
    return _ordinary_reason(token, index, state, ordinal)


def _morph_trap(
    token: Token, index: _BookIndex, state: _PassState
) -> GlossReason | None:
    key = _lemma_key(token)
    if token.reunited_lemma and key not in state.reunited_seen:
        state.reunited_seen.add(key)
        return GlossReason.MORPH_TRAP
    if index.lang != "hu":
        return None
    signature = _morph_signature(token.morph)
    pair = (key, signature)
    rare = bool(signature) and index.morph_totals.get(signature, 0) <= (
        index.config.rare_morph_max_count
    )
    if not rare or pair in state.morph_seen:
        return None
    state.morph_seen.add(pair)
    return GlossReason.MORPH_TRAP


def _ordinary_reason(
    token: Token,
    index: _BookIndex,
    state: _PassState,
    ordinal: int,
) -> GlossReason | None:
    key = _lemma_key(token)
    if key in state.pending:
        return None
    memory = state.memory.get(key)
    if _still_unglossed(memory):
        if token.upos == "PROPN" or key not in index.frequent:
            return GlossReason.FIRST_OCCURRENCE
        return None
    if token.upos == "PROPN" or memory is None:
        return None
    return _reminder(key, memory, index, ordinal)


def _still_unglossed(memory: _LemmaMemory | None) -> bool:
    return memory is None or memory.last_glossed_ordinal is None


def _reminder(
    key: str, memory: _LemmaMemory, index: _BookIndex, ordinal: int
) -> GlossReason | None:
    last = memory.last_glossed_ordinal
    if last is None:
        return None
    gap = ordinal - last
    total = index.lemma_totals.get(key, 0)
    if gap < index.config.reminder_gap_sentences:
        return None
    if total >= index.config.reminder_max_occurrences:
        return None
    return GlossReason.REMINDER


def _remember_seen(state: _PassState, token: Token, ordinal: int) -> None:
    if token.upos in _SKIP_UPOS:
        return
    key = _lemma_key(token)
    if key not in state.memory:
        state.memory[key] = _LemmaMemory(first_seen_ordinal=ordinal)


def _remember_glossed(state: _PassState, token: Token, ordinal: int) -> None:
    key = _lemma_key(token)
    memory = state.memory.setdefault(key, _LemmaMemory(first_seen_ordinal=ordinal))
    memory.gloss_count += 1
    memory.last_glossed_ordinal = ordinal


def _sentence_quota(chapter_index: int, index: _BookIndex) -> int:
    config = index.config
    start = config.quota_chapter_start
    end = config.quota_last_third
    count = index.chapter_count
    if count < 3:
        return start
    last_third_from = count - (count // 3) + 1
    if chapter_index >= last_third_from:
        return end
    if chapter_index <= 1:
        return start
    span = last_third_from - 1
    dropped = (start - end) * (chapter_index - 1) // span
    return max(end, start - dropped)


def _apply_quota(
    candidates: tuple[GlossDecision, ...],
    tokens: tuple[Token, ...],
    quota: int,
    ranked: tuple[str, ...],
) -> tuple[GlossDecision, ...]:
    if len(candidates) <= quota:
        return candidates
    by_id = {token.id: token for token in tokens}
    overflow = len(candidates) - quota
    drop_ids = _ids_to_drop(candidates, by_id, overflow, ranked)
    return tuple(item for item in candidates if item.token_id not in drop_ids)


def _ids_to_drop(
    candidates: tuple[GlossDecision, ...],
    by_id: dict[str, Token],
    overflow: int,
    ranked: tuple[str, ...],
) -> frozenset[str]:
    flexible = [item for item in candidates if item.reason not in _LOCKED]
    reminders = [item for item in flexible if item.reason is GlossReason.REMINDER]
    firsts = [item for item in flexible if item.reason is not GlossReason.REMINDER]
    dropped: list[str] = []
    for item in reversed(reminders):
        if len(dropped) >= overflow:
            break
        dropped.append(item.token_id)
    rest = sorted(firsts, key=lambda item: _drop_key(item, by_id, ranked))
    for item in rest:
        if len(dropped) >= overflow:
            break
        dropped.append(item.token_id)
    return frozenset(dropped)


def _drop_key(
    item: GlossDecision, by_id: dict[str, Token], ranked: tuple[str, ...]
) -> tuple[int, int]:
    token = by_id[item.token_id]
    try:
        rank = ranked.index(_lemma_key(token))
    except ValueError:
        rank = len(ranked)
    return (rank, -token.index)


def _lemma_key(token: Token) -> str:
    lemma = token.reunited_lemma or token.lemma
    return lemma.casefold()


def _morph_signature(morph: Morphology) -> str:
    return "|".join(
        f"{feature.key}={feature.value}" for feature in morph.features if feature.value
    )
