"""Composition root: ports and configs for CLI and Dagster (roadmap 7.5)."""

from __future__ import annotations

import time
from pathlib import Path

from frank.application.analyze_book import AnalyzeConfig, AnalyzePorts
from frank.application.annotate_chapter import (
    AnnotateConfig,
    AnnotatePorts,
    LemmaSupport,
)
from frank.application.build_address import AddressPorts
from frank.application.build_characters import CharacterPorts
from frank.application.build_style import StylePorts
from frank.application.build_termbase import TermbasePorts, TranslatePorts
from frank.application.check_generation import CheckPorts
from frank.application.generate_paragraph import (
    GenerateConfig,
    GeneratePorts,
    SessionBudget,
    termbase_version,
)
from frank.application.generate_passages import StatusPorts
from frank.application.ingest_book import IngestPorts, IngestRequest
from frank.application.render_book import RenderPorts
from frank.application.report_book import ReportPorts
from frank.application.review_termbase import ReviewPorts
from frank.config import Settings
from frank.domain.model.annotation import GlossPlanConfig, SegmentationConfig
from frank.domain.model.book import PassageGroupingConfig
from frank.domain.model.context import ContextAssemblyConfig
from frank.domain.model.frank import ValidationConfig
from frank.domain.model.termbase import (
    AddressMatrixConfig,
    ChapterBriefConfig,
    CharacterEvidenceConfig,
    TermCollectConfig,
)
from frank.infrastructure.llm.chrf import sentence_chrf
from frank.infrastructure.llm.client import chat_client_from_settings
from frank.infrastructure.llm.generator import (
    GeneratorConfig,
    LlmFrankGenerator,
    prompt_version,
    task_instruction,
)
from frank.infrastructure.nlp.address_resolver import (
    ResolveConfig,
    SmartAddressResolver,
)
from frank.infrastructure.nlp.character_mapper import MapConfig, SmartCharacterMapper
from frank.infrastructure.nlp.lemma_arbiter import ArbiterConfig, SmartLemmaArbiter
from frank.infrastructure.nlp.lexicon import (
    FileLexicon,
    lexicon_path,
    load_address_cues,
    load_calques,
    load_exonyms,
    load_gender_cues,
    load_gloss_lists,
)
from frank.infrastructure.nlp.load import load_analyzer
from frank.infrastructure.nlp.prefixes import load_inventory
from frank.infrastructure.nlp.style_builder import SmartStyleBuilder, StyleConfig
from frank.infrastructure.nlp.term_translator import (
    SmartTermTranslator,
    TranslateConfig,
)
from frank.infrastructure.notify.macos import MacosNotifier
from frank.infrastructure.persistence.cache import StepCache
from frank.infrastructure.persistence.generation_cache import StepGenerationCache
from frank.infrastructure.persistence.repositories import (
    SqliteBookRepository,
    SqliteRunRepository,
)
from frank.infrastructure.persistence.tables import create_book_db
from frank.infrastructure.rendering.docx_renderer import write_docx
from frank.infrastructure.sources.fetch import LocalFileFetcher
from frank.infrastructure.sources.raw_store import FilesystemRawStore


def chapter_partition_key(slug: str, index: int) -> str:
    return f"{slug}:{index}"


def parse_chapter_partition(key: str) -> tuple[str, int]:
    slug, sep, raw = key.rpartition(":")
    if not sep or not raw.isdigit():
        raise ValueError(f"invalid chapter partition: {key}")
    return slug, int(raw)


def open_books(books_dir: Path, slug: str) -> SqliteBookRepository:
    return SqliteBookRepository(create_book_db(books_dir / slug / "book.db"))


def open_runs(books_dir: Path, slug: str) -> SqliteRunRepository:
    return SqliteRunRepository(create_book_db(books_dir / slug / "book.db"))


def ingest_ports(settings: Settings, books_dir: Path) -> IngestPorts:
    return IngestPorts(
        fetcher=LocalFileFetcher(settings.languages.source),
        raw_store=FilesystemRawStore(books_dir),
        open_books=lambda slug: open_books(books_dir, slug),
        books_dir=books_dir,
    )


