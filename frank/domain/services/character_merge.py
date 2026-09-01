"""Merge chapter Character drafts into book-level rows (roadmap 3.3)."""

from __future__ import annotations

from collections import Counter

from frank.domain.model.termbase import (
    Character,
    CharacterDraft,
    Gender,
    Term,
    TermKind,
)


def merge_characters(
    book_id: str,
    drafts: tuple[CharacterDraft, ...],
    terms: tuple[Term, ...],
) -> tuple[Character, ...]:
    """Union drafts that share a lemma, canonical name, or alias; do not guess gender.

    German: ``Gretel`` listed as an alias of ``Margarete`` becomes one Character.
    Hungarian: ``Sanyi`` with canonical ``Sándor`` merges with the ``Sándor`` draft.
    Conflicting female/male evidence stays ``UNKNOWN`` for the 3.6 review gate.
    """
    groups = _groups(drafts)
    persons = tuple(item for item in terms if item.kind is TermKind.PERSON)
    found = [_character(book_id, group, persons) for group in groups]
    return tuple(
        sorted(found, key=lambda item: (item.canonical_name.casefold(), item.id))
    )


def _groups(
    drafts: tuple[CharacterDraft, ...],
) -> tuple[tuple[CharacterDraft, ...], ...]:
    if not drafts:
        return ()
    parent = list(range(len(drafts)))
    seen: dict[str, int] = {}
    for index, draft in enumerate(drafts):
        for key in _keys(draft):
            prior = seen.get(key)
            if prior is None:
                seen[key] = index
                continue
            _union(parent, index, prior)
            seen[key] = _find(parent, index)
    buckets: dict[int, list[CharacterDraft]] = {}
    for index, draft in enumerate(drafts):
        buckets.setdefault(_find(parent, index), []).append(draft)
    return tuple(tuple(group) for _, group in sorted(buckets.items()))


def _keys(draft: CharacterDraft) -> tuple[str, ...]:
    names = (draft.lemma, draft.canonical_name, *draft.aliases)
    found = [item.casefold().strip() for item in names if item.strip()]
    return tuple(dict.fromkeys(found))


def _find(parent: list[int], index: int) -> int:
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index


def _union(parent: list[int], left: int, right: int) -> None:
    root_left = _find(parent, left)
    root_right = _find(parent, right)
    if root_left != root_right:
        parent[root_right] = root_left


def _character(
    book_id: str,
    drafts: tuple[CharacterDraft, ...],
    persons: tuple[Term, ...],
) -> Character:
    canonical = _canonical_name(drafts)
    aliases = _aliases(drafts, persons, canonical)
    slug = canonical.casefold().replace(" ", "-")
    return Character(
        id=f"{book_id}-char-{slug}",
        book_id=book_id,
        canonical_name=canonical,
        translation_uk=_translation(drafts, persons),
        gender=_gender(drafts),
        aliases=aliases,
        role_note=_role_note(drafts),
    )


def _canonical_name(drafts: tuple[CharacterDraft, ...]) -> str:
    names = [item.canonical_name.strip() or item.lemma for item in drafts]
    counts = Counter(item.casefold() for item in names)
    winner = min(counts, key=lambda key: (-counts[key], len(key), key))
    for name in sorted(names, key=lambda item: (len(item), item)):
        if name.casefold() == winner:
            return name
    return names[0]


def _translation(drafts: tuple[CharacterDraft, ...], terms: tuple[Term, ...]) -> str:
    lemmas = {item.lemma.casefold() for item in drafts}
    for term in sorted(terms, key=lambda item: item.lemma):
        if term.lemma.casefold() in lemmas and term.translation_uk.strip():
            return term.translation_uk.strip()
    for draft in drafts:
        if draft.translation_uk.strip():
            return draft.translation_uk.strip()
    return ""


def _aliases(
    drafts: tuple[CharacterDraft, ...],
    terms: tuple[Term, ...],
    canonical: str,
) -> tuple[str, ...]:
    skip = canonical.casefold()
    found: list[str] = []
    seen: set[str] = set()
    for name in _alias_names(drafts, terms):
        key = name.casefold()
        if not name or key == skip or key in seen:
            continue
        seen.add(key)
        found.append(name)
    return tuple(sorted(found, key=str.casefold))


def _alias_names(
    drafts: tuple[CharacterDraft, ...], terms: tuple[Term, ...]
) -> tuple[str, ...]:
    lemmas = {item.lemma.casefold() for item in drafts}
    names: list[str] = []
    for draft in drafts:
        names.extend(draft.aliases)
    for term in terms:
        if term.lemma.casefold() in lemmas:
            names.extend(term.surface_forms)
    names.extend(item.lemma for item in drafts)
    return tuple(names)


def _gender(drafts: tuple[CharacterDraft, ...]) -> Gender:
    known = {item.gender for item in drafts if item.gender is not Gender.UNKNOWN}
    if len(known) == 1:
        return next(iter(known))
    return Gender.UNKNOWN


def _role_note(drafts: tuple[CharacterDraft, ...]) -> str:
    notes = sorted(
        {item.role_note.strip() for item in drafts if item.role_note.strip()}
    )
    return "; ".join(notes)
