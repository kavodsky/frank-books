"""Sentence split, tokens, and lemma refinement (roadmap 2.1–2.2b)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from frank.domain.model.annotation import Annotation, Token
from frank.domain.model.book import BookStructure, Paragraph, Sentence
from frank.domain.model.lemma import LemmaOverride, LemmaPair, LemmaType
from frank.domain.ports.linguistics import (
    LemmaArbiter,
    LemmaLexicon,
    LinguisticAnalyzer,
)
from frank.domain.ports.repositories import BookRepository
from frank.domain.services.annotation import annotate_paragraph
from frank.domain.services.lemmas import apply_overrides, lemma_types, partition_lemmas


@dataclass(frozen=True)
class AnnotatePorts:
    open_books: Callable[[str], BookRepository]
    analyzer_for: Callable[[str], LinguisticAnalyzer]
    lexicon_for: Callable[[str], LemmaLexicon]
    arbiter_for: Callable[[str], LemmaArbiter]


class AnnotateReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    paragraph_count: int
    sentence_count: int
    token_count: int
    override_count: int


def annotate_book(ports: AnnotatePorts, slug: str) -> AnnotateReport:
    repo = ports.open_books(slug)
    structure = repo.get_structure(slug)
    lang = structure.book.lang
    analyzer = ports.analyzer_for(lang)
    annotation = _annotate_structure(structure, analyzer)
    refined, overrides = _refine(
        annotation, analyzer, ports.lexicon_for(lang), ports.arbiter_for(lang)
    )
    repo.replace_annotation(slug, refined)
    repo.replace_overrides(slug, overrides)
    return AnnotateReport(
        slug=slug,
        paragraph_count=len(structure.paragraphs),
        sentence_count=len(refined.sentences),
        token_count=len(refined.tokens),
        override_count=len(overrides),
    )


def render_annotate_report(report: AnnotateReport) -> str:
    return (
        f"slug: {report.slug}\n"
        f"paragraphs: {report.paragraph_count}\n"
        f"sentences: {report.sentence_count}\n"
        f"tokens: {report.token_count}\n"
        f"lemma_overrides: {report.override_count}\n"
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


def _pair(item: LemmaType, analyzer: LinguisticAnalyzer) -> LemmaPair:
    return LemmaPair(
        surface=item.surface,
        upos=item.upos,
        example_sentence=item.example_sentence,
        analyzer_lemma=item.analyzer_lemma,
        second_lemma=analyzer.second_lemma(item.surface, item.upos),
    )
