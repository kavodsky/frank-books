"""OpenAI-protocol chat client. No backend-specific paths (ADR 0009)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from frank.config import Settings
from frank.domain.errors import ModelTimeout, ModelUnreachable, SchemaInvalid

_CHAT_PATH = "/chat/completions"


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int
    min_seconds: float
    max_seconds: float


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class CompletionRequest:
    messages: tuple[ChatMessage, ...]
    model: str
    base_url: str
    json_schema: dict[str, Any] | None
    timeout_seconds: float


@dataclass(frozen=True)
class CompletionResult:
    content: str
    model: str
    latency_ms: float
    raw: dict[str, Any]


@dataclass(frozen=True)
class _CallLog:
    request: CompletionRequest
    payload: dict[str, Any] | None
    error: str | None
    latency_ms: float


class OpenAiChatClient:
    """Async `/v1/chat/completions` client with retries, timeout, and JSONL logs."""

    def __init__(
        self,
        retry: RetryPolicy,
        log_dir: Path,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._retry = retry
        self._log_dir = log_dir
        self._http = http or httpx.AsyncClient(trust_env=False)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        started = time.perf_counter()
        payload: dict[str, Any] | None = None
        error: str | None = None
        try:
            payload = await self._send(request)
            content = _message_content(payload)
            if request.json_schema is not None:
                _ensure_json(content)
            return CompletionResult(
                content=content,
                model=request.model,
                latency_ms=(time.perf_counter() - started) * 1000,
                raw=payload,
            )
        except (ModelUnreachable, ModelTimeout, SchemaInvalid) as exc:
            error = str(exc)
            raise
        except httpx.ConnectError as exc:
            error = str(exc)
            raise ModelUnreachable(str(exc)) from exc
        except httpx.TimeoutException as exc:
            error = str(exc)
            raise ModelTimeout(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            error = str(exc)
            raise _classify_status(exc) from exc
        finally:
            self._write_log(
                _CallLog(
                    request,
                    payload,
                    error,
                    (time.perf_counter() - started) * 1000,
                )
            )

    async def _send(self, request: CompletionRequest) -> dict[str, Any]:
        url = request.base_url.rstrip("/") + _CHAT_PATH
        body = _request_body(request)
        response = await self._post_with_retry(url, body, request.timeout_seconds)
        return _parse_json_body(response)

    async def _post_with_retry(
        self,
        url: str,
        body: dict[str, Any],
        timeout: float,
    ) -> httpx.Response:
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._retry.max_retries + 1),
            wait=wait_exponential(
                multiplier=self._retry.min_seconds,
                min=self._retry.min_seconds,
                max=self._retry.max_seconds,
            ),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        response: httpx.Response | None = None
        async for attempt in retrying:
            with attempt:
                response = await self._post_once(url, body, timeout)
        if response is None:
            raise ModelUnreachable("retry loop produced no response")
        return response

    async def _post_once(
        self,
        url: str,
        body: dict[str, Any],
        timeout: float,
    ) -> httpx.Response:
        response = await self._http.post(url, json=body, timeout=timeout)
        response.raise_for_status()
        return response

    def _write_log(self, record: _CallLog) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        path = self._log_dir / f"llm-{day}.jsonl"
        line = json.dumps(
            {
                "ts": datetime.now(UTC).isoformat(),
                "model": record.request.model,
                "base_url": record.request.base_url,
                "latency_ms": record.latency_ms,
                "prompt": [
                    {"role": m.role, "content": m.content}
                    for m in record.request.messages
                ],
                "response": record.payload,
                "error": record.error,
            },
            ensure_ascii=False,
        )
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def chat_client_from_settings(settings: Settings, log_dir: Path) -> OpenAiChatClient:
    policy = RetryPolicy(
        max_retries=settings.budgets.llm_max_retries,
        min_seconds=settings.budgets.llm_retry_min_seconds,
        max_seconds=settings.budgets.llm_retry_max_seconds,
    )
    return OpenAiChatClient(retry=policy, log_dir=log_dir)


def _request_body(request: CompletionRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": request.model,
        "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        "temperature": 0,
    }
    if request.json_schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "result",
                "strict": True,
                "schema": request.json_schema,
            },
        }
    return body


def _parse_json_body(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise SchemaInvalid(str(exc)) from exc
    if not isinstance(payload, dict):
        raise SchemaInvalid("response JSON is not an object")
    return payload


def _message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise SchemaInvalid("response has no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise SchemaInvalid("choice is not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise SchemaInvalid("response has no message")
    content = message.get("content")
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    if not isinstance(content, str) or content == "":
        raise SchemaInvalid("response content is empty")
    return content


def _ensure_json(content: str) -> None:
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        raise SchemaInvalid(str(exc)) from exc


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.ConnectError | httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return False


def _classify_status(exc: httpx.HTTPStatusError) -> ModelUnreachable | SchemaInvalid:
    if exc.response.status_code in {429, 500, 502, 503, 504}:
        return ModelUnreachable(str(exc))
    return SchemaInvalid(str(exc))
