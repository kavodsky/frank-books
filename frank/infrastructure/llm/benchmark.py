"""Benchmark harness: gold sentences through candidate models (roadmap 0.4)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from sacrebleu.metrics import BLEU, CHRF

from frank.infrastructure.llm.client import (
    ChatMessage,
    CompletionRequest,
    OpenAiChatClient,
)
from frank.infrastructure.llm.schemas import BenchJudgement, BenchTranslation
from frank.infrastructure.llm.templating import render_prompt

_CHRF = CHRF()
_BLEU = BLEU(effective_order=True)


@dataclass(frozen=True)
class GoldSentence:
    id: str
    lang: str
    source: str
    reference_uk: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class ModelCandidate:
    name: str
    base_url: str


@dataclass(frozen=True)
class ScoredItem:
    gold: GoldSentence
    hypothesis: str
    chrf: float
    bleu: float
    judge_score: float | None


@dataclass(frozen=True)
class ModelReport:
    model: str
    items: tuple[ScoredItem, ...]
    chrf: float
    bleu: float
    judge: float | None


@dataclass(frozen=True)
class BenchPlan:
    gold: tuple[GoldSentence, ...]
    models: tuple[ModelCandidate, ...]
    judge: ModelCandidate
    timeout_seconds: float
    out_path: Path | None


def load_gold(path: Path) -> tuple[GoldSentence, ...]:
    sentences: list[GoldSentence] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "":
            continue
        sentences.append(_gold_from_json(json.loads(line)))
    return tuple(sentences)


def load_gold_files(paths: Sequence[Path]) -> tuple[GoldSentence, ...]:
    loaded: list[GoldSentence] = []
    for path in paths:
        loaded.extend(load_gold(path))
    return tuple(loaded)


def parse_model_spec(spec: str, default_base_url: str) -> ModelCandidate:
    if "@" not in spec:
        return ModelCandidate(name=spec, base_url=default_base_url)
    name, base_url = spec.split("@", 1)
    return ModelCandidate(name=name, base_url=base_url)


async def run_benchmark(client: OpenAiChatClient, plan: BenchPlan) -> str:
    reports: list[ModelReport] = []
    for model in plan.models:
        items = await _score_model(client, plan, model)
        reports.append(_summarize(model.name, items))
    markdown = render_report(tuple(reports))
    if plan.out_path is not None:
        plan.out_path.write_text(markdown, encoding="utf-8")
    return markdown


def render_report(reports: tuple[ModelReport, ...]) -> str:
    lines = [
        "# Benchmark report",
        "",
        "| model | chrF | BLEU | judge | n |",
        "|---|---:|---:|---:|---:|",
    ]
    for report in reports:
        judge = "—" if report.judge is None else f"{report.judge:.2f}"
        lines.append(
            f"| {report.model} | {report.chrf:.2f} | {report.bleu:.2f} "
            f"| {judge} | {len(report.items)} |"
        )
    lines.extend(["", "## Hard cases (separable verb / preverb)", ""])
    for report in reports:
        hard = [item for item in report.items if _is_hard(item.gold)]
        if not hard:
            continue
        chrf = mean(item.chrf for item in hard)
        lines.append(
            f"- **{report.model}** hard-subset chrF: {chrf:.2f} (n={len(hard)})"
        )
    return "\n".join(lines) + "\n"


def _gold_from_json(payload: dict[str, object]) -> GoldSentence:
    tags = payload.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    return GoldSentence(
        id=str(payload["id"]),
        lang=str(payload["lang"]),
        source=str(payload["source"]),
        reference_uk=str(payload["reference_uk"]),
        tags=tuple(str(tag) for tag in tags),
    )


def _is_hard(gold: GoldSentence) -> bool:
    return "separable_verb" in gold.tags or "preverb" in gold.tags


def _summarize(model: str, items: tuple[ScoredItem, ...]) -> ModelReport:
    hyps = [item.hypothesis for item in items]
    refs = [[item.gold.reference_uk for item in items]]
    judges = [item.judge_score for item in items if item.judge_score is not None]
    return ModelReport(
        model=model,
        items=items,
        chrf=_CHRF.corpus_score(hyps, refs).score,
        bleu=_BLEU.corpus_score(hyps, refs).score,
        judge=None if not judges else mean(judges),
    )


async def _score_model(
    client: OpenAiChatClient,
    plan: BenchPlan,
    model: ModelCandidate,
) -> tuple[ScoredItem, ...]:
    scored: list[ScoredItem] = []
    for gold in plan.gold:
        hyp = await _translate(client, plan, model, gold)
        judge = await _judge(client, plan, gold, hyp)
        scored.append(
            ScoredItem(
                gold=gold,
                hypothesis=hyp,
                chrf=_CHRF.sentence_score(hyp, [gold.reference_uk]).score,
                bleu=_BLEU.sentence_score(hyp, [gold.reference_uk]).score,
                judge_score=judge,
            )
        )
    return tuple(scored)


async def _translate(
    client: OpenAiChatClient,
    plan: BenchPlan,
    model: ModelCandidate,
    gold: GoldSentence,
) -> str:
    prompt = render_prompt(
        "bench_translate.j2",
        {"lang": gold.lang, "source": gold.source},
    )
    result = await client.complete(
        CompletionRequest(
            messages=(ChatMessage(role="user", content=prompt),),
            model=model.name,
            base_url=model.base_url,
            json_schema=BenchTranslation.model_json_schema(),
            timeout_seconds=plan.timeout_seconds,
        )
    )
    return BenchTranslation.model_validate_json(result.content).translation_uk


async def _judge(
    client: OpenAiChatClient,
    plan: BenchPlan,
    gold: GoldSentence,
    hypothesis: str,
) -> float | None:
    prompt = render_prompt(
        "bench_judge.j2",
        {
            "lang": gold.lang,
            "source": gold.source,
            "reference_uk": gold.reference_uk,
            "hypothesis": hypothesis,
        },
    )
    result = await client.complete(
        CompletionRequest(
            messages=(ChatMessage(role="user", content=prompt),),
            model=plan.judge.name,
            base_url=plan.judge.base_url,
            json_schema=BenchJudgement.model_json_schema(),
            timeout_seconds=plan.timeout_seconds,
        )
    )
    return float(BenchJudgement.model_validate_json(result.content).score)
