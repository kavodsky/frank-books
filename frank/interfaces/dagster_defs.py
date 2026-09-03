"""Dagster assets, checks, and RetryPolicy (roadmap Phase 7)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import get_type_hints

from dagster import (
    AssetCheckExecutionContext,
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    BackfillPolicy,
    Backoff,
    Config,
    ConfigurableResource,
    Definitions,
    DynamicPartitionsDefinition,
    Failure,
    Output,
    RetryPolicy,
    asset,
    asset_check,
    define_asset_job,
    in_process_executor,
)

from frank.application.analyze_book import analyze_book
from frank.application.annotate_chapter import annotate_book
from frank.application.check_generation import (
    ChapterCheckRequest,
    StoredCheckReport,
    check_back_translation,
    check_lemmas,
    check_named_records,
)
from frank.application.generate_passages import (
    book_generation_status,
    generate_chapter,
)
from frank.application.ingest_book import ingest_book
from frank.application.render_book import render_book
from frank.config import Settings, load_settings
from frank.domain.errors import FrankError
from frank.domain.model.frank import CheckName
from frank.interfaces import wiring

CHAPTERS = DynamicPartitionsDefinition(name="chapter")


def _retry_settings() -> Settings:
    path = Path("config.toml")
    if not path.is_file():
        path = Path("config.example.toml")
    return load_settings(path)


_LLM_RETRY = RetryPolicy(
    max_retries=_retry_settings().budgets.asset_max_retries,
    delay=_retry_settings().budgets.asset_retry_delay_seconds,
    backoff=Backoff.EXPONENTIAL,
)


class FrankResource(ConfigurableResource):
    config_path: str = "config.toml"
    books_dir: str = "books"

    def settings(self) -> Settings:
        return load_settings(Path(self.config_path))

    def root(self) -> Path:
        return Path(self.books_dir)


class BookRunConfig(Config):
    slug: str
    source: str = ""
    lang: str = ""
    max_minutes: int | None = None
    max_passages: int | None = None


def _typed[F: Callable](fn: F) -> F:
    # Dagster reads inspect.signature before PEP 563 evaluation.
    fn.__annotations__ = get_type_hints(fn)
    return fn


@asset(group_name="frank")
@_typed
def ingest(
    context: AssetExecutionContext, config: BookRunConfig, frank: FrankResource
) -> Output[str]:
    if not config.source:
        raise Failure(description="source is required to ingest")
    settings = frank.settings()
    report = _call(
        lambda: ingest_book(
            wiring.ingest_ports(settings, frank.root()),
            wiring.ingest_request(
                settings, config.source, config.slug, config.lang or None
            ),
        )
    )
    _register_chapters(context, report.slug, frank.root())
    return Output(
        report.slug,
        metadata={
            "chapters": report.chapter_count,
            "paragraphs": report.paragraph_count,
        },
    )


@asset(deps=[ingest], group_name="frank", retry_policy=_LLM_RETRY)
@_typed
def segment(
    context: AssetExecutionContext, config: BookRunConfig, frank: FrankResource
) -> Output[str]:
    settings = frank.settings()
    report = _call(
        lambda: annotate_book(
            wiring.annotate_ports(settings, config.slug, frank.root()),
            config.slug,
            wiring.annotate_config(settings),
        )
    )
    _register_chapters(context, config.slug, frank.root())
    return Output(
        config.slug,
        metadata={
            "sentences": report.sentence_count,
            "tokens": report.token_count,
            "sense_units": report.sense_unit_count,
        },
    )


@asset(deps=[segment], group_name="frank", retry_policy=_LLM_RETRY)
@_typed
def analyze(
    context: AssetExecutionContext, config: BookRunConfig, frank: FrankResource
) -> Output[str]:
    settings = frank.settings()
    report = _call(
        lambda: analyze_book(
            wiring.analyze_ports(settings, config.slug, frank.root()),
            config.slug,
            wiring.analyze_config(settings),
        )
    )
    _register_chapters(context, config.slug, frank.root())
    return Output(
        config.slug,
        metadata={
            "terms": report.termbase.term_count,
            "characters": report.characters.character_count,
            "address_pairs": report.addresses.pair_count,
        },
    )


@asset(
    deps=[analyze],
    partitions_def=CHAPTERS,
    group_name="frank",
    retry_policy=_LLM_RETRY,
    pool="generation",
    backfill_policy=BackfillPolicy.multi_run(max_partitions_per_run=1),
)
@_typed
def generate(
    context: AssetExecutionContext, config: BookRunConfig, frank: FrankResource
) -> Output[str]:
    slug, index = _chapter_of(config, context)
    settings = frank.settings()
    budget = wiring.session_budget(settings, config.max_minutes, config.max_passages)
    report = _call(
        lambda: generate_chapter(
            wiring.generate_ports(settings, slug, frank.root()),
            slug,
            wiring.generate_config(settings, slug, frank.root(), budget),
            index,
        )
    )
    status = book_generation_status(wiring.status_ports(frank.root()), slug)
    return Output(
        slug,
        metadata={
            "chapter_index": index,
            "passages_done": report.passages_done,
            "passages_total": report.passages_total,
            "session_passages": report.session_passages,
            "needs_human": report.needs_human,
            "fast_count": report.fast_count,
            "smart_count": report.smart_count,
            "passages_per_hour": status.passages_per_hour or 0.0,
            "eta_hours": status.eta_hours or 0.0,
        },
    )


@asset(deps=[analyze], group_name="frank")
@_typed
def render(config: BookRunConfig, frank: FrankResource) -> Output[str]:
    out = wiring.render_path(frank.root(), config.slug)
    report = _call(
        lambda: render_book(wiring.render_ports(frank.root()), config.slug, out)
    )
    return Output(
        report.path, metadata={"passages": report.passages, "path": report.path}
    )


@asset_check(asset=segment, name="lemmas_present", blocking=True)
@_typed
def lemmas_present_check(
    config: BookRunConfig, frank: FrankResource
) -> AssetCheckResult:
    return _to_check(check_lemmas(wiring.check_ports(frank.root()), config.slug))


@asset_check(
    asset=generate,
    name="termbase_consistency",
    blocking=True,
    partitions_def=CHAPTERS,
)
@_typed
def termbase_consistency(
    context: AssetCheckExecutionContext, frank: FrankResource
) -> AssetCheckResult:
    return _record_check(context, frank, CheckName.TERMBASE)


@asset_check(
    asset=generate, name="ukrainian_language", blocking=True, partitions_def=CHAPTERS
)
@_typed
def ukrainian_language(
    context: AssetCheckExecutionContext, frank: FrankResource
) -> AssetCheckResult:
    return _record_check(context, frank, CheckName.UKRAINIAN)


@asset_check(
    asset=generate, name="gloss_coverage", blocking=True, partitions_def=CHAPTERS
)
@_typed
def gloss_coverage(
    context: AssetCheckExecutionContext, frank: FrankResource
) -> AssetCheckResult:
    return _record_check(context, frank, CheckName.GLOSS_COVERAGE)


@asset_check(
    asset=generate, name="sense_unit_coverage", blocking=True, partitions_def=CHAPTERS
)
@_typed
def sense_unit_coverage(
    context: AssetCheckExecutionContext, frank: FrankResource
) -> AssetCheckResult:
    return _record_check(context, frank, CheckName.SENSE_UNIT_COVERAGE)


@asset_check(
    asset=generate, name="tv_compliance", blocking=True, partitions_def=CHAPTERS
)
@_typed
def tv_compliance(
    context: AssetCheckExecutionContext, frank: FrankResource
) -> AssetCheckResult:
    return _record_check(context, frank, CheckName.TV)


@asset_check(
    asset=generate, name="back_translation", blocking=False, partitions_def=CHAPTERS
)
@_typed
def back_translation(
    context: AssetCheckExecutionContext, frank: FrankResource
) -> AssetCheckResult:
    slug, index = wiring.parse_chapter_partition(context.partition_key)
    report = check_back_translation(wiring.check_ports(frank.root()), slug, index)
    return _to_check(report, AssetCheckSeverity.WARN)


def _record_check(
    context: AssetCheckExecutionContext, frank: FrankResource, name: CheckName
) -> AssetCheckResult:
    slug, index = wiring.parse_chapter_partition(context.partition_key)
    settings = frank.settings()
    request = ChapterCheckRequest(
        slug=slug,
        chapter_index=index,
        name=name,
        validation=wiring.generate_config(
            settings,
            slug,
            frank.root(),
            wiring.session_budget(settings, None, None),
        ).validation,
    )
    return _to_check(check_named_records(wiring.check_ports(frank.root()), request))


def _to_check(
    report: StoredCheckReport, severity: AssetCheckSeverity = AssetCheckSeverity.ERROR
) -> AssetCheckResult:
    return AssetCheckResult(
        passed=report.passed,
        severity=severity if not report.passed else AssetCheckSeverity.ERROR,
        description=report.detail,
        metadata={"failed_count": report.failed_count},
    )


def _chapter_of(
    config: BookRunConfig, context: AssetExecutionContext
) -> tuple[str, int]:
    key = context.partition_key
    slug, index = wiring.parse_chapter_partition(key)
    if slug != config.slug:
        raise Failure(
            description=f"partition slug {slug!r} != config.slug {config.slug!r}"
        )
    return slug, index


def _register_chapters(
    context: AssetExecutionContext, slug: str, books_dir: Path
) -> None:
    structure = wiring.open_books(books_dir, slug).get_structure(slug)
    keys = [
        wiring.chapter_partition_key(slug, item.index) for item in structure.chapters
    ]
    context.instance.add_dynamic_partitions(CHAPTERS.name, keys)


def _call[T](action: Callable[[], T]) -> T:
    try:
        return action()
    except FrankError as exc:
        raise Failure(
            description=exc.message,
            metadata={"error_class": exc.error_class.value},
        ) from exc


defs = Definitions(
    assets=[ingest, segment, analyze, generate, render],
    asset_checks=[
        lemmas_present_check,
        termbase_consistency,
        ukrainian_language,
        gloss_coverage,
        sense_unit_coverage,
        tv_compliance,
        back_translation,
    ],
    resources={"frank": FrankResource()},
    jobs=[
        define_asset_job("frank_ingest", selection="ingest"),
        define_asset_job("frank_segment", selection="segment"),
        define_asset_job("frank_analyze", selection="analyze"),
        define_asset_job(
            "frank_generate",
            selection="generate",
            executor_def=in_process_executor,
        ),
        define_asset_job("frank_render", selection="render"),
    ],
)
