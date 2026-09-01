"""SMART chapter summaries and StyleCard reduce (roadmap 3.5)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import TypeVar

from frank.domain.model.termbase import ChapterBrief, StyleCard, StyleReduceInput
from frank.infrastructure.llm.client import (
    ChatMessage,
    CompletionRequest,
    OpenAiChatClient,
)
from frank.infrastructure.llm.schemas import ChapterSummaryResult, StyleCardProposal
from frank.infrastructure.llm.templating import render_prompt
from frank.infrastructure.persistence.cache import CacheKey, StepCache

_T = TypeVar("_T")
_SUMMARY_STEP = "chapter_summary"
_STYLE_STEP = "style_card"
_SUMMARY_SCHEMA = ChapterSummaryResult.model_json_schema()
_STYLE_SCHEMA = StyleCardProposal.model_json_schema()
_SUMMARY_TEMPLATE = "chapter_summary.j2"
_STYLE_TEMPLATE = "style_card.j2"


@dataclass(frozen=True)
class StyleConfig:
    model: str
    base_url: str
    timeout_seconds: float
    slug: str
    summary_sentence_min: int
    summary_sentence_max: int


@dataclass
class SmartStyleBuilder:
    client: OpenAiChatClient
    config: StyleConfig
    cache: StepCache
    llm_calls: int = field(default=0)
    _loop: asyncio.AbstractEventLoop | None = field(
        default=None, repr=False, compare=False
    )

    def summarize(self, brief: ChapterBrief) -> str:
        if not brief.lead and not brief.tail:
            return ""
        key = _summary_key(self.config, brief)
        hit = self.cache.get(key)
        if hit is not None:
            return _summary_from_payload(hit)
        text = self._run(self._summarize(brief))
        self.cache.put(key, {"summary_uk": text})
        return text

    def compose(self, payload: StyleReduceInput) -> StyleCard:
        key = _style_key(self.config, payload)
        hit = self.cache.get(key)
        if hit is not None:
            return _style_from_payload(payload.book_id, hit)
        card = self._run(self._compose(payload))
        self.cache.put(key, _style_to_payload(card))
        return card

    def _run(self, coro: Awaitable[_T]) -> _T:
        return self._ensure_loop().run_until_complete(coro)

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    async def _summarize(self, brief: ChapterBrief) -> str:
        self.llm_calls += 1
        prompt = render_prompt(
            _SUMMARY_TEMPLATE,
            {
                "lang": brief.lang,
                "sentence_min": str(self.config.summary_sentence_min),
                "sentence_max": str(self.config.summary_sentence_max),
                "brief_json": _brief_json(brief),
            },
        )
        result = await self.client.complete(
            CompletionRequest(
                messages=(ChatMessage(role="user", content=prompt),),
                model=self.config.model,
                base_url=self.config.base_url,
                json_schema=_SUMMARY_SCHEMA,
                timeout_seconds=self.config.timeout_seconds,
            )
        )
        parsed = ChapterSummaryResult.model_validate_json(result.content)
        return parsed.summary_uk.strip()

    async def _compose(self, payload: StyleReduceInput) -> StyleCard:
        self.llm_calls += 1
        prompt = render_prompt(
            _STYLE_TEMPLATE,
            {"lang": payload.lang, "reduce_json": _reduce_json(payload)},
        )
        result = await self.client.complete(
            CompletionRequest(
                messages=(ChatMessage(role="user", content=prompt),),
                model=self.config.model,
                base_url=self.config.base_url,
                json_schema=_STYLE_SCHEMA,
                timeout_seconds=self.config.timeout_seconds,
            )
        )
        parsed = StyleCardProposal.model_validate_json(result.content)
        return _card(payload.book_id, parsed)


def _card(book_id: str, item: StyleCardProposal) -> StyleCard:
    return StyleCard(
        book_id=book_id,
        epoch=item.epoch.strip(),
        setting=item.setting.strip(),
        source_register=item.source_register.strip(),
        narration=item.narration.strip(),
        tone=item.tone.strip(),
        directives=item.directives.strip(),
    )


def _brief_json(brief: ChapterBrief) -> str:
    payload = {
        "index": brief.index,
        "title": brief.title,
        "lead": list(brief.lead),
        "tail": list(brief.tail),
        "characters": [
            {
                "canonical_name": item.canonical_name,
                "translation_uk": item.translation_uk,
            }
            for item in brief.characters
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _reduce_json(payload: StyleReduceInput) -> str:
    body = {
        "title": payload.title,
        "author": payload.author,
        "summaries": [
            {
                "index": item.index,
                "title": item.title,
                "summary_uk": item.summary_uk,
            }
            for item in payload.summaries
        ],
    }
    return json.dumps(body, ensure_ascii=False, sort_keys=True)


def _summary_key(config: StyleConfig, brief: ChapterBrief) -> CacheKey:
    blob = json.dumps(
        {
            "template": _SUMMARY_TEMPLATE,
            "min": config.summary_sentence_min,
            "max": config.summary_sentence_max,
            "brief": json.loads(_brief_json(brief)),
            "lang": brief.lang,
            "chapter_id": brief.chapter_id,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return CacheKey(
        book_slug=config.slug, paragraph_hash=digest, step_name=_SUMMARY_STEP
    )


def _style_key(config: StyleConfig, payload: StyleReduceInput) -> CacheKey:
    blob = json.dumps(
        {
            "template": _STYLE_TEMPLATE,
            "lang": payload.lang,
            "reduce": json.loads(_reduce_json(payload)),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return CacheKey(book_slug=config.slug, paragraph_hash=digest, step_name=_STYLE_STEP)


def _summary_from_payload(payload: dict[str, object]) -> str:
    return str(payload.get("summary_uk", "")).strip()


def _style_to_payload(card: StyleCard) -> dict[str, object]:
    return {
        "epoch": card.epoch,
        "setting": card.setting,
        "source_register": card.source_register,
        "narration": card.narration,
        "tone": card.tone,
        "directives": card.directives,
    }


def _style_from_payload(book_id: str, payload: dict[str, object]) -> StyleCard:
    return StyleCard(
        book_id=book_id,
        epoch=str(payload.get("epoch", "")),
        setting=str(payload.get("setting", "")),
        source_register=str(payload.get("source_register", "")),
        narration=str(payload.get("narration", "")),
        tone=str(payload.get("tone", "")),
        directives=str(payload.get("directives", "")),
    )
