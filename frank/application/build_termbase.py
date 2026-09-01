"""Collect and translate Term candidates (roadmap 3.1–3.2)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from frank.domain.model.annotation import GlossLists
from frank.domain.model.termbase import Exonym, Term, TermCollectConfig, TermKind
from frank.domain.ports.linguistics import LemmaLexicon, TermTranslator
from frank.domain.ports.repositories import BookRepository, TermbaseRepository
from frank.domain.services.term_candidates import TermCollectRequest, collect_terms
from frank.domain.services.term_renderings import (
    apply_exonyms,
    apply_renderings,
    untranslated,
)


@dataclass(frozen=True)
class TermbasePorts:
    open_books: Callable[[str], BookRepository]
    open_terms: Callable[[str], TermbaseRepository]
    lexicon_for: Callable[[str], LemmaLexicon]
    lists_for: Callable[[str], GlossLists]


class TermbaseReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    term_count: int
    person_count: int
    place_count: int
    org_count: int
    disambig_count: int
    idiom_count: int


def build_termbase(
    ports: TermbasePorts, slug: str, config: TermCollectConfig
) -> TermbaseReport:
    books = ports.open_books(slug)
    terms_repo = ports.open_terms(slug)
    structure = books.get_structure(slug)
    lang = structure.book.lang
    terms = collect_terms(
        TermCollectRequest(
            book_id=structure.book.id,
            tokens=books.get_tokens(slug),
            lexicon=ports.lexicon_for(lang),
            idioms=ports.lists_for(lang).idioms,
            config=config,
        )
    )
    terms_repo.replace_terms(slug, terms)
    return _report(slug, terms)


def render_termbase_report(report: TermbaseReport) -> str:
    return (
        f"slug: {report.slug}\n"
        f"terms: {report.term_count}\n"
        f"person: {report.person_count}\n"
        f"place: {report.place_count}\n"
        f"org: {report.org_count}\n"
        f"disambig: {report.disambig_count}\n"
        f"idiom: {report.idiom_count}\n"
    )


def _report(slug: str, terms: tuple[Term, ...]) -> TermbaseReport:
    kinds = [item.kind for item in terms]
    return TermbaseReport(
        slug=slug,
        term_count=len(terms),
        person_count=kinds.count(TermKind.PERSON),
        place_count=kinds.count(TermKind.PLACE),
        org_count=kinds.count(TermKind.ORG),
        disambig_count=kinds.count(TermKind.DISAMBIG),
        idiom_count=kinds.count(TermKind.IDIOM),
    )


@dataclass(frozen=True)
class TranslatePorts:
    open_books: Callable[[str], BookRepository]
    open_terms: Callable[[str], TermbaseRepository]
    exonyms: Callable[[], tuple[Exonym, ...]]
    translator: TermTranslator


class TranslateReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    translated_count: int
    exonym_count: int
    llm_count: int
    untranslated_count: int


def translate_termbase(ports: TranslatePorts, slug: str) -> TranslateReport:
    books = ports.open_books(slug)
    terms_repo = ports.open_terms(slug)
    lang = books.get_structure(slug).book.lang
    source = terms_repo.get_terms(slug)
    with_exonyms = apply_exonyms(source, ports.exonyms())
    pending = untranslated(with_exonyms)
    renderings = ports.translator.propose(pending, lang)
    done = apply_renderings(with_exonyms, renderings)
    terms_repo.replace_terms(slug, done)
    return TranslateReport(
        slug=slug,
        translated_count=_filled(done),
        exonym_count=_filled(with_exonyms) - _filled(source),
        llm_count=len(renderings),
        untranslated_count=len(done) - _filled(done),
    )


def render_translate_report(report: TranslateReport) -> str:
    return (
        f"translated: {report.translated_count}\n"
        f"exonyms: {report.exonym_count}\n"
        f"llm: {report.llm_count}\n"
        f"untranslated: {report.untranslated_count}\n"
    )


def _filled(terms: tuple[Term, ...]) -> int:
    return sum(1 for item in terms if item.translation_uk.strip())
