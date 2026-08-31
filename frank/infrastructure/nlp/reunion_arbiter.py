"""Batched SMART reunion arbitration with a candidate-set cache (roadmap 2.2c)."""

from __future__ import annotations

import hashlib
import json
from asyncio import AbstractEventLoop
from dataclasses import dataclass, field

from frank.domain.model.reunion import ReunionCandidate, ReunionSource, VerbParticle
from frank.domain.ports.linguistics import LemmaLexicon
from frank.infrastructure.llm.client import (
    ChatMessage,
    CompletionRequest,
    OpenAiChatClient,
)
from frank.infrastructure.llm.schemas import ReunionBatchResult
from frank.infrastructure.llm.templating import render_prompt
from frank.infrastructure.nlp.lemma_arbiter import ArbiterConfig
from frank.infrastructure.persistence.cache import CacheKey, StepCache

_STEP = "lemma_reunite"
_SCHEMA = ReunionBatchResult.model_json_schema()


@dataclass
class ReunionArbiter:
    client: OpenAiChatClient
    config: ArbiterConfig
    cache: StepCache
    lexicon: LemmaLexicon
    loop: AbstractEventLoop
    llm_calls: int = field(default=0)

    def decide(self, pending: tuple[ReunionCandidate, ...]) -> tuple[VerbParticle, ...]:
        if not pending:
            return ()
        key = _cache_key(self.config.slug, pending)
        hit = self.cache.get(key)
        if hit is not None:
            return _from_payload(hit)
        chosen = self.loop.run_until_complete(self._arbitrate(pending))
        self.cache.put(key, _to_payload(chosen))
        return chosen

    async def _arbitrate(
        self, pending: tuple[ReunionCandidate, ...]
    ) -> tuple[VerbParticle, ...]:
        first = await self._complete_batches(pending, "lemma_reunite.j2")
        validated, unknown = _split_valid(pending, first, self.lexicon)
        if not unknown:
            return validated
        second = await self._vote_batches(unknown, first)
        return validated + _confirm_votes(unknown, first, second)

    async def _vote_batches(
        self,
        unknown: tuple[ReunionCandidate, ...],
        first: dict[tuple[str, str], str | None],
    ) -> dict[tuple[str, str], str | None]:
        chosen: dict[tuple[str, str], str | None] = {}
        for batch in _batches(unknown, self.config.batch_size):
            payload = _vote_json(batch, first)
            chosen.update(await self._complete_json(payload, "lemma_reunite_vote.j2"))
        return chosen

    async def _complete_batches(
        self,
        pending: tuple[ReunionCandidate, ...],
        template: str,
    ) -> dict[tuple[str, str], str | None]:
        chosen: dict[tuple[str, str], str | None] = {}
        for batch in _batches(pending, self.config.batch_size):
            chosen.update(await self._complete_json(_batch_json(batch), template))
        return chosen

    async def _complete_json(
        self,
        batch_json: str,
        template: str,
    ) -> dict[tuple[str, str], str | None]:
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
        parsed = ReunionBatchResult.model_validate_json(result.content)
        return {
            (item.particle.casefold(), item.verb.casefold()): item.reunited_lemma
            for item in parsed.items
        }


def _split_valid(
    pending: tuple[ReunionCandidate, ...],
    first: dict[tuple[str, str], str | None],
    lexicon: LemmaLexicon,
) -> tuple[tuple[VerbParticle, ...], tuple[ReunionCandidate, ...]]:
    accepted: list[VerbParticle] = []
    unknown: list[ReunionCandidate] = []
    for item in pending:
        lemma = first.get(_key(item))
        if lemma is None:
            continue
        if lexicon.contains(lemma):
            accepted.append(_particle(item, lemma, ReunionSource.LLM))
            continue
        unknown.append(item)
    return tuple(accepted), tuple(unknown)


def _confirm_votes(
    unknown: tuple[ReunionCandidate, ...],
    first: dict[tuple[str, str], str | None],
    second: dict[tuple[str, str], str | None],
) -> tuple[VerbParticle, ...]:
    found: list[VerbParticle] = []
    for item in unknown:
        key = _key(item)
        proposal = first.get(key)
        vote = second.get(key)
        if proposal is not None and proposal == vote:
            found.append(_particle(item, proposal, ReunionSource.LLM_VOTE))
    return tuple(found)


def _particle(
    item: ReunionCandidate, lemma: str, source: ReunionSource
) -> VerbParticle:
    return VerbParticle(
        sentence_id=item.sentence_id,
        particle_token_id=item.particle_token_id,
        verb_token_id=item.verb_token_id,
        reunited_lemma=lemma,
        source=source,
    )


def _batches(
    items: tuple[ReunionCandidate, ...], size: int
) -> tuple[tuple[ReunionCandidate, ...], ...]:
    return tuple(items[index : index + size] for index in range(0, len(items), size))


def _batch_json(batch: tuple[ReunionCandidate, ...]) -> str:
    payload = [
        {
            "particle": item.particle,
            "verb": item.verb,
            "example_sentence": item.example_sentence,
            "proposed_lemma": item.proposed_lemma,
        }
        for item in batch
    ]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _vote_json(
    batch: tuple[ReunionCandidate, ...], first: dict[tuple[str, str], str | None]
) -> str:
    payload = [
        {
            "particle": item.particle,
            "verb": item.verb,
            "example_sentence": item.example_sentence,
            "proposed_lemma": first.get(_key(item)),
        }
        for item in batch
    ]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _key(item: ReunionCandidate) -> tuple[str, str]:
    return (item.particle.casefold(), item.verb.casefold())


def _cache_key(slug: str, pending: tuple[ReunionCandidate, ...]) -> CacheKey:
    blob = json.dumps(
        [
            {
                "particle": item.particle,
                "verb": item.verb,
                "proposed_lemma": item.proposed_lemma,
            }
            for item in pending
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return CacheKey(book_slug=slug, paragraph_hash=digest, step_name=_STEP)


def _to_payload(particles: tuple[VerbParticle, ...]) -> dict[str, object]:
    return {
        "particles": [
            {
                "sentence_id": item.sentence_id,
                "particle_token_id": item.particle_token_id,
                "verb_token_id": item.verb_token_id,
                "reunited_lemma": item.reunited_lemma,
                "source": item.source.value,
            }
            for item in particles
        ]
    }


def _from_payload(payload: dict[str, object]) -> tuple[VerbParticle, ...]:
    raw = payload["particles"]
    if not isinstance(raw, list):
        return ()
    return tuple(_from_dict(item) for item in raw if isinstance(item, dict))


def _from_dict(item: dict[str, object]) -> VerbParticle:
    return VerbParticle(
        sentence_id=str(item["sentence_id"]),
        particle_token_id=str(item["particle_token_id"]),
        verb_token_id=str(item["verb_token_id"]),
        reunited_lemma=str(item["reunited_lemma"]),
        source=ReunionSource(str(item["source"])),
    )
