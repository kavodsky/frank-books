"""Sentence split, tokens, lemma refinement, and reunification (roadmap 2.1–2.2c)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from frank.domain.model.annotation import Annotation, Token
from frank.domain.model.book import BookStructure, Paragraph, Sentence
from frank.domain.model.lemma import LemmaOverride, LemmaPair, LemmaType
from frank.domain.model.reunion import PrefixInventory
from frank.domain.ports.linguistics import (
    LemmaArbiter,
    LemmaLexicon,
    LinguisticAnalyzer,
)
from frank.domain.ports.repositories import BookRepository
from frank.domain.services.annotation import annotate_paragraph
from frank.domain.services.lemmas import apply_overrides, lemma_types, partition_lemmas
from frank.domain.services.reunification import (
    apply_reunions,
    partition_reunions,
    reunion_candidates,
)


@dataclass(frozen=True)
class LemmaSupport:
    lexicon: LemmaLexicon
    inventory: PrefixInventory


@dataclass(frozen=True)
class AnnotatePorts:
    open_books: Callable[[str], BookRepository]
    analyzer_for: Callable[[str], LinguisticAnalyzer]
    lemma_support_for: Callable[[str], LemmaSupport]
    arbiter_for: Callable[[str], LemmaArbiter]


class AnnotateReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    paragraph_count: int
    sentence_count: int
    token_count: int
    override_count: int
    particle_count: int


def annotate_book(ports: AnnotatePorts, slug: str) -> AnnotateReport:
    repo = ports.open_books(slug)
    structure = repo.get_structure(slug)
    lang = structure.book.lang
    analyzer = ports.analyzer_for(lang)
    support = ports.lemma_support_for(lang)
    arbiter = ports.arbiter_for(lang)
    annotation = _annotate_structure(structure, analyzer)
    refined, overrides = _refine(annotation, analyzer, support.lexicon, arbiter)
    reunited = _reunite(refined, support.inventory, support.lexicon, arbiter)
    repo.replace_annotation(slug, reunited)
    repo.replace_overrides(slug, overrides)
    return AnnotateReport(
        slug=slug,
        paragraph_count=len(structure.paragraphs),
        sentence_count=len(reunited.sentences),
        token_count=len(reunited.tokens),
        override_count=len(overrides),
        particle_count=len(reunited.particles),
    )


def render_annotate_report(report: AnnotateReport) -> str:
    return (
        f"slug: {report.slug}\n"
        f"paragraphs: {report.paragraph_count}\n"
        f"sentences: {report.sentence_count}\n"
        f"tokens: {report.token_count}\n"
        f"lemma_overrides: {report.override_count}\n"
        f"verb_particles: {report.particle_count}\n"
    )


def _annotate_structure(
    structure: BookStructure, analyzer: LinguisticAnalyzer
) -> Annotation:
    sentences: list[Sentence] = []
    tokens: list[Token] = []
    for paragraph in structure.paragraphs:
        piece = _annotate_one(paragraph, analyzer)
        sentences.extend(piece.sentences)
        tokens.extend(piece.tokens)
    return Annotation(sentences=tuple(sentences), tokens=tuple(tokens))


def _annotate_one(paragraph: Paragraph, analyzer: LinguisticAnalyzer) -> Annotation:
    return annotate_paragraph(paragraph, analyzer.analyze(paragraph.raw_text))


def _refine(
    annotation: Annotation,
    analyzer: LinguisticAnalyzer,
    lexicon: LemmaLexicon,
    arbiter: LemmaArbiter,
) -> tuple[Annotation, tuple[LemmaOverride, ...]]:
    types = lemma_types(annotation)
    pairs = tuple(_pair(item, analyzer) for item in types)
    disputed = partition_lemmas(pairs, lexicon).disputed
    if not disputed:
        return annotation, ()
    overrides = arbiter.decide(disputed)
    tokens = apply_overrides(annotation.tokens, overrides)
    return Annotation(sentences=annotation.sentences, tokens=tokens), overrides


def _reunite(
    annotation: Annotation,
    inventory: PrefixInventory,
    lexicon: LemmaLexicon,
    arbiter: LemmaArbiter,
) -> Annotation:
    candidates = reunion_candidates(annotation, inventory, lexicon)
    accepted, pending = partition_reunions(candidates)
    voted = arbiter.decide_reunions(pending) if pending else ()
    particles = accepted + voted
    tokens = apply_reunions(annotation.tokens, particles)
    return Annotation(
        sentences=annotation.sentences, tokens=tokens, particles=particles
    )


def _pair(item: LemmaType, analyzer: LinguisticAnalyzer) -> LemmaPair:
    return LemmaPair(
        surface=item.surface,
        upos=item.upos,
        example_sentence=item.example_sentence,
        analyzer_lemma=item.analyzer_lemma,
        second_lemma=analyzer.second_lemma(item.surface, item.upos),
    )
