"""Export and approve the human termbase review (roadmap 3.6)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from frank.domain.errors import SchemaInvalid
from frank.domain.model.termbase import Gender, TermbaseSnapshot
from frank.domain.ports.repositories import BookRepository, TermbaseRepository
from frank.domain.services.termbase_review import (
    apply_review,
    document_from_termbase,
    parse_review_toml,
    render_review_toml,
    require_approved_termbase,
)


@dataclass(frozen=True)
class ReviewPorts:
    open_books: Callable[[str], BookRepository]
    open_terms: Callable[[str], TermbaseRepository]


class ApproveReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    term_count: int
    character_count: int
    address_pair_count: int
    unknown_gender_count: int


def export_review(ports: ReviewPorts, slug: str) -> str:
    return render_review_toml(document_from_termbase(_snapshot(ports, slug)))


def approve_review(ports: ReviewPorts, slug: str, text: str) -> ApproveReport:
    if not text.strip():
        raise SchemaInvalid("review TOML is empty")
    books = ports.open_books(slug)
    terms_repo = ports.open_terms(slug)
    book_id = books.get_structure(slug).book.id
    snapshot = apply_review(book_id, parse_review_toml(text))
    terms_repo.replace_characters(slug, snapshot.characters)
    terms_repo.replace_address_pairs(slug, snapshot.address_pairs)
    terms_repo.replace_terms(slug, snapshot.terms)
    return _report(slug, snapshot)


def check_generation_gate(ports: ReviewPorts, slug: str) -> None:
    require_approved_termbase(_snapshot(ports, slug))


def render_approve_report(report: ApproveReport) -> str:
    return (
        f"approved_terms: {report.term_count}\n"
        f"characters: {report.character_count}\n"
        f"address_pairs: {report.address_pair_count}\n"
        f"unknown_gender: {report.unknown_gender_count}\n"
    )


def _snapshot(ports: ReviewPorts, slug: str) -> TermbaseSnapshot:
    terms_repo = ports.open_terms(slug)
    return TermbaseSnapshot(
        terms=terms_repo.get_terms(slug),
        characters=terms_repo.get_characters(slug),
        address_pairs=terms_repo.get_address_pairs(slug),
    )


def _report(slug: str, snapshot: TermbaseSnapshot) -> ApproveReport:
    unknown = sum(1 for item in snapshot.characters if item.gender is Gender.UNKNOWN)
    return ApproveReport(
        slug=slug,
        term_count=len(snapshot.terms),
        character_count=len(snapshot.characters),
        address_pair_count=len(snapshot.address_pairs),
        unknown_gender_count=unknown,
    )
