"""Human review TOML for terms, characters, and T/V (roadmap 3.6)."""

from __future__ import annotations

from frank.domain.errors import SchemaInvalid, TermbaseNotApproved
from frank.domain.model.termbase import (
    AddressPair,
    Character,
    Gender,
    ReviewAddressPair,
    ReviewCharacter,
    ReviewDocument,
    ReviewTerm,
    Term,
    TermbaseSnapshot,
)
from frank.domain.services.termbase_review_toml import (
    load_review_toml,
    render_review_toml,
)

__all__ = [
    "apply_review",
    "document_from_termbase",
    "parse_review_toml",
    "render_review_toml",
    "require_approved_termbase",
]


def document_from_termbase(snapshot: TermbaseSnapshot) -> ReviewDocument:
    """Stable review rows; approved is not exported because import always sets it."""
    return ReviewDocument(
        terms=tuple(_review_term(item) for item in _sorted_terms(snapshot.terms)),
        characters=tuple(
            _review_character(item) for item in _sorted_characters(snapshot.characters)
        ),
        address_pairs=tuple(
            _review_pair(item) for item in _sorted_pairs(snapshot.address_pairs)
        ),
    )


def parse_review_toml(text: str) -> ReviewDocument:
    """Reject malformed TOML, unknown enums, duplicates, and dangling T/V ends."""
    document = load_review_toml(text)
    _assert_review(document)
    return document


def apply_review(book_id: str, document: ReviewDocument) -> TermbaseSnapshot:
    """Replace the three collections from the file; every Term becomes approved.

    German ``Oliver`` / Hungarian ``Sándor`` keep their ids; the human fixes
    ``translation_uk`` and ``gender``, not the pipeline.
    """
    _assert_review(document)
    return TermbaseSnapshot(
        terms=tuple(_term(book_id, item) for item in document.terms),
        characters=tuple(_character(book_id, item) for item in document.characters),
        address_pairs=tuple(_pair(book_id, item) for item in document.address_pairs),
    )


def require_approved_termbase(snapshot: TermbaseSnapshot) -> None:
    """Block Phase 5 while any Term is unapproved or any Character gender is unknown.

    German Oliver with ``approved=false`` is enough to refuse. Hungarian Sándor
    with ``gender=unknown`` refuses even when every term is approved. ``--yolo``
    skips this check in the generation asset, not here.
    """
    pending = tuple(item.lemma for item in snapshot.terms if not item.approved)
    unknown = tuple(
        item.canonical_name
        for item in snapshot.characters
        if item.gender is Gender.UNKNOWN
    )
    if pending or unknown:
        raise TermbaseNotApproved(_gate_message(pending, unknown))


def _gate_message(pending: tuple[str, ...], unknown: tuple[str, ...]) -> str:
    parts: list[str] = []
    if pending:
        parts.append("unapproved terms: " + ", ".join(pending))
    if unknown:
        parts.append("unknown gender: " + ", ".join(unknown))
    return "; ".join(parts)


def _review_term(item: Term) -> ReviewTerm:
    return ReviewTerm(
        id=item.id,
        kind=item.kind,
        lemma=item.lemma,
        translation_uk=item.translation_uk,
        note=item.note,
        surface_forms=item.surface_forms,
    )


def _review_character(item: Character) -> ReviewCharacter:
    return ReviewCharacter(
        id=item.id,
        canonical_name=item.canonical_name,
        translation_uk=item.translation_uk,
        gender=item.gender,
        aliases=item.aliases,
        role_note=item.role_note,
    )


def _review_pair(item: AddressPair) -> ReviewAddressPair:
    return ReviewAddressPair(
        speaker_id=item.speaker_id,
        addressee_id=item.addressee_id,
        tv_form=item.tv_form,
    )


def _term(book_id: str, item: ReviewTerm) -> Term:
    return Term(
        id=item.id,
        book_id=book_id,
        kind=item.kind,
        surface_forms=item.surface_forms,
        lemma=item.lemma,
        translation_uk=item.translation_uk,
        note=item.note,
        approved=True,
    )


def _character(book_id: str, item: ReviewCharacter) -> Character:
    return Character(
        id=item.id,
        book_id=book_id,
        canonical_name=item.canonical_name,
        translation_uk=item.translation_uk,
        gender=item.gender,
        aliases=item.aliases,
        role_note=item.role_note,
    )


def _pair(book_id: str, item: ReviewAddressPair) -> AddressPair:
    return AddressPair(
        book_id=book_id,
        speaker_id=item.speaker_id,
        addressee_id=item.addressee_id,
        tv_form=item.tv_form,
    )


def _sorted_terms(items: tuple[Term, ...]) -> tuple[Term, ...]:
    return tuple(sorted(items, key=lambda item: (item.kind.value, item.lemma)))


def _sorted_characters(items: tuple[Character, ...]) -> tuple[Character, ...]:
    return tuple(sorted(items, key=lambda item: item.canonical_name))


def _sorted_pairs(items: tuple[AddressPair, ...]) -> tuple[AddressPair, ...]:
    return tuple(sorted(items, key=lambda item: (item.speaker_id, item.addressee_id)))


def _assert_review(document: ReviewDocument) -> None:
    _unique(tuple(item.id for item in document.terms), "term id")
    _unique(tuple(item.id for item in document.characters), "character id")
    _unique(_pair_keys(document.address_pairs), "address pair")
    known = {item.id for item in document.characters}
    for item in document.address_pairs:
        if item.speaker_id in known and item.addressee_id in known:
            continue
        raise SchemaInvalid(
            f"address pair {item.speaker_id}->{item.addressee_id} "
            "needs both characters in the file"
        )


def _pair_keys(pairs: tuple[ReviewAddressPair, ...]) -> tuple[str, ...]:
    return tuple(f"{item.speaker_id}->{item.addressee_id}" for item in pairs)


def _unique(ids: tuple[str, ...], label: str) -> None:
    seen: set[str] = set()
    for item in ids:
        if item in seen:
            raise SchemaInvalid(f"duplicate {label}: {item}")
        seen.add(item)
