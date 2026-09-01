"""Batched SMART term translation with a candidate-set cache (roadmap 3.2)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import TypeVar

from frank.domain.model.termbase import Term, TermRendering
from frank.infrastructure.llm.client import (
    ChatMessage,
    CompletionRequest,
    OpenAiChatClient,
)
from frank.infrastructure.llm.schemas import TermBatchResult
from frank.infrastructure.llm.templating import render_prompt
from frank.infrastructure.persistence.cache import CacheKey, StepCache

_T = TypeVar("_T")
_STEP = "term_translate"
_SCHEMA = TermBatchResult.model_json_schema()
_TEMPLATE = "term_translate.j2"


@dataclass(frozen=True)
class TranslateConfig:
    model: str
    base_url: str
    timeout_seconds: float
    batch_size: int
    slug: str


@dataclass
class SmartTermTranslator:
    client: OpenAiChatClient
    config: TranslateConfig
    cache: StepCache
    llm_calls: int = field(default=0)
    _loop: asyncio.AbstractEventLoop | None = field(
        default=None, repr=False, compare=False
    )

    def propose(self, terms: tuple[Term, ...], lang: str) -> tuple[TermRendering, ...]:
        if not terms:
            return ()
        key = _cache_key(self.config.slug, lang, terms)
        hit = self.cache.get(key)
        if hit is not None:
            return _from_payload(hit)
        chosen = self._run(self._translate(terms, lang))
        self.cache.put(key, _to_payload(chosen))
        return chosen

    def _run(self, coro: Awaitable[_T]) -> _T:
        return self._ensure_loop().run_until_complete(coro)

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    async def _translate(
        self, terms: tuple[Term, ...], lang: str
    ) -> tuple[TermRendering, ...]:
        wanted = {item.lemma.casefold() for item in terms}
        found: list[TermRendering] = []
        for batch in _batches(terms, self.config.batch_size):
            found.extend(await self._complete_batch(batch, lang, wanted))
        return tuple(found)

    async def _complete_batch(
        self,
        batch: tuple[Term, ...],
        lang: str,
        wanted: set[str],
    ) -> tuple[TermRendering, ...]:
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
        parsed = TermBatchResult.model_validate_json(result.content)
        return tuple(
            _rendering(item.lemma, item.translation_uk, item.note)
            for item in parsed.items
            if item.lemma.casefold() in wanted and item.translation_uk.strip()
        )


def _rendering(lemma: str, translation_uk: str, note: str) -> TermRendering:
    return TermRendering(
        lemma=lemma.casefold(),
        translation_uk=translation_uk.strip(),
        note=note.strip(),
    )


def _batches(items: tuple[Term, ...], size: int) -> tuple[tuple[Term, ...], ...]:
    return tuple(items[index : index + size] for index in range(0, len(items), size))


def _batch_json(batch: tuple[Term, ...]) -> str:
    payload = [
        {
            "lemma": item.lemma,
            "kind": item.kind.value,
            "surface_forms": list(item.surface_forms),
        }
        for item in batch
    ]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _cache_key(slug: str, lang: str, terms: tuple[Term, ...]) -> CacheKey:
    blob = json.dumps(
        {
            "lang": lang,
            "template": _TEMPLATE,
            "terms": [
                {"id": item.id, "kind": item.kind.value, "lemma": item.lemma}
                for item in terms
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return CacheKey(book_slug=slug, paragraph_hash=digest, step_name=_STEP)


def _to_payload(items: tuple[TermRendering, ...]) -> dict[str, object]:
    return {
        "renderings": [
            {
                "lemma": item.lemma,
                "translation_uk": item.translation_uk,
                "note": item.note,
            }
            for item in items
        ]
    }


def _from_payload(payload: dict[str, object]) -> tuple[TermRendering, ...]:
    raw = payload.get("renderings")
    if not isinstance(raw, list):
        return ()
    found: list[TermRendering] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        found.append(
            _rendering(
                str(item["lemma"]), str(item["translation_uk"]), str(item["note"])
            )
        )
    return tuple(found)
