"""Clause-level SenseUnit spans over a dependency parse (roadmap 2.3)."""

from __future__ import annotations

from frank.domain.model.annotation import (
    Annotation,
    SegmentationConfig,
    SenseUnit,
    Token,
)
from frank.domain.model.book import Sentence

_VERBAL = frozenset({"VERB", "AUX"})
_NON_FINITE = frozenset({"Inf", "Part", "Ger"})
_COORD_DEPS = frozenset({"cd", "cc"})
_PP_DEPS = frozenset({"mo", "obl", "nmod", "mnr", "pg"})


def segment_annotation(
    annotation: Annotation, config: SegmentationConfig
) -> tuple[SenseUnit, ...]:
    found: list[SenseUnit] = []
    for sentence in annotation.sentences:
        tokens = tuple(
            token for token in annotation.tokens if token.sentence_id == sentence.id
        )
        found.extend(segment_sentence(sentence, tokens, config))
    return tuple(found)


def segment_sentence(
    sentence: Sentence,
    tokens: tuple[Token, ...],
    config: SegmentationConfig,
) -> tuple[SenseUnit, ...]:
    """Split at finite-verb clauses, coordinations, and heavy PPs; never split ≤8.

    German: ``Als er aufstand, sah er, dass der Wald still war.`` → three units
    (subordinate, main, complement). Hungarian: ``Amikor megérkezett a várba,
    az őrök kinyitották a kaput.`` → two units at the finite ``conj``.
    """
    ordered = tuple(sorted(tokens, key=lambda token: token.index))
    if not ordered:
        return ()
    spans = _spans_for(ordered, config)
    return tuple(
        _unit(sentence, index, start, end)
        for index, (start, end) in enumerate(spans, start=1)
    )


def _spans_for(
    tokens: tuple[Token, ...], config: SegmentationConfig
) -> list[tuple[int, int]]:
    full = (tokens[0].index, tokens[-1].index)
    if _content_count(tokens, full) <= config.short_sentence_max_tokens:
        return [full]
    spans = _clause_spans(tokens)
    spans = _move_leading_punct(tokens, spans)
    spans = _move_trailing_coordinator(tokens, spans)
    spans = _merge_fragments(tokens, spans, config.unit_min_tokens)
    spans = _split_heavy_oversize(tokens, spans, config)
    return _cover_sentence(tokens, spans)


def _clause_spans(tokens: tuple[Token, ...]) -> list[tuple[int, int]]:
    by_index = {token.index: token for token in tokens}
    heads = frozenset(token.index for token in tokens if _is_clause_head(token))
    if not heads:
        return [(tokens[0].index, tokens[-1].index)]
    owners = [_owner_index(token, by_index, heads) for token in tokens]
    spans: list[tuple[int, int]] = []
    start = 0
    for index in range(1, len(tokens) + 1):
        if index < len(tokens) and owners[index] == owners[start]:
            continue
        spans.append((tokens[start].index, tokens[index - 1].index))
        start = index
    return spans


def _owner_index(
    token: Token, by_index: dict[int, Token], heads: frozenset[int]
) -> int:
    current = token
    seen: set[int] = set()
    while current.index not in seen:
        seen.add(current.index)
        if current.index in heads:
            return current.index
        parent = by_index.get(current.head_index)
        if parent is None:
            return current.index
        current = parent
    return token.index


def _is_clause_head(token: Token) -> bool:
    if token.upos not in _VERBAL:
        return False
    form = token.morph.value_of("VerbForm")
    return form not in _NON_FINITE