def ingest_request(
    settings: Settings, location: str, slug: str | None, lang: str | None
) -> IngestRequest:
    ingest = settings.ingest
    return IngestRequest(
        location=location,
        slug=slug,
        lang=lang,
        header_max_chars=ingest.header_max_chars,
        header_min_repeats=ingest.header_min_repeats,
        max_paragraph_chars=ingest.max_paragraph_chars,
        foreign_script_ratio=ingest.foreign_script_ratio,
    )


def annotate_ports(settings: Settings, slug: str, books_dir: Path) -> AnnotatePorts:
    return AnnotatePorts(
        open_books=lambda name: open_books(books_dir, name),
        analyzer_for=lambda lang: load_analyzer(lang, settings.nlp),
        lemma_support_for=lambda lang: LemmaSupport(
            lexicon=FileLexicon(lexicon_path(lang)),
            inventory=load_inventory(lang),
        ),
        arbiter_for=lambda lang: _lemma_arbiter(settings, slug, lang, books_dir),
        gloss_lists_for=load_gloss_lists,
    )


def annotate_config(settings: Settings) -> AnnotateConfig:
    nlp = settings.nlp
    gloss = settings.gloss
    passage = settings.passage
    return AnnotateConfig(
        segmentation=SegmentationConfig(
            short_sentence_max_tokens=nlp.short_sentence_max_tokens,
            unit_min_tokens=nlp.sense_unit_min_tokens,
            unit_max_tokens=nlp.sense_unit_max_tokens,
            heavy_pp_min_tokens=nlp.heavy_pp_min_tokens,
        ),
        gloss=GlossPlanConfig(
            frequency_top_n=gloss.frequency_top_n,
            function_word_top_n=gloss.function_word_top_n,
            reminder_gap_sentences=gloss.reminder_gap_sentences,
            reminder_max_occurrences=gloss.reminder_max_occurrences,
            quota_chapter_start=gloss.quota_chapter_start,
            quota_last_third=gloss.quota_last_third,
            rare_morph_max_count=gloss.rare_morph_max_count,
        ),
        grouping=PassageGroupingConfig(
            min_chars=passage.min_chars,
            max_chars=passage.max_chars,
            dialogue_max_chars=passage.dialogue_max_chars,
        ),
    )


def analyze_ports(settings: Settings, slug: str, books_dir: Path) -> AnalyzePorts:
    return AnalyzePorts(
        termbase=_termbase_ports(books_dir),
        translate=_translate_ports(settings, slug, books_dir),
        characters=_character_ports(settings, slug, books_dir),
        address=_address_ports(settings, slug, books_dir),
        style=_style_ports(settings, slug, books_dir),
    )


def analyze_config(settings: Settings) -> AnalyzeConfig:
    termbase = settings.termbase
    return AnalyzeConfig(
        terms=TermCollectConfig(
            entity_min_occurrences=termbase.entity_min_occurrences,
            unknown_lemma_min_count=termbase.unknown_lemma_min_count,
            idiom_min_occurrences=termbase.idiom_min_occurrences,
            merge_max_edit_distance=termbase.merge_max_edit_distance,
            merge_min_stem_chars=termbase.merge_min_stem_chars,
        ),
        characters=CharacterEvidenceConfig(
            evidence_sentences_per_person=termbase.evidence_sentences_per_person
        ),
        address=AddressMatrixConfig(
            evidence_sentences_per_pair=termbase.evidence_sentences_per_pair
        ),
        briefs=ChapterBriefConfig(
            lead_sentences=termbase.summary_lead_sentences,
            tail_sentences=termbase.summary_tail_sentences,
            summary_sentence_min=termbase.summary_sentence_min,
            summary_sentence_max=termbase.summary_sentence_max,
        ),
    )


def review_ports(books_dir: Path) -> ReviewPorts:
    return ReviewPorts(
        open_books=lambda slug: open_books(books_dir, slug),
        open_terms=lambda slug: open_books(books_dir, slug),
    )


