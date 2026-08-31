"""SMART reunion arbitration is cached on the candidate set (roadmap 2.2c)."""

from __future__ import annotations

import json

import httpx
import pytest

from frank.domain.model.reunion import ReunionCandidate, ReunionSource
from frank.infrastructure.llm.client import OpenAiChatClient, RetryPolicy
from frank.infrastructure.nlp.lemma_arbiter import ArbiterConfig, SmartLemmaArbiter
from frank.infrastructure.persistence.cache import StepCache


class _Lexicon:
    def __init__(self, forms: frozenset[str]) -> None:
        self._forms = forms

    def contains(self, form: str) -> bool:
        return form.casefold() in self._forms


def _ok(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "choices": [{"message": {"role": "assistant", "content": content}}],
        },
    )


@pytest.mark.integration
def test_unchanged_reunions_make_zero_llm_calls_on_rerun(tmp_path) -> None:
    hits = {"n": 0}
    body = json.dumps(
        {"items": [{"particle": "an", "verb": "rufen", "reunited_lemma": "anrufen"}]}
    )

    def handler(_req: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return _ok(body)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    client = OpenAiChatClient(
        retry=RetryPolicy(max_retries=0, min_seconds=0.01, max_seconds=0.02),
        log_dir=tmp_path / "logs",
        http=http,
    )
    arbiter = SmartLemmaArbiter(
        client=client,
        config=ArbiterConfig(
            model="smart-model",
            base_url="http://127.0.0.1:8080/v1",
            timeout_seconds=5,
            batch_size=50,
            slug="oliver-de",
        ),
        cache=StepCache(tmp_path / "cache"),
        lexicon=_Lexicon(frozenset({"anrufen"})),
    )
    pending = (
        ReunionCandidate(
            sentence_id="s1",
            particle_token_id="s1-t3",
            verb_token_id="s1-t2",
            example_sentence="Er ruft an.",
            particle="an",
            verb="rufen",
            proposed_lemma="anrufen",
            needs_arbitration=True,
        ),
    )
    first = arbiter.decide_reunions(pending)
    assert hits["n"] == 1
    assert first[0].reunited_lemma == "anrufen"
    assert first[0].source is ReunionSource.LLM
    second = arbiter.decide_reunions(pending)
    assert hits["n"] == 1
    assert second == first
    assert arbiter.llm_calls == 1
