"""Batched SMART lemma arbitration with a disputed-type cache (roadmap 2.2b)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import TypeVar

from frank.domain.model.lemma import DisputedLemma, LemmaOverride, LemmaSource
from frank.domain.model.reunion import ReunionCandidate, VerbParticle
from frank.domain.ports.linguistics import LemmaLexicon
from frank.infrastructure.llm.client import (
    ChatMessage,
    CompletionRequest,
    OpenAiChatClient,
)
from frank.infrastructure.llm.schemas import LemmaBatchResult
from frank.infrastructure.llm.templating import render_prompt
from frank.infrastructure.persistence.cache import CacheKey, StepCache

_T = TypeVar("_T")
_STEP = "lemma_refine"
_SCHEMA = LemmaBatchResult.model_json_schema()


@dataclass(frozen=True)
class ArbiterConfig:
    model: str
    base_url: str
    timeout_seconds: float
    batch_size: int
    slug: str


@dataclass
class SmartLemmaArbiter:
    client: OpenAiChatClient
    config: ArbiterConfig
    cache: StepCache
    lexicon: LemmaLexicon
    llm_calls: int = field(default=0)
    _loop: asyncio.AbstractEventLoop | None = field(
        default=None, repr=False, compare=False
    )

    def decide(self, disputed: tuple[DisputedLemma, ...]) -> tuple[LemmaOverride, ...]:
        if not disputed:
            return ()
        key = _cache_key(self.config.slug, disputed)
        hit = self.cache.get(key)
        if hit is not None:
            return _overrides_from_payload(hit)
        chosen = self._run(self._arbitrate(disputed))
        self.cache.put(key, _payload_from_overrides(chosen))
        return chosen

    def decide_reunions(
        self, pending: tuple[ReunionCandidate, ...]
    ) -> tuple[VerbParticle, ...]:
        from frank.infrastructure.nlp.reunion_arbiter import ReunionArbiter

        inner = ReunionArbiter(
            client=self.client,
            config=self.config,
            cache=self.cache,
            lexicon=self.lexicon,
            loop=self._ensure_loop(),
        )
        found = inner.decide(pending)
        self.llm_calls += inner.llm_calls
        return found

    def _run(self, coro: Awaitable[_T]) -> _T:
        return self._ensure_loop().run_until_complete(coro)

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    async def _arbitrate(
        self, disputed: tuple[DisputedLemma, ...]
    ) -> tuple[LemmaOverride, ...]:
        first = await self._complete_batches(disputed, "lemma_arbitrate.j2")
        validated, unknown = _split_valid(disputed, first, self.lexicon)
        if not unknown:
            return validated
        second = await self._vote_batches(unknown, first)
        return validated + _confirm_votes(unknown, first, second)

    async def _vote_batches(
        self,
        unknown: tuple[DisputedLemma, ...],
        first: dict[tuple[str, str], str],
    ) -> dict[tuple[str, str], str]:
        chosen: dict[tuple[str, str], str] = {}
        for batch in _batches(unknown, self.config.batch_size):
            payload = _vote_json(batch, first)
            chosen.update(await self._complete_json(payload, "lemma_vote.j2"))
        return chosen

    async def _complete_batches(
        self,
        disputed: tuple[DisputedLemma, ...],
        template: str,
    ) -> dict[tuple[str, str], str]:
        chosen: dict[tuple[str, str], str] = {}
        for batch in _batches(disputed, self.config.batch_size):
            chosen.update(await self._complete_json(_batch_json(batch), template))
        return chosen

    async def _complete_json(
        self,
        batch_json: str,
        template: str,
    ) -> dict[tuple[str, str], str]:
        self.llm_calls += 1
        prompt = render_prompt(template, {"batch_json": batch_json})
        result = await self.client.complete(
            CompletionRequest(
                messages=(ChatMessage(role="user", content=prompt),),
                model=self.config.model,
                base_url=self.config.base_url,
                json_schema=_SCHEMA,
                timeout_seconds=self.config.timeout_seconds,
            )
        )
        parsed = LemmaBatchResult.model_validate_json(result.content)
        return {(item.surface, item.upos): item.lemma for item in parsed.items}


def _split_valid(
    disputed: tuple[DisputedLemma, ...],
    first: dict[tuple[str, str], str],
    lexicon: LemmaLexicon,
) -> tuple[tuple[LemmaOverride, ...], tuple[DisputedLemma, ...]]:
    accepted: list[LemmaOverride] = []
    unknown: list[DisputedLemma] = []
    for item in disputed:
        lemma = first.get((item.surface, item.upos))
        if lemma is None:
            accepted.append(_kept(item))
            continue
        if lexicon.contains(lemma):
            accepted.append(_override(item, lemma, LemmaSource.LLM))
            continue
        unknown.append(item)
    return tuple(accepted), tuple(unknown)


def _confirm_votes(
    unknown: tuple[DisputedLemma, ...],
    first: dict[tuple[str, str], str],
    second: dict[tuple[str, str], str],
) -> tuple[LemmaOverride, ...]:
    found: list[LemmaOverride] = []
    for item in unknown:
        key = (item.surface, item.upos)
        proposal = first.get(key)
        vote = second.get(key)
        if proposal is not None and proposal == vote:
            found.append(_override(item, proposal, LemmaSource.LLM_VOTE))
            continue
        found.append(_kept(item))
    return tuple(found)


def _kept(item: DisputedLemma) -> LemmaOverride:
    return _override(item, item.analyzer_lemma, LemmaSource.ANALYZER_KEPT)


def _override(item: DisputedLemma, lemma: str, source: LemmaSource) -> LemmaOverride:
    return LemmaOverride(
        surface=item.surface,
        upos=item.upos,
        lemma=lemma,
        source=source,
    )


def _batches(
    items: tuple[DisputedLemma, ...], size: int
) -> tuple[tuple[DisputedLemma, ...], ...]:
    return tuple(items[index : index + size] for index in range(0, len(items), size))


def _batch_json(batch: tuple[DisputedLemma, ...]) -> str:
    payload = [
        {
            "surface": item.surface,
            "upos": item.upos,
            "example_sentence": item.example_sentence,
            "analyzer_lemma": item.analyzer_lemma,
            "second_lemma": item.second_lemma,
        }
        for item in batch
    ]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _vote_json(
    batch: tuple[DisputedLemma, ...], first: dict[tuple[str, str], str]
) -> str:
    payload = [
        {
            "surface": item.surface,
            "upos": item.upos,
            "example_sentence": item.example_sentence,
            "proposed_lemma": first[(item.surface, item.upos)],
        }
        for item in batch
    ]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _cache_key(slug: str, disputed: tuple[DisputedLemma, ...]) -> CacheKey:
    blob = json.dumps(
        [
            {
                "surface": item.surface,
                "upos": item.upos,
                "analyzer_lemma": item.analyzer_lemma,
                "second_lemma": item.second_lemma,
            }
            for item in disputed
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return CacheKey(book_slug=slug, paragraph_hash=digest, step_name=_STEP)


def _payload_from_overrides(overrides: tuple[LemmaOverride, ...]) -> dict[str, object]:
    return {
        "overrides": [
            {
                "surface": item.surface,
                "upos": item.upos,
                "lemma": item.lemma,
                "source": item.source.value,
            }
            for item in overrides
        ]
    }


def _overrides_from_payload(payload: dict[str, object]) -> tuple[LemmaOverride, ...]:
    raw = payload["overrides"]
    if not isinstance(raw, list):
        return ()
    return tuple(_override_from_dict(item) for item in raw if isinstance(item, dict))


def _override_from_dict(item: dict[str, object]) -> LemmaOverride:
    return LemmaOverride(
        surface=str(item["surface"]),
        upos=str(item["upos"]),
        lemma=str(item["lemma"]),
        source=LemmaSource(str(item["source"])),
    )
