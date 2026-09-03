"""The `frank` command. Subcommands are added by the roadmap phase that needs them."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer

from frank.application.analyze_book import analyze_book, render_analyze_report
from frank.application.annotate_chapter import annotate_book, render_annotate_report
from frank.application.generate_passages import book_generation_status, render_status
from frank.application.ingest_book import (
    ingest_book,
    inspect_slug,
    render_inspect_report,
)
from frank.application.render_book import format_render_report, render_book
from frank.application.report_book import book_report, render_book_report
from frank.application.review_termbase import (
    approve_review,
    export_review,
    render_approve_report,
)
from frank.config import load_settings
from frank.infrastructure.llm.benchmark import (
    BenchPlan,
    load_gold_files,
    parse_model_spec,
    run_benchmark,
)
from frank.infrastructure.llm.client import OpenAiChatClient, chat_client_from_settings
from frank.interfaces import wiring

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
    typer.echo(asyncio.run(_run_bench(client, plan)))


async def _run_bench(client: OpenAiChatClient, plan: BenchPlan) -> str:
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
        wiring.ingest_ports(settings, _BOOKS_DIR),
        wiring.ingest_request(settings, str(source), slug, lang),
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
        wiring.ingest_ports(settings, _BOOKS_DIR),
        slug,
        wiring.ingest_request(settings, slug, slug, None),
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
        wiring.annotate_ports(settings, slug, _BOOKS_DIR),
        slug,
        wiring.annotate_config(settings),
    )
    typer.echo(render_annotate_report(report))


@app.command()
def terms(
    slug: Annotated[str, typer.Argument(help="Book slug under books/")],
    config: Annotated[Path, typer.Option("--config")] = Path("config.toml"),
) -> None:
    """Collect terms, characters, T/V matrix, summaries, and the style card."""
    settings = load_settings(config)
    report = analyze_book(
        wiring.analyze_ports(settings, slug, _BOOKS_DIR),
        slug,
        wiring.analyze_config(settings),
    )
    typer.echo(render_analyze_report(report))


@app.command("review-terms")
def review_terms_cmd(
    slug: Annotated[str, typer.Argument(help="Book slug under books/")],
) -> None:
    """Export termbase, characters, and the T/V matrix as editable TOML."""
    typer.echo(export_review(wiring.review_ports(_BOOKS_DIR), slug), nl=False)


@app.command()
def approve(
    slug: Annotated[str, typer.Argument(help="Book slug under books/")],
) -> None:
    """Import a reviewed TOML and set term.approved=true."""
    report = approve_review(wiring.review_ports(_BOOKS_DIR), slug, sys.stdin.read())
    typer.echo(render_approve_report(report))


@app.command()
def status(
    slug: Annotated[str, typer.Argument(help="Book slug under books/")],
) -> None:
    """Passages done / total, pace, and session ETA."""
    typer.echo(
        render_status(book_generation_status(wiring.status_ports(_BOOKS_DIR), slug)),
        nl=False,
    )


@app.command()
def report(
    slug: Annotated[str, typer.Argument(help="Book slug under books/")],
) -> None:
    """Cumulative book-level session picture."""
    typer.echo(
        render_book_report(book_report(wiring.report_ports(_BOOKS_DIR), slug)),
        nl=False,
    )


@app.command()
def render(
    slug: Annotated[str, typer.Argument(help="Book slug under books/")],
    docx: Annotated[
        Path | None,
        typer.Option("--docx", help="Write this path instead of books/<slug>/out/"),
    ] = None,
) -> None:
    """Write a Frank .docx for every completed passage so far."""
    out = wiring.render_path(_BOOKS_DIR, slug) if docx is None else docx
    result = render_book(wiring.render_ports(_BOOKS_DIR), slug, out)
    typer.echo(format_render_report(result), nl=False)
