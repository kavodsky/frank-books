"""Chapter-local SMART character mapping with an evidence-set cache (roadmap 3.3)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import TypeVar

from frank.domain.model.termbase import (
    ChapterEvidence,
    CharacterDraft,
    Gender,
    PersonEvidence,
)
from frank.infrastructure.llm.client import (
    ChatMessage,
    CompletionRequest,
    OpenAiChatClient,
)
from frank.infrastructure.llm.schemas import CharacterBatchResult, CharacterProposal
from frank.infrastructure.llm.templating import render_prompt
from frank.infrastructure.persistence.cache import CacheKey, StepCache

_T = TypeVar("_T")
_STEP = "character_map"
_SCHEMA = CharacterBatchResult.model_json_schema()
_TEMPLATE = "character_map.j2"
_GENDERS = {item.value: item for item in Gender}


@dataclass(frozen=True)
class MapConfig:
    model: str
    base_url: str
    timeout_seconds: float
    batch_size: int
    slug: str


@dataclass
class SmartCharacterMapper:
    client: OpenAiChatClient
    config: MapConfig
    cache: StepCache
    llm_calls: int = field(default=0)
    _loop: asyncio.AbstractEventLoop | None = field(
        default=None, repr=False, compare=False
    )

    def map_chapter(
        self, evidence: ChapterEvidence, lang: str
    ) -> tuple[CharacterDraft, ...]:
        if not evidence.persons:
            return ()
        key = _cache_key(self.config.slug, lang, evidence)
        hit = self.cache.get(key)
        if hit is not None:
            return _from_payload(hit)
        chosen = self._run(self._map(evidence, lang))
        self.cache.put(key, _to_payload(chosen))
        return chosen

    def _run(self, coro: Awaitable[_T]) -> _T:
        return self._ensure_loop().run_until_complete(coro)

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    async def _map(
        self, evidence: ChapterEvidence, lang: str
    ) -> tuple[CharacterDraft, ...]:
        wanted = {item.lemma.casefold() for item in evidence.persons}
        found: list[CharacterDraft] = []
        for batch in _batches(evidence.persons, self.config.batch_size):
            found.extend(await self._complete_batch(batch, lang, wanted))
        return tuple(found)

    async def _complete_batch(
        self,
        batch: tuple[PersonEvidence, ...],
        lang: str,
        wanted: set[str],
    ) -> tuple[CharacterDraft, ...]:
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
        parsed = CharacterBatchResult.model_validate_json(result.content)
        return tuple(
            _draft(item)
            for item in parsed.items
            if item.lemma.casefold() in wanted and item.canonical_name.strip()
        )


def _draft(item: CharacterProposal) -> CharacterDraft:
    aliases = tuple(
        dict.fromkeys(alias.strip() for alias in item.aliases if alias.strip())
    )
    lemma = item.lemma.strip()
    return CharacterDraft(
        lemma=lemma,
        canonical_name=item.canonical_name.strip() or lemma,
        translation_uk=item.translation_uk.strip(),
        gender=_GENDERS.get(item.gender, Gender.UNKNOWN),
        aliases=aliases,
        role_note=item.role_note.strip(),
    )


def _batches(
    items: tuple[PersonEvidence, ...], size: int
) -> tuple[tuple[PersonEvidence, ...], ...]:
    return tuple(items[index : index + size] for index in range(0, len(items), size))


def _batch_json(batch: tuple[PersonEvidence, ...]) -> str:
    payload = [
        {
            "lemma": item.lemma,
            "translation_uk": item.translation_uk,
            "surface_forms": list(item.surface_forms),
            "sentences": list(item.sentences),
        }
        for item in batch
    ]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _cache_key(slug: str, lang: str, evidence: ChapterEvidence) -> CacheKey:
    blob = json.dumps(
        {
            "lang": lang,
            "template": _TEMPLATE,
            "chapter_id": evidence.chapter_id,
            "persons": [
                {
                    "lemma": item.lemma,
                    "sentences": list(item.sentences),
                    "surfaces": list(item.surface_forms),
                }
                for item in evidence.persons
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return CacheKey(book_slug=slug, paragraph_hash=digest, step_name=_STEP)


def _to_payload(items: tuple[CharacterDraft, ...]) -> dict[str, object]:
    return {
        "drafts": [
            {
                "lemma": item.lemma,
                "canonical_name": item.canonical_name,
                "translation_uk": item.translation_uk,
                "gender": item.gender.value,
                "aliases": list(item.aliases),
                "role_note": item.role_note,
            }
            for item in items
        ]
    }


def _from_payload(payload: dict[str, object]) -> tuple[CharacterDraft, ...]:
    raw = payload.get("drafts")
    if not isinstance(raw, list):
        return ()
    found: list[CharacterDraft] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        found.append(
            CharacterDraft(
                lemma=str(item["lemma"]),
                canonical_name=str(item["canonical_name"]),
                translation_uk=str(item["translation_uk"]),
                gender=_GENDERS.get(str(item["gender"]).casefold(), Gender.UNKNOWN),
                aliases=tuple(str(alias) for alias in item.get("aliases", ())),
                role_note=str(item.get("role_note", "")),
            )
        )
    return tuple(found)
