"""Build the AddressPair matrix from dialogue (roadmap 3.4)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from frank.domain.model.termbase import (
    AddressCues,
    AddressMatrixConfig,
    AddressPair,
    TvForm,
)
from frank.domain.ports.linguistics import AddressResolver
from frank.domain.ports.repositories import BookRepository, TermbaseRepository
from frank.domain.services.address_detect import (
    AddressDetectRequest,
    collect_address_observations,
)
from frank.domain.services.address_merge import (
    fill_unresolved_mixed,
    merge_address_observations,
)


@dataclass(frozen=True)
class AddressPorts:
    open_books: Callable[[str], BookRepository]
    open_terms: Callable[[str], TermbaseRepository]
    cues_for: Callable[[str], AddressCues]
    resolver: AddressResolver


class AddressReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    pair_count: int
    t_count: int
    v_count: int
    mixed_count: int
    smart_count: int


def build_address_matrix(
    ports: AddressPorts, slug: str, config: AddressMatrixConfig
) -> AddressReport:
    books = ports.open_books(slug)
    terms = ports.open_terms(slug)
    structure = books.get_structure(slug)
    characters = terms.get_characters(slug)
    observations = collect_address_observations(
        AddressDetectRequest(
            structure=structure,
            sentences=books.get_sentences(slug),
            tokens=books.get_tokens(slug),
            characters=characters,
            cues=ports.cues_for(structure.book.lang),
        )
    )
    resolved, unresolved = merge_address_observations(
        structure.book.id, observations, characters, config
    )
    smart = ports.resolver.resolve(unresolved, structure.book.lang)
    pairs = fill_unresolved_mixed(structure.book.id, unresolved, resolved + smart)
    terms.replace_address_pairs(slug, pairs)
    return _report(slug, pairs, len(smart))


def render_address_report(report: AddressReport) -> str:
    return (
        f"address_pairs: {report.pair_count}\n"
        f"t: {report.t_count}\n"
        f"v: {report.v_count}\n"
        f"mixed: {report.mixed_count}\n"
        f"smart: {report.smart_count}\n"
    )


def _report(
    slug: str, pairs: tuple[AddressPair, ...], smart_count: int
) -> AddressReport:
    forms = [item.tv_form for item in pairs]
    return AddressReport(
        slug=slug,
        pair_count=len(pairs),
        t_count=forms.count(TvForm.T),
        v_count=forms.count(TvForm.V),
        mixed_count=forms.count(TvForm.MIXED),
        smart_count=smart_count,
    )