def generate_ports(settings: Settings, slug: str, books_dir: Path) -> GeneratePorts:
    client = chat_client_from_settings(settings, books_dir / slug / "logs")
    return GeneratePorts(
        open_books=lambda name: open_books(books_dir, name),
        open_terms=lambda name: open_books(books_dir, name),
        open_records=lambda name: open_books(books_dir, name),
        open_runs=lambda name: open_runs(books_dir, name),
        generator=LlmFrankGenerator(
            client=client,
            config=GeneratorConfig(
                fast_model=settings.fast.name,
                fast_url=settings.fast.base_url,
                smart_model=settings.smart.name,
                smart_url=settings.smart.base_url,
                timeout_seconds=settings.budgets.llm_timeout_seconds,
                scene_brief_sentences=settings.context.scene_brief_sentences,
            ),
        ),
        cache=StepGenerationCache(StepCache(books_dir / slug / "cache"), slug),
        notifier=MacosNotifier(),
        score_chrf=sentence_chrf,
        monotonic=time.monotonic,
    )


def generate_config(
    settings: Settings, slug: str, books_dir: Path, session: SessionBudget
) -> GenerateConfig:
    repo = open_books(books_dir, slug)
    structure = repo.get_structure(slug)
    terms = repo.get_terms(slug)
    gen = settings.generation
    ctx = settings.context
    return GenerateConfig(
        session=session,
        context=ContextAssemblyConfig(
            max_tokens=settings.budgets.prompt_tokens,
            rolling_window_sentences=ctx.rolling_window_sentences,
            scene_brief_sentences=ctx.scene_brief_sentences,
            style_card_digest_lines=ctx.style_card_digest_lines,
        ),
        validation=ValidationConfig(
            length_ratio_min=gen.length_ratio_min,
            length_ratio_max=gen.length_ratio_max,
            ukrainian_marker_min_chars=gen.ukrainian_marker_min_chars,
            calques=load_calques(),
        ),
        fast_retry_attempts=gen.fast_retry_attempts,
        backtranslation_sample_rate=gen.backtranslation_sample_rate,
        backtranslation_chrf_min=gen.backtranslation_chrf_min,
        hard_sentence_min_tokens=gen.hard_sentence_min_tokens,
        scene_brief_every_paragraphs=ctx.scene_brief_every_paragraphs,
        prompt_version=prompt_version(),
        models=f"{settings.fast.name}|{settings.smart.name}",
        termbase_version=termbase_version(terms),
        instruction=task_instruction(structure.book.lang),
    )


def session_budget(
    settings: Settings, minutes: int | None, passages: int | None
) -> SessionBudget:
    budgets = settings.budgets
    return SessionBudget(
        max_passages=budgets.session_max_passages if passages is None else passages,
        max_minutes=float(budgets.session_max_minutes if minutes is None else minutes),
    )


def status_ports(books_dir: Path) -> StatusPorts:
    return StatusPorts(
        open_books=lambda slug: open_books(books_dir, slug),
        open_runs=lambda slug: open_runs(books_dir, slug),
    )


def report_ports(books_dir: Path) -> ReportPorts:
    return ReportPorts(
        open_books=lambda slug: open_books(books_dir, slug),
        open_runs=lambda slug: open_runs(books_dir, slug),
        open_records=lambda slug: open_books(books_dir, slug),
    )


def check_ports(books_dir: Path) -> CheckPorts:
    return CheckPorts(
        open_books=lambda slug: open_books(books_dir, slug),
        open_terms=lambda slug: open_books(books_dir, slug),
        open_records=lambda slug: open_books(books_dir, slug),
    )


def render_ports(books_dir: Path) -> RenderPorts:
    return RenderPorts(
        open_books=lambda slug: open_books(books_dir, slug),
        open_records=lambda slug: open_books(books_dir, slug),
        write_docx=write_docx,
    )


def render_path(books_dir: Path, slug: str) -> Path:
    return books_dir / slug / "out" / f"{slug}.docx"


