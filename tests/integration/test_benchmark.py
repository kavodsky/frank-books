"""`frank bench` produces a markdown report against a mocked backend."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from frank.infrastructure.llm.benchmark import (
    BenchPlan,
    ModelCandidate,
    load_gold,
    run_benchmark,
)
from frank.infrastructure.llm.client import OpenAiChatClient, RetryPolicy
from frank.interfaces.cli import app

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "gold_mini.jsonl"


def _handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    prompt = body["messages"][0]["content"]
    if "Score 1" in prompt:
        content = json.dumps({"score": 4, "comment": "ok"}, ensure_ascii=False)
    elif "Olvasd" in prompt:
        content = json.dumps({"translation_uk": "Прочитай листа!"}, ensure_ascii=False)
    else:
        content = json.dumps(
            {"translation_uk": "Він телефонує своїй матері."}, ensure_ascii=False
        )
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": content}}]},
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_benchmark_writes_markdown_report(tmp_path) -> None:
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        trust_env=False,
    )
    client = OpenAiChatClient(
        retry=RetryPolicy(max_retries=0, min_seconds=0.01, max_seconds=0.02),
        log_dir=tmp_path / "logs",
        http=http,
    )
    out = tmp_path / "report.md"
    markdown = await run_benchmark(
        client,
        BenchPlan(
            gold=load_gold(FIXTURE),
            models=(
                ModelCandidate(name="fast-model", base_url="http://127.0.0.1:1/v1"),
            ),
            judge=ModelCandidate(name="smart-model", base_url="http://127.0.0.1:1/v1"),
            timeout_seconds=5,
            out_path=out,
        ),
    )
    await client.aclose()
    assert out.read_text(encoding="utf-8") == markdown
    assert "| chrF |" in markdown
    assert "fast-model" in markdown
    assert "Hard cases" in markdown


@pytest.mark.integration
def test_bench_help_lists_command() -> None:
    result = CliRunner().invoke(app, ["bench", "--help"])
    assert result.exit_code == 0
    assert "--gold" in result.stdout
    assert "--models" in result.stdout
