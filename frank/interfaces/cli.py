"""The `frank` command. Subcommands are added by the roadmap phase that needs them."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from frank.application.ingest_book import (
    IngestPorts,
    IngestRequest,
    ingest_book,
    inspect_slug,
    render_inspect_report,
)
from frank.config import Settings, load_settings
from frank.infrastructure.llm.benchmark import (
    BenchPlan,
    load_gold_files,
    parse_model_spec,
    run_benchmark,
)
from frank.infrastructure.llm.client import OpenAiChatClient, chat_client_from_settings
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


def _ports(settings: Settings) -> IngestPorts:
    return IngestPorts(
        fetcher=LocalFileFetcher(settings.languages.source),
        raw_store=FilesystemRawStore(_BOOKS_DIR),
        open_books=_open_books,
        books_dir=_BOOKS_DIR,
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