def _move_leading_punct(
    tokens: tuple[Token, ...], spans: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    if len(spans) < 2:
        return spans
    by_index = {token.index: token for token in tokens}
    out = [spans[0]]
    for start, end in spans[1:]:
        while start < end and by_index[start].upos == "PUNCT":
            prev_start, _prev_end = out[-1]
            out[-1] = (prev_start, start)
            nxt = _neighbor(tokens, start, 1)
            if nxt is None:
                break
            start = nxt
        out.append((start, end))
    return out


def _move_trailing_coordinator(
    tokens: tuple[Token, ...], spans: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    if len(spans) < 2:
        return spans
    by_index = {token.index: token for token in tokens}
    out = [list(span) for span in spans]
    for index in range(len(out) - 1):
        start, end = out[index]
        while start < end and _is_coordinator(by_index[end]):
            out[index + 1][0] = end
            prev = _neighbor(tokens, end, -1)
            if prev is None:
                break
            end = prev
            out[index][1] = end
    return [(span[0], span[1]) for span in out]


def _merge_fragments(
    tokens: tuple[Token, ...],
    spans: list[tuple[int, int]],
    min_tokens: int,
) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for span in spans:
        if not out:
            out.append(span)
            continue
        if _should_merge(tokens, out[-1], span, min_tokens):
            out[-1] = (out[-1][0], span[1])
            continue
        out.append(span)
    return out


def _should_merge(
    tokens: tuple[Token, ...],
    previous: tuple[int, int],
    current: tuple[int, int],
    min_tokens: int,
) -> bool:
    prev_headed = _has_clause_head(tokens, previous)
    headed = _has_clause_head(tokens, current)
    if prev_headed and headed:
        return False
    leftover = current if not headed else previous
    return _content_count(tokens, leftover) < min_tokens


def _split_heavy_oversize(
    tokens: tuple[Token, ...],
    spans: list[tuple[int, int]],
    config: SegmentationConfig,
) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for span in spans:
        found.extend(_split_one_pp(tokens, span, config))
    return _merge_fragments(tokens, found, config.unit_min_tokens)


def _split_one_pp(
    tokens: tuple[Token, ...],
    span: tuple[int, int],
    config: SegmentationConfig,
) -> list[tuple[int, int]]:
    if _content_count(tokens, span) <= config.unit_max_tokens:
        return [span]
    pp = _first_heavy_pp(tokens, span, config.heavy_pp_min_tokens)
    if pp is None:
        return [span]
    start, end = span
    lo, hi = pp
    pieces = [(start, lo - 1), (lo, hi), (hi + 1, end)]
    return [
        piece
        for piece in pieces
        if piece[0] <= piece[1] and _span_exists(tokens, piece)
    ]


def _first_heavy_pp(
    tokens: tuple[Token, ...], span: tuple[int, int], min_tokens: int
) -> tuple[int, int] | None:
    start, end = span
    for token in tokens:
        if token.index < start or token.index > end:
            continue
        if not _is_pp_anchor(token):
            continue
        found = _subtree_span(token, tokens, start, end)
        if found is None:
            continue
        if found == span:
            continue
        if _content_count(tokens, found) >= min_tokens:
            return found
    return None


def _is_pp_anchor(token: Token) -> bool:
    dep = token.dep.split(":")[0]
    if token.upos == "ADP" and dep in _PP_DEPS:
        return True
    return dep in {"obl", "nmod"}


def _subtree_span(
    anchor: Token, tokens: tuple[Token, ...], start: int, end: int
) -> tuple[int, int] | None:
    by_index = {token.index: token for token in tokens}
    members = {
        token.index
        for token in tokens
        if start <= token.index <= end and _in_subtree(token, anchor, by_index)
    }
    if not members:
        return None
    lo, hi = min(members), max(members)
    for token in tokens:
        inside = lo <= token.index <= hi
        stray = token.index not in members and token.upos != "PUNCT"
        if inside and stray:
            return None
    return lo, hi


def _in_subtree(token: Token, anchor: Token, by_index: dict[int, Token]) -> bool:
    if token.index == anchor.index:
        return True
    current = token
    seen: set[int] = set()
    while current.index not in seen:
        seen.add(current.index)
        parent = by_index.get(current.head_index)
        if parent is None:
            return False
        if parent.index == anchor.index:
            return True
        current = parent
    return False


def _cover_sentence(
    tokens: tuple[Token, ...], spans: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    if not spans:
        return [(tokens[0].index, tokens[-1].index)]
    first, last = tokens[0].index, tokens[-1].index
    spans[0] = (first, spans[0][1])
    spans[-1] = (spans[-1][0], last)
    return spans


def _has_clause_head(tokens: tuple[Token, ...], span: tuple[int, int]) -> bool:
    start, end = span
    return any(
        start <= token.index <= end and _is_clause_head(token) for token in tokens
    )


def _is_coordinator(token: Token) -> bool:
    if token.upos == "CCONJ":
        return True
    return token.dep.split(":")[0] in _COORD_DEPS


def _content_count(tokens: tuple[Token, ...], span: tuple[int, int]) -> int:
    start, end = span
    return sum(
        1 for token in tokens if start <= token.index <= end and token.upos != "PUNCT"
    )


def _neighbor(tokens: tuple[Token, ...], index: int, step: int) -> int | None:
    ordered = [token.index for token in tokens]
    pos = ordered.index(index) + step
    if pos < 0 or pos >= len(ordered):
        return None
    return ordered[pos]


def _span_exists(tokens: tuple[Token, ...], span: tuple[int, int]) -> bool:
    start, end = span
    return any(start <= token.index <= end for token in tokens)


def _unit(sentence: Sentence, index: int, start: int, end: int) -> SenseUnit:
    return SenseUnit(
        id=f"{sentence.id}-u{index}",
        sentence_id=sentence.id,
        index=index,
        start_index=start,
        end_index=end,
    )
