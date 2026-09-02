"""Sentences that skip a clean FAST pass and go to SMART (roadmap 5.3).

German: ``Mood=Sub`` on a finite verb (``wäre``) is irrealis. Hungarian:
``Mood=Cnd`` (``volna``). Idiom termbase hits and long hypotaxis also escalate.
"""

from __future__ import annotations

from frank.domain.model.annotation import Token
from frank.domain.model.book import Sentence
from frank.domain.model.termbase import Term, TermKind

_IRREALIS = frozenset({"sub", "subj", "cnd", "cond"})


def hard_sentence_ids(
    sentences: tuple[Sentence, ...],
    tokens: tuple[Token, ...],
    terms: tuple[Term, ...],
    min_tokens: int,
) -> frozenset[str]:
    """Return sentence ids that must be (re)generated on SMART."""
    grouped = _by_sentence(tokens)
    idioms = tuple(item for item in terms if item.kind is TermKind.IDIOM)
    found: set[str] = set()
    for sentence in sentences:
        piece = grouped.get(sentence.id, ())
        if _is_hard(piece, idioms, min_tokens):
            found.add(sentence.id)
    return frozenset(found)


def _is_hard(
    tokens: tuple[Token, ...], idioms: tuple[Term, ...], min_tokens: int
) -> bool:
    if _content_count(tokens) >= min_tokens:
        return True
    if any(_is_irrealis(token) for token in tokens):
        return True
    return any(_idiom_hits(item, tokens) for item in idioms)


def _content_count(tokens: tuple[Token, ...]) -> int:
    return sum(1 for token in tokens if token.upos != "PUNCT")


def _is_irrealis(token: Token) -> bool:
    mood = (token.morph.value_of("Mood") or "").casefold()
    return mood in _IRREALIS


def _idiom_hits(term: Term, tokens: tuple[Token, ...]) -> bool:
    keys = _token_keys(tokens)
    if term.lemma.casefold() in keys:
        return True
    return any(form.casefold() in keys for form in term.surface_forms)


def _token_keys(tokens: tuple[Token, ...]) -> set[str]:
    keys: set[str] = set()
    for token in tokens:
        keys.add(token.lemma.casefold())
        keys.add(token.surface.casefold())
        if token.reunited_lemma:
            keys.add(token.reunited_lemma.casefold())
    return keys


def _by_sentence(tokens: tuple[Token, ...]) -> dict[str, tuple[Token, ...]]:
    grouped: dict[str, list[Token]] = {}
    for token in tokens:
        grouped.setdefault(token.sentence_id, []).append(token)
    return {key: tuple(value) for key, value in grouped.items()}
