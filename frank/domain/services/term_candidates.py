"""Collect Term candidates from NER spans, unknown lemmas, and idiom lists (3.1)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from frank.domain.model.annotation import Token
from frank.domain.model.termbase import Term, TermCollectConfig, TermKind
from frank.domain.ports.linguistics import LemmaLexicon

_ENTITY_LABELS = {
    "PER": TermKind.PERSON,
    "PERSON": TermKind.PERSON,
    "LOC": TermKind.PLACE,
    "GPE": TermKind.PLACE,
    "FAC": TermKind.PLACE,
    "PLACE": TermKind.PLACE,
    "ORG": TermKind.ORG,
}
_CONTENT = frozenset({"NOUN", "VERB", "ADJ"})
_KIND_ORDER = (
    TermKind.PERSON,
    TermKind.PLACE,
    TermKind.ORG,
    TermKind.TITLE,
    TermKind.IDIOM,
    TermKind.DISAMBIG,
)


@dataclass(frozen=True)
class TermCollectRequest:
    book_id: str
    tokens: tuple[Token, ...]
    lexicon: LemmaLexicon
    idioms: tuple[str, ...]
    config: TermCollectConfig


@dataclass
class _Group:
    kind: TermKind
    lemmas: set[str] = field(default_factory=set)
    surfaces: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Mention:
    kind: TermKind
    surface: str
    lemma: str


def collect_terms(request: TermCollectRequest) -> tuple[Term, ...]:
    """Merge analyzer NER spans into unapproved Term rows; no LLM.

    German: ``Oliver`` / ``Olivers`` and ``Berlin`` stay PERSON / PLACE.
    Hungarian: ``Budapesten`` merges with ``Budapest`` (suffix / edit distance).
    ``Sanyi`` is not merged with ``Sándor`` (aliases wait for 3.3).
    """
    entities = _entity_terms(request)
    taken = {item.lemma.casefold() for item in entities}
    extras = _disambig_terms(request, taken) + _idiom_terms(request)
    return _sorted(entities + extras)


def _entity_terms(request: TermCollectRequest) -> tuple[Term, ...]:
    mentions = _mentions(request.tokens)
    found: list[Term] = []
    for kind in (TermKind.PERSON, TermKind.PLACE, TermKind.ORG):
        piece = tuple(item for item in mentions if item.kind is kind)
        found.extend(_terms_from_mentions(request.book_id, kind, piece, request.config))
    return tuple(found)


def _mentions(tokens: Sequence[Token]) -> tuple[_Mention, ...]:
    found: list[_Mention] = []
    run: list[Token] = []
    kind: TermKind | None = None
    sentence_id = ""
    for token in tokens:
        mapped = _ENTITY_LABELS.get(token.ent_type.upper()) if token.ent_type else None
        same = (
            mapped is kind and token.sentence_id == sentence_id and mapped is not None
        )
        if same:
            run.append(token)
            continue
        if run and kind is not None:
            found.append(_mention(kind, run))
        run = [token] if mapped is not None else []
        kind = mapped
        sentence_id = token.sentence_id
    if run and kind is not None:
        found.append(_mention(kind, run))
    return tuple(found)


def _mention(kind: TermKind, run: list[Token]) -> _Mention:
    content = tuple(token for token in run if token.upos != "PUNCT")
    used = content or tuple(run)
    return _Mention(
        kind=kind,
        surface=" ".join(token.surface for token in used),
        lemma=" ".join(token.lemma for token in used).casefold(),
    )


def _terms_from_mentions(
    book_id: str,
    kind: TermKind,
    mentions: tuple[_Mention, ...],
    config: TermCollectConfig,
) -> tuple[Term, ...]:
    groups = _cluster(mentions, config)
    found: list[Term] = []
    for group in groups:
        if len(group.surfaces) < config.entity_min_occurrences:
            continue
        lemma = _canonical(group.lemmas)
        found.append(_term(book_id, kind, lemma, tuple(group.surfaces)))
    return tuple(found)


def _cluster(
    mentions: tuple[_Mention, ...], config: TermCollectConfig
) -> tuple[_Group, ...]:
    groups: list[_Group] = []
    for mention in mentions:
        match = _matching_group(groups, mention.lemma, config)
        if match is None:
            match = _Group(kind=mention.kind, lemmas={mention.lemma})
            groups.append(match)
        match.lemmas.add(mention.lemma)
        match.surfaces.append(mention.surface)
    return tuple(groups)


def _matching_group(
    groups: Sequence[_Group], lemma: str, config: TermCollectConfig
) -> _Group | None:
    for group in groups:
        if any(_mergeable(lemma, other, config) for other in group.lemmas):
            return group
    return None


def _mergeable(left: str, right: str, config: TermCollectConfig) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) < config.merge_min_stem_chars:
        return False
    if left.startswith(right) or right.startswith(left):
        return True
    stem = config.merge_min_stem_chars
    if left[:stem] != right[:stem]:
        return False
    return _levenshtein(left, right) <= config.merge_max_edit_distance


def _canonical(lemmas: set[str]) -> str:
    return min(lemmas, key=lambda item: (len(item), item))


def _disambig_terms(request: TermCollectRequest, taken: set[str]) -> tuple[Term, ...]:
    counts: Counter[str] = Counter()
    surfaces: dict[str, list[str]] = {}
    for token in request.tokens:
        key = token.lemma.casefold()
        if not _is_unknown(token, request.lexicon, taken):
            continue
        counts[key] += 1
        surfaces.setdefault(key, []).append(token.surface)
    found: list[Term] = []
    for lemma, count in counts.items():
        if count < request.config.unknown_lemma_min_count:
            continue
        found.append(
            _term(request.book_id, TermKind.DISAMBIG, lemma, tuple(surfaces[lemma]))
        )
    return tuple(found)


def _is_unknown(token: Token, lexicon: LemmaLexicon, taken: set[str]) -> bool:
    if token.upos not in _CONTENT:
        return False
    key = token.lemma.casefold()
    if not key or key in taken:
        return False
    return not lexicon.contains(key)


def _idiom_terms(request: TermCollectRequest) -> tuple[Term, ...]:
    found: list[Term] = []
    for idiom in request.idioms:
        parts = tuple(part for part in idiom.casefold().split() if part)
        if not parts:
            continue
        hits = _idiom_hits(request.tokens, parts)
        if len(hits) < request.config.idiom_min_occurrences:
            continue
        found.append(_term(request.book_id, TermKind.IDIOM, " ".join(parts), hits))
    return tuple(found)


def _idiom_hits(tokens: Sequence[Token], parts: tuple[str, ...]) -> tuple[str, ...]:
    found: list[str] = []
    width = len(parts)
    for index in range(len(tokens) - width + 1):
        window = tokens[index : index + width]
        lemmas = tuple(token.lemma.casefold() for token in window)
        if lemmas != parts:
            continue
        if len({token.sentence_id for token in window}) != 1:
            continue
        found.append(" ".join(token.surface for token in window))
    return tuple(found)


def _term(book_id: str, kind: TermKind, lemma: str, surfaces: tuple[str, ...]) -> Term:
    unique = tuple(sorted(set(surfaces), key=str.casefold))
    slug = lemma.replace(" ", "-")
    return Term(
        id=f"{book_id}-{kind.value}-{slug}",
        book_id=book_id,
        kind=kind,
        surface_forms=unique,
        lemma=lemma,
    )


def _sorted(terms: tuple[Term, ...]) -> tuple[Term, ...]:
    rank = {kind: index for index, kind in enumerate(_KIND_ORDER)}
    return tuple(sorted(terms, key=lambda item: (rank[item.kind], item.lemma, item.id)))


def _levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    current = [0] * (len(right) + 1)
    for i, source in enumerate(left, start=1):
        current[0] = i
        for j, target in enumerate(right, start=1):
            cost = 0 if source == target else 1
            current[j] = min(
                previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost
            )
        previous, current = current, previous
    return previous[len(right)]