def _lemma_arbiter(
    settings: Settings, slug: str, lang: str, books_dir: Path
) -> SmartLemmaArbiter:
    return SmartLemmaArbiter(
        client=chat_client_from_settings(settings, books_dir / slug / "logs"),
        config=ArbiterConfig(
            model=settings.smart.name,
            base_url=settings.smart.base_url,
            timeout_seconds=settings.budgets.llm_timeout_seconds,
            batch_size=settings.nlp.lemma_batch_size,
            slug=slug,
        ),
        cache=StepCache(books_dir / slug / "cache"),
        lexicon=FileLexicon(lexicon_path(lang)),
    )


def _termbase_ports(books_dir: Path) -> TermbasePorts:
    return TermbasePorts(
        open_books=lambda slug: open_books(books_dir, slug),
        open_terms=lambda slug: open_books(books_dir, slug),
        lexicon_for=lambda lang: FileLexicon(lexicon_path(lang)),
        lists_for=load_gloss_lists,
    )


def _translate_ports(settings: Settings, slug: str, books_dir: Path) -> TranslatePorts:
    return TranslatePorts(
        open_books=lambda name: open_books(books_dir, name),
        open_terms=lambda name: open_books(books_dir, name),
        exonyms=load_exonyms,
        translator=SmartTermTranslator(
            client=chat_client_from_settings(settings, books_dir / slug / "logs"),
            config=TranslateConfig(
                model=settings.smart.name,
                base_url=settings.smart.base_url,
                timeout_seconds=settings.budgets.llm_timeout_seconds,
                batch_size=settings.termbase.translation_batch_size,
                slug=slug,
            ),
            cache=StepCache(books_dir / slug / "cache"),
        ),
    )


def _character_ports(settings: Settings, slug: str, books_dir: Path) -> CharacterPorts:
    return CharacterPorts(
        open_books=lambda name: open_books(books_dir, name),
        open_terms=lambda name: open_books(books_dir, name),
        gender_cues=load_gender_cues,
        mapper=SmartCharacterMapper(
            client=chat_client_from_settings(settings, books_dir / slug / "logs"),
            config=MapConfig(
                model=settings.smart.name,
                base_url=settings.smart.base_url,
                timeout_seconds=settings.budgets.llm_timeout_seconds,
                batch_size=settings.termbase.character_map_batch_size,
                slug=slug,
            ),
            cache=StepCache(books_dir / slug / "cache"),
        ),
    )


def _address_ports(settings: Settings, slug: str, books_dir: Path) -> AddressPorts:
    return AddressPorts(
        open_books=lambda name: open_books(books_dir, name),
        open_terms=lambda name: open_books(books_dir, name),
        cues_for=load_address_cues,
        resolver=SmartAddressResolver(
            client=chat_client_from_settings(settings, books_dir / slug / "logs"),
            config=ResolveConfig(
                model=settings.smart.name,
                base_url=settings.smart.base_url,
                timeout_seconds=settings.budgets.llm_timeout_seconds,
                batch_size=settings.termbase.address_map_batch_size,
                slug=slug,
            ),
            cache=StepCache(books_dir / slug / "cache"),
        ),
    )


def _style_ports(settings: Settings, slug: str, books_dir: Path) -> StylePorts:
    builder = SmartStyleBuilder(
        client=chat_client_from_settings(settings, books_dir / slug / "logs"),
        config=StyleConfig(
            model=settings.smart.name,
            base_url=settings.smart.base_url,
            timeout_seconds=settings.budgets.llm_timeout_seconds,
            slug=slug,
            summary_sentence_min=settings.termbase.summary_sentence_min,
            summary_sentence_max=settings.termbase.summary_sentence_max,
        ),
        cache=StepCache(books_dir / slug / "cache"),
    )
    return StylePorts(
        open_books=lambda name: open_books(books_dir, name),
        open_terms=lambda name: open_books(books_dir, name),
        summarizer=builder,
        composer=builder,
        write_markdown=lambda name, text: _write_style(books_dir, name, text),
    )


def _write_style(books_dir: Path, slug: str, markdown: str) -> None:
    (books_dir / slug / "style_card.md").write_text(markdown, encoding="utf-8")
