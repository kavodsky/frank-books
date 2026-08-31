"""OpenAI-protocol client against a mocked backend."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from frank.domain.errors import ModelTimeout, ModelUnreachable, SchemaInvalid
from frank.infrastructure.llm.client import (
    ChatMessage,
    CompletionRequest,
    OpenAiChatClient,
    RetryPolicy,
)


def _client(
    tmp_path, handler: Callable[[httpx.Request], httpx.Response]
) -> OpenAiChatClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    return OpenAiChatClient(
        retry=RetryPolicy(max_retries=2, min_seconds=0.01, max_seconds=0.05),
        log_dir=tmp_path / "logs",
        http=http,
    )


def _request() -> CompletionRequest:
    return CompletionRequest(
        messages=(ChatMessage(role="user", content="hi"),),
        model="fast-model",
        base_url="http://127.0.0.1:11434/v1",
        json_schema={"type": "object"},
        timeout_seconds=5,
    )


def _ok(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "choices": [{"message": {"role": "assistant", "content": content}}],
        },
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_returns_content_and_logs(tmp_path) -> None:
    client = _client(tmp_path, lambda _req: _ok('{"translation_uk": "привіт"}'))
    result = await client.complete(_request())
    await client.aclose()
    assert "привіт" in result.content
    logs = list((tmp_path / "logs").glob("llm-*.jsonl"))
    assert len(logs) == 1
    record = json.loads(logs[0].read_text(encoding="utf-8").splitlines()[0])
    assert record["model"] == "fast-model"
    assert record["prompt"][0]["content"] == "hi"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retries_then_succeeds(tmp_path) -> None:
    hits = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(503, text="busy")
        return _ok('{"ok": true}')

    client = _client(tmp_path, handler)
    result = await client.complete(_request())
    await client.aclose()
    assert hits["n"] == 2
    assert "ok" in result.content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_connect_error_is_model_unreachable(tmp_path) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _client(tmp_path, handler)
    with pytest.raises(ModelUnreachable):
        await client.complete(_request())
    await client.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_timeout_is_classified(tmp_path) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    client = _client(tmp_path, handler)
    with pytest.raises(ModelTimeout):
        await client.complete(_request())
    await client.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_json_content_is_schema_invalid(tmp_path) -> None:
    client = _client(tmp_path, lambda _req: _ok("not-json"))
    with pytest.raises(SchemaInvalid):
        await client.complete(_request())
    await client.aclose()
