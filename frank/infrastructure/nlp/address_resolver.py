"""SMART T/V resolution for heuristic-unresolved AddressPair rows (roadmap 3.4)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import TypeVar

from frank.domain.model.termbase import AddressPair, TvForm, UnresolvedPair
from frank.infrastructure.llm.client import (
    ChatMessage,
    CompletionRequest,
    OpenAiChatClient,
)
from frank.infrastructure.llm.schemas import AddressBatchResult, AddressProposal
from frank.infrastructure.llm.templating import render_prompt
from frank.infrastructure.persistence.cache import CacheKey, StepCache

_T = TypeVar("_T")
_STEP = "address_resolve"
_SCHEMA = AddressBatchResult.model_json_schema()
_TEMPLATE = "address_resolve.j2"
_FORMS = {item.value: item for item in TvForm}


@dataclass(frozen=True)
class ResolveConfig:
    model: str
    base_url: str
    timeout_seconds: float
    batch_size: int
    slug: str


@dataclass
class SmartAddressResolver:
    client: OpenAiChatClient
    config: ResolveConfig
    cache: StepCache
    llm_calls: int = field(default=0)
    _loop: asyncio.AbstractEventLoop | None = field(
        default=None, repr=False, compare=False
    )

    def resolve(
        self, pairs: tuple[UnresolvedPair, ...], lang: str
    ) -> tuple[AddressPair, ...]:
        if not pairs:
            return ()
        key = _cache_key(self.config.slug, lang, pairs)
        hit = self.cache.get(key)
        if hit is not None:
            return _from_payload(hit)
        chosen = self._run(self._resolve(pairs, lang))
        self.cache.put(key, _to_payload(chosen))
        return chosen

    def _run(self, coro: Awaitable[_T]) -> _T:
        return self._ensure_loop().run_until_complete(coro)

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    async def _resolve(
        self, pairs: tuple[UnresolvedPair, ...], lang: str
    ) -> tuple[AddressPair, ...]:
        wanted = {(item.speaker_id, item.addressee_id) for item in pairs}
        found: list[AddressPair] = []
        for batch in _batches(pairs, self.config.batch_size):
            found.extend(await self._complete_batch(batch, lang, wanted))
        return tuple(found)

    async def _complete_batch(
        self,
        batch: tuple[UnresolvedPair, ...],
        lang: str,
        wanted: set[tuple[str, str]],
    ) -> tuple[AddressPair, ...]:
        self.llm_calls += 1
        prompt = render_prompt(
            _TEMPLATE, {"lang": lang, "batch_json": _batch_json(batch)}
        )
        result = await self.client.complete(
            CompletionRequest(
                messages=(ChatMessage(role="user", content=prompt),),
                model=self.config.model,
                base_url=self.config.base_url,
                json_schema=_SCHEMA,
                timeout_seconds=self.config.timeout_seconds,
            )
        )
        parsed = AddressBatchResult.model_validate_json(result.content)
        book_id = batch[0].book_id
        return tuple(
            _pair(item, book_id)
            for item in parsed.items
            if (item.speaker_id, item.addressee_id) in wanted
        )


def _pair(item: AddressProposal, book_id: str) -> AddressPair:
    return AddressPair(
        book_id=book_id,
        speaker_id=item.speaker_id.strip(),
        addressee_id=item.addressee_id.strip(),
        tv_form=_FORMS.get(item.tv_form, TvForm.MIXED),
    )


def _batches(
    items: tuple[UnresolvedPair, ...], size: int
) -> tuple[tuple[UnresolvedPair, ...], ...]:
    return tuple(items[index : index + size] for index in range(0, len(items), size))


def _batch_json(batch: tuple[UnresolvedPair, ...]) -> str:
    payload = [
        {
            "speaker_id": item.speaker_id,
            "addressee_id": item.addressee_id,
            "speaker_name": item.speaker_name,
            "addressee_name": item.addressee_name,
            "sentences": list(item.sentences),
        }
        for item in batch
    ]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _cache_key(slug: str, lang: str, pairs: tuple[UnresolvedPair, ...]) -> CacheKey:
    blob = json.dumps(
        {
            "lang": lang,
            "template": _TEMPLATE,
            "pairs": [
                {
                    "speaker_id": item.speaker_id,
                    "addressee_id": item.addressee_id,
                    "sentences": list(item.sentences),
                }
                for item in pairs
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return CacheKey(book_slug=slug, paragraph_hash=digest, step_name=_STEP)


def _to_payload(items: tuple[AddressPair, ...]) -> dict[str, object]:
    return {
        "pairs": [
            {
                "book_id": item.book_id,
                "speaker_id": item.speaker_id,
                "addressee_id": item.addressee_id,
                "tv_form": item.tv_form.value,
            }
            for item in items
        ]
    }


def _from_payload(payload: dict[str, object]) -> tuple[AddressPair, ...]:
    raw = payload.get("pairs")
    if not isinstance(raw, list):
        return ()
    found: list[AddressPair] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        found.append(
            AddressPair(
                book_id=str(item["book_id"]),
                speaker_id=str(item["speaker_id"]),
                addressee_id=str(item["addressee_id"]),
                tv_form=_FORMS.get(str(item["tv_form"]), TvForm.MIXED),
            )
        )
    return tuple(found)
