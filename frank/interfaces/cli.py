"""The `frank` command. Subcommands are added by the roadmap phase that needs them."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer

from frank.application.annotate_chapter import (
    AnnotateConfig,
    AnnotatePorts,
    LemmaSupport,
    annotate_book,
    render_annotate_report,
)
from frank.application.build_address import (
    AddressPorts,
    build_address_matrix,
    render_address_report,
)
from frank.application.build_characters import (
    CharacterPorts,
    build_character_registry,
    render_character_report,
)
from frank.application.build_style import (
    StylePorts,
    build_style_card,
    render_style_report,
)
from frank.application.build_termbase import (
    TermbasePorts,
    TranslatePorts,
    build_termbase,
    render_termbase_report,
    render_translate_report,
    translate_termbase,
)
from frank.application.generate_passages import (
    StatusPorts,
    book_generation_status,
    render_status,
)
from frank.application.ingest_book import (
    IngestPorts,
    IngestRequest,
    ingest_book,
    inspect_slug,
    render_inspect_report,
)
from frank.application.render_book import (
    RenderPorts,
    format_render_report,
    render_book,
)
from frank.application.review_termbase import (
    ReviewPorts,
    approve_review,
    export_review,
    render_approve_report,
)
from frank.config import Settings, load_settings
from frank.domain.model.annotation import GlossPlanConfig, SegmentationConfig
from frank.domain.model.book import PassageGroupingConfig
from frank.domain.model.termbase import (
    AddressMatrixConfig,
    ChapterBriefConfig,
    CharacterEvidenceConfig,
    TermCollectConfig,
)
from frank.infrastructure.llm.benchmark import (
    BenchPlan,
    load_gold_files,
    parse_model_spec,
    run_benchmark,
)
from frank.infrastructure.llm.client import OpenAiChatClient, chat_client_from_settings
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
from frank.infrastructure.persistence.cache import StepCache
from frank.infrastructure.persistence.repositories import (
    SqliteBookRepository,
    SqliteRunRepository,
)
from frank.infrastructure.persistence.tables import create_book_db
from frank.infrastructure.rendering.docx_renderer import write_docx
from frank.infrastructure.sources.fetch import LocalFileFetcher
from frank.infrastructure.sources.raw_store import FilesystemRawStore

app = typer.Typer(
    name="frank",
    help=(
        "Build Ilya Frank method reading books from German and Hungarian originals, "
        "glossed in Ukrainian."
    ),
    no_args_is_help=True,
)

_DEFAULT_GOLD = (
    Path("gold/de_sample.jsonl"),
    Path("gold/hu_sample.jsonl"),
)
_BOOKS_DIR = Path("books")


@app.callback()
def main() -> None:
    """Hands-on commands; generation itself is started from Dagster only."""


@app.command()
def bench(
    models: Annotated[
        list[str],
        typer.Option("--models", help="Candidate name, or name@base_url"),
    ],
    gold: Annotated[
        list[Path] | None,
        typer.Option("--gold", help="Gold JSONL; defaults to gold/de and gold/hu"),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Write the markdown report to this path"),
    ] = None,
    config: Annotated[
        Path,
        typer.Option("--config", help="TOML settings file"),
    ] = Path("config.toml"),
) -> None:
    """Run gold sentences through candidate models; report chrF, BLEU, and judge."""
    settings = load_settings(config)
    gold_paths = _DEFAULT_GOLD if gold is None else tuple(gold)
    candidates = tuple(
        parse_model_spec(spec, settings.fast.base_url) for spec in models
    )
    plan = BenchPlan(
        gold=load_gold_files(gold_paths),
        models=candidates,
        judge=parse_model_spec(settings.smart.name, settings.smart.base_url),
        timeout_seconds=settings.budgets.llm_timeout_seconds,
        out_path=out,
    )
    client = chat_client_from_settings(settings, Path("books/_bench/logs"))
    report = asyncio.run(_run(client, plan))
    typer.echo(report)


async def _run(client: OpenAiChatClient, plan: BenchPlan) -> str:
    try:
        return await run_benchmark(client, plan)
    finally:
        await client.aclose()


@app.command()
def ingest(
    source: Annotated[Path, typer.Argument(help="Local .txt, .html, or .epub")],
    slug: Annotated[str | None, typer.Option("--slug")] = None,
    lang: Annotated[str | None, typer.Option("--lang")] = None,
    config: Annotated[Path, typer.Option("--config")] = Path("config.toml"),
) -> None:
    """Normalize a local file, split into chapters, persist, then inspect."""
    settings = load_settings(config)
    report = ingest_book(
        _ports(settings),
        _ingest_request(settings, str(source), slug, lang),
    )
    typer.echo(render_inspect_report(report))
    if not report.clean:
        raise typer.Exit(code=1)


@app.command("inspect")
def inspect_cmd(
    slug: Annotated[str, typer.Argument(help="Book slug under books/")],
    config: Annotated[Path, typer.Option("--config")] = Path("config.toml"),
) -> None:
    """Sanity report: chapters, paragraph counts, suspicious paragraphs."""
    settings = load_settings(config)
    report = inspect_slug(
        _ports(settings), slug, _ingest_request(settings, slug, slug, None)
    )
    typer.echo(render_inspect_report(report))
    if not report.clean:
        raise typer.Exit(code=1)


@app.command()
def annotate(
    slug: Annotated[str, typer.Argument(help="Book slug under books/")],
    config: Annotated[Path, typer.Option("--config")] = Path("config.toml"),
) -> None:
    """Annotate sentences, tokens, lemmas, sense units, glosses, and passages."""
    settings = load_settings(config)
    report = annotate_book(
        _annotate_ports(settings, slug), slug, _annotate_config(settings)
    )
    typer.echo(render_annotate_report(report))


@app.command()
def terms(
    slug: Annotated[str, typer.Argument(help="Book slug under books/")],
    config: Annotated[Path, typer.Option("--config")] = Path("config.toml"),
) -> None:
    """Collect terms, characters, T/V matrix, summaries, and the style card."""
    settings = load_settings(config)
    collected = build_termbase(_termbase_ports(settings), slug, _term_config(settings))
    translated = translate_termbase(_translate_ports(settings, slug), slug)
    characters = build_character_registry(
        _character_ports(settings, slug), slug, _character_config(settings)
    )
    addresses = build_address_matrix(
        _address_ports(settings, slug), slug, _address_config(settings)
    )
    style = build_style_card(
        _style_ports(settings, slug), slug, _brief_config(settings)
    )
    typer.echo(
        render_termbase_report(collected)
        + render_translate_report(translated)
        + render_character_report(characters)
        + render_address_report(addresses)
        + render_style_report(style)
    )


@app.command("review-terms")
def review_terms_cmd(
    slug: Annotated[str, typer.Argument(help="Book slug under books/")],
) -> None:
    """Export termbase, characters, and the T/V matrix as editable TOML."""
    typer.echo(export_review(_review_ports(), slug), nl=False)


@app.command()
def approve(
    slug: Annotated[str, typer.Argument(help="Book slug under books/")],
) -> None:
    """Import a reviewed TOML and set term.approved=true."""
    report = approve_review(_review_ports(), slug, sys.stdin.read())
    typer.echo(render_approve_report(report))


@app.command()
def status(
    slug: Annotated[str, typer.Argument(help="Book slug under books/")],
) -> None:
    """Passages done / total and passages-per-hour."""
    typer.echo(render_status(book_generation_status(_status_ports(), slug)), nl=False)


@app.command()
def render(
    slug: Annotated[str, typer.Argument(help="Book slug under books/")],
    docx: Annotated[
        Path | None,
        typer.Option("--docx", help="Write this path instead of books/<slug>/out/"),
    ] = None,
) -> None:
    """Write a Frank .docx for every completed passage so far."""
    out = _BOOKS_DIR / slug / "out" / f"{slug}.docx" if docx is None else docx
    report = render_book(_render_ports(), slug, out)
    typer.echo(format_render_report(report), nl=False)


def _ports(settings: Settings) -> IngestPorts:
    return IngestPorts(
        fetcher=LocalFileFetcher(settings.languages.source),
        raw_store=FilesystemRawStore(_BOOKS_DIR),
        open_books=_open_books,
        books_dir=_BOOKS_DIR,
    )


def _annotate_ports(settings: Settings, slug: str) -> AnnotatePorts:
    return AnnotatePorts(
        open_books=_open_books,
        analyzer_for=lambda lang: load_analyzer(lang, settings.nlp),
        lemma_support_for=lambda lang: LemmaSupport(
            lexicon=FileLexicon(lexicon_path(lang)),
            inventory=load_inventory(lang),
        ),
        arbiter_for=lambda lang: _lemma_arbiter(settings, slug, lang),
        gloss_lists_for=load_gloss_lists,
    )


def _segmentation(settings: Settings) -> SegmentationConfig:
    nlp = settings.nlp
    return SegmentationConfig(
        short_sentence_max_tokens=nlp.short_sentence_max_tokens,
        unit_min_tokens=nlp.sense_unit_min_tokens,
        unit_max_tokens=nlp.sense_unit_max_tokens,
        heavy_pp_min_tokens=nlp.heavy_pp_min_tokens,
    )


def _gloss_config(settings: Settings) -> GlossPlanConfig:
    gloss = settings.gloss
    return GlossPlanConfig(
        frequency_top_n=gloss.frequency_top_n,
        function_word_top_n=gloss.function_word_top_n,
        reminder_gap_sentences=gloss.reminder_gap_sentences,
        reminder_max_occurrences=gloss.reminder_max_occurrences,
        quota_chapter_start=gloss.quota_chapter_start,
        quota_last_third=gloss.quota_last_third,
        rare_morph_max_count=gloss.rare_morph_max_count,
    )


def _annotate_config(settings: Settings) -> AnnotateConfig:
    return AnnotateConfig(
        segmentation=_segmentation(settings),
        gloss=_gloss_config(settings),
        grouping=_grouping(settings),
    )


def _grouping(settings: Settings) -> PassageGroupingConfig:
    passage = settings.passage
    return PassageGroupingConfig(
        min_chars=passage.min_chars,
        max_chars=passage.max_chars,
        dialogue_max_chars=passage.dialogue_max_chars,
    )


def _termbase_ports(_settings: Settings) -> TermbasePorts:
    return TermbasePorts(
        open_books=_open_books,
        open_terms=_open_books,
        lexicon_for=lambda lang: FileLexicon(lexicon_path(lang)),
        lists_for=load_gloss_lists,
    )


def _term_config(settings: Settings) -> TermCollectConfig:
    termbase = settings.termbase
    return TermCollectConfig(
        entity_min_occurrences=termbase.entity_min_occurrences,
        unknown_lemma_min_count=termbase.unknown_lemma_min_count,
        idiom_min_occurrences=termbase.idiom_min_occurrences,
        merge_max_edit_distance=termbase.merge_max_edit_distance,
        merge_min_stem_chars=termbase.merge_min_stem_chars,
    )


def _translate_ports(settings: Settings, slug: str) -> TranslatePorts:
    return TranslatePorts(
        open_books=_open_books,
        open_terms=_open_books,
        exonyms=load_exonyms,
        translator=_term_translator(settings, slug),
    )


def _term_translator(settings: Settings, slug: str) -> SmartTermTranslator:
    return SmartTermTranslator(
        client=chat_client_from_settings(settings, _BOOKS_DIR / slug / "logs"),
        config=TranslateConfig(
            model=settings.smart.name,
            base_url=settings.smart.base_url,
            timeout_seconds=settings.budgets.llm_timeout_seconds,
            batch_size=settings.termbase.translation_batch_size,
            slug=slug,
        ),
        cache=StepCache(_BOOKS_DIR / slug / "cache"),
    )


def _character_ports(settings: Settings, slug: str) -> CharacterPorts:
    return CharacterPorts(
        open_books=_open_books,
        open_terms=_open_books,
        gender_cues=load_gender_cues,
        mapper=_character_mapper(settings, slug),
    )


def _character_config(settings: Settings) -> CharacterEvidenceConfig:
    return CharacterEvidenceConfig(
        evidence_sentences_per_person=settings.termbase.evidence_sentences_per_person
    )


def _character_mapper(settings: Settings, slug: str) -> SmartCharacterMapper:
    return SmartCharacterMapper(
        client=chat_client_from_settings(settings, _BOOKS_DIR / slug / "logs"),
        config=MapConfig(
            model=settings.smart.name,
            base_url=settings.smart.base_url,
            timeout_seconds=settings.budgets.llm_timeout_seconds,
            batch_size=settings.termbase.character_map_batch_size,
            slug=slug,
        ),
        cache=StepCache(_BOOKS_DIR / slug / "cache"),
    )


def _address_ports(settings: Settings, slug: str) -> AddressPorts:
    return AddressPorts(
        open_books=_open_books,
        open_terms=_open_books,
        cues_for=load_address_cues,
        resolver=_address_resolver(settings, slug),
    )


def _address_config(settings: Settings) -> AddressMatrixConfig:
    return AddressMatrixConfig(
        evidence_sentences_per_pair=settings.termbase.evidence_sentences_per_pair
    )


def _address_resolver(settings: Settings, slug: str) -> SmartAddressResolver:
    return SmartAddressResolver(
        client=chat_client_from_settings(settings, _BOOKS_DIR / slug / "logs"),
        config=ResolveConfig(
            model=settings.smart.name,
            base_url=settings.smart.base_url,
            timeout_seconds=settings.budgets.llm_timeout_seconds,
            batch_size=settings.termbase.address_map_batch_size,
            slug=slug,
        ),
        cache=StepCache(_BOOKS_DIR / slug / "cache"),
    )


def _style_ports(settings: Settings, slug: str) -> StylePorts:
    builder = _style_builder(settings, slug)
    return StylePorts(
        open_books=_open_books,
        open_terms=_open_books,
        summarizer=builder,
        composer=builder,
        write_markdown=_write_style_markdown,
    )


def _brief_config(settings: Settings) -> ChapterBriefConfig:
    termbase = settings.termbase
    return ChapterBriefConfig(
        lead_sentences=termbase.summary_lead_sentences,
        tail_sentences=termbase.summary_tail_sentences,
        summary_sentence_min=termbase.summary_sentence_min,
        summary_sentence_max=termbase.summary_sentence_max,
    )


def _style_builder(settings: Settings, slug: str) -> SmartStyleBuilder:
    termbase = settings.termbase
    return SmartStyleBuilder(
        client=chat_client_from_settings(settings, _BOOKS_DIR / slug / "logs"),
        config=StyleConfig(
            model=settings.smart.name,
            base_url=settings.smart.base_url,
            timeout_seconds=settings.budgets.llm_timeout_seconds,
            slug=slug,
            summary_sentence_min=termbase.summary_sentence_min,
            summary_sentence_max=termbase.summary_sentence_max,
        ),
        cache=StepCache(_BOOKS_DIR / slug / "cache"),
    )


def _write_style_markdown(slug: str, markdown: str) -> None:
    (_BOOKS_DIR / slug / "style_card.md").write_text(markdown, encoding="utf-8")


def _review_ports() -> ReviewPorts:
    return ReviewPorts(open_books=_open_books, open_terms=_open_books)


def _lemma_arbiter(settings: Settings, slug: str, lang: str) -> SmartLemmaArbiter:
    return SmartLemmaArbiter(
        client=chat_client_from_settings(settings, _BOOKS_DIR / slug / "logs"),
        config=ArbiterConfig(
            model=settings.smart.name,
            base_url=settings.smart.base_url,
            timeout_seconds=settings.budgets.llm_timeout_seconds,
            batch_size=settings.nlp.lemma_batch_size,
            slug=slug,
        ),
        cache=StepCache(_BOOKS_DIR / slug / "cache"),
        lexicon=FileLexicon(lexicon_path(lang)),
    )


def _open_books(slug: str) -> SqliteBookRepository:
    return SqliteBookRepository(create_book_db(_BOOKS_DIR / slug / "book.db"))


def _open_runs(slug: str) -> SqliteRunRepository:
    return SqliteRunRepository(create_book_db(_BOOKS_DIR / slug / "book.db"))


def _status_ports() -> StatusPorts:
    return StatusPorts(open_books=_open_books, open_runs=_open_runs)


def _render_ports() -> RenderPorts:
    return RenderPorts(
        open_books=_open_books,
        open_records=_open_books,
        write_docx=write_docx,
    )


def _ingest_request(
    settings: Settings,
    location: str,
    slug: str | None,
    lang: str | None,
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
