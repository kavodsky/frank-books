"""Sentence split through gloss planning (roadmap 2.1–2.4)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from frank.domain.model.annotation import (
    Annotation,
    GlossLists,
    GlossPlanConfig,
    GlossPlanRequest,
    SegmentationConfig,
    SentencePlacement,
    Token,
)
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
from frank.domain.services.gloss_planning import plan_glosses
from frank.domain.services.lemmas import apply_overrides, lemma_types, partition_lemmas
from frank.domain.services.reunification import (
    apply_reunions,
    partition_reunions,
    reunion_candidates,
)
from frank.domain.services.segmentation import segment_annotation


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
    gloss_lists_for: Callable[[str], GlossLists]


class AnnotateReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    paragraph_count: int
    sentence_count: int
    token_count: int
    override_count: int
    particle_count: int
    sense_unit_count: int
    gloss_count: int


def annotate_book(
    ports: AnnotatePorts,
    slug: str,
    segmentation: SegmentationConfig,
    gloss: GlossPlanConfig,
) -> AnnotateReport:
    repo = ports.open_books(slug)
    structure = repo.get_structure(slug)
    lang = structure.book.lang
    analyzer = ports.analyzer_for(lang)
    support = ports.lemma_support_for(lang)
    arbiter = ports.arbiter_for(lang)
    annotation = _annotate_structure(structure, analyzer)
    refined, overrides = _refine(annotation, analyzer, support.lexicon, arbiter)
    reunited = _reunite(refined, support.inventory, support.lexicon, arbiter)
    units = segment_annotation(reunited, segmentation)
    segmented = reunited.model_copy(update={"sense_units": units})
    done = _with_gloss_plan(ports, structure, segmented, gloss)
    repo.replace_annotation(slug, done)
    repo.replace_overrides(slug, overrides)
    return _report(slug, structure, done, overrides)


def render_annotate_report(report: AnnotateReport) -> str:
    return (
        f"slug: {report.slug}\n"
        f"paragraphs: {report.paragraph_count}\n"
        f"sentences: {report.sentence_count}\n"
        f"tokens: {report.token_count}\n"
        f"lemma_overrides: {report.override_count}\n"
        f"verb_particles: {report.particle_count}\n"
        f"sense_units: {report.sense_unit_count}\n"
        f"gloss_plan: {report.gloss_count}\n"
    )


def _with_gloss_plan(
    ports: AnnotatePorts,
    structure: BookStructure,
    annotation: Annotation,
    gloss: GlossPlanConfig,
) -> Annotation:
    plan = plan_glosses(
        GlossPlanRequest(
            annotation=annotation,
            placements=_placements(structure, annotation),
            chapter_count=len(structure.chapters),
            lang=structure.book.lang,
            lists=ports.gloss_lists_for(structure.book.lang),
            config=gloss,
        )
    )
    return annotation.model_copy(update={"gloss_plan": plan})


def _placements(
    structure: BookStructure, annotation: Annotation
) -> tuple[SentencePlacement, ...]:
    chapter_by_id = {chapter.id: chapter for chapter in structure.chapters}
    paragraph_by_id = {item.id: item for item in structure.paragraphs}
    found: list[SentencePlacement] = []
    for ordinal, sentence in enumerate(annotation.sentences, start=1):
        paragraph = paragraph_by_id[sentence.paragraph_id]
        chapter = chapter_by_id[paragraph.chapter_id]
        found.append(
            SentencePlacement(
                sentence_id=sentence.id,
                ordinal=ordinal,
                chapter_index=chapter.index,
            )
        )
    return tuple(found)


def _report(
    slug: str,
    structure: BookStructure,
    done: Annotation,
    overrides: tuple[LemmaOverride, ...],
) -> AnnotateReport:
    return AnnotateReport(
        slug=slug,
        paragraph_count=len(structure.paragraphs),
        sentence_count=len(done.sentences),
        token_count=len(done.tokens),
        override_count=len(overrides),
        particle_count=len(done.particles),
        sense_unit_count=len(done.sense_units),
        gloss_count=len(done.gloss_plan),
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
