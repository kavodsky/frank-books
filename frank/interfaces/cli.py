"""The `frank` command. Subcommands are added by the roadmap phase that needs them."""

from __future__ import annotations

import asyncio
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
from frank.application.build_termbase import (
    TermbasePorts,
    TranslatePorts,
    build_termbase,
    render_termbase_report,
    render_translate_report,
    translate_termbase,
)
from frank.application.ingest_book import (
    IngestPorts,
    IngestRequest,
    ingest_book,
    inspect_slug,
    render_inspect_report,
)
from frank.config import Settings, load_settings
from frank.domain.model.annotation import GlossPlanConfig, SegmentationConfig
from frank.domain.model.book import PassageGroupingConfig
from frank.domain.model.termbase import TermCollectConfig
from frank.infrastructure.llm.benchmark import (
    BenchPlan,
    load_gold_files,
    parse_model_spec,
    run_benchmark,
)
from frank.infrastructure.llm.client import OpenAiChatClient, chat_client_from_settings
from frank.infrastructure.nlp.lemma_arbiter import ArbiterConfig, SmartLemmaArbiter
from frank.infrastructure.nlp.lexicon import (
    FileLexicon,
    lexicon_path,
    load_exonyms,
    load_gloss_lists,
)
from frank.infrastructure.nlp.load import load_analyzer
from frank.infrastructure.nlp.prefixes import load_inventory
from frank.infrastructure.nlp.term_translator import (
    SmartTermTranslator,
    TranslateConfig,
)
from frank.infrastructure.persistence.cache import StepCache
from frank.infrastructure.persistence.repositories import SqliteBookRepository
from frank.infrastructure.persistence.tables import create_book_db
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
    """Collect Term candidates and fill Ukrainian renderings (exonyms + SMART)."""
    settings = load_settings(config)
    collected = build_termbase(_termbase_ports(settings), slug, _term_config(settings))
    translated = translate_termbase(_translate_ports(settings, slug), slug)
    typer.echo(render_termbase_report(collected) + render_translate_report(translated))


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
