"""Anti-corruption: LLM JSON for one paragraph becomes FrankRecords (roadmap 5.1)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from frank.domain.errors import SchemaInvalid
from frank.domain.model.annotation import SenseUnit, Token
from frank.domain.model.book import Sentence
from frank.domain.model.frank import (
    FrankRecord,
    ModelTier,
    SenseUnitTranslation,
    WordNote,
)
from frank.domain.ports.translator import ParagraphGenerationRequest
from frank.infrastructure.llm.client import (
    ChatMessage,
    CompletionRequest,
    OpenAiChatClient,
)
from frank.infrastructure.llm.schemas import (
    BackTranslateResult,
    ParagraphOut,
    SceneBriefResult,
    SentenceOut,
    WordNoteOut,
)
from frank.infrastructure.llm.templating import render_prompt

_T = TypeVar("_T")
_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
_PARAGRAPH_SCHEMA = ParagraphOut.model_json_schema()
_BRIEF_SCHEMA = SceneBriefResult.model_json_schema()
_BACK_SCHEMA = BackTranslateResult.model_json_schema()


@dataclass(frozen=True)
class GeneratorConfig:
    fast_model: str
    fast_url: str
    smart_model: str
    smart_url: str
    timeout_seconds: float
    scene_brief_sentences: int


@dataclass
class LlmFrankGenerator:
    client: OpenAiChatClient
    config: GeneratorConfig
    llm_calls: int = field(default=0)
    _loop: asyncio.AbstractEventLoop | None = field(
        default=None, repr=False, compare=False
    )

    def generate_fast(
        self, request: ParagraphGenerationRequest
    ) -> tuple[FrankRecord, ...]:
        return self._run(self._generate(request, ModelTier.FAST))

    def generate_smart(
        self, request: ParagraphGenerationRequest
    ) -> tuple[FrankRecord, ...]:
        return self._run(self._generate(request, ModelTier.SMART))

    def back_translate(self, text: str, source_lang: str, producer: ModelTier) -> str:
        return self._run(self._back_translate(text, source_lang, producer))

    def update_scene_brief(self, source_so_far: str, lang: str) -> str:
        return self._run(self._scene_brief(source_so_far, lang))

    def _run(self, coro: Awaitable[_T]) -> _T:
        return self._ensure_loop().run_until_complete(coro)

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    async def _generate(
        self, request: ParagraphGenerationRequest, tier: ModelTier
    ) -> tuple[FrankRecord, ...]:
        self.llm_calls += 1
        prompt = render_prompt(
            "generate_paragraph_input.j2",
            {
                "context": request.context.rendered,
                "payload_json": _payload_json(request),
                "correction": request.correction,
            },
        )
        parsed = await self._complete(prompt, tier, _PARAGRAPH_SCHEMA)
        return tuple(_record(item, request, tier) for item in _parse_paragraph(parsed))

    async def _scene_brief(self, source_so_far: str, lang: str) -> str:
        self.llm_calls += 1
        prompt = render_prompt(
            "scene_brief.j2",
            {
                "lang": lang,
                "sentence_max": str(self.config.scene_brief_sentences),
                "source": source_so_far,
            },
        )
        parsed = await self._complete(prompt, ModelTier.FAST, _BRIEF_SCHEMA)
        return _parse_brief(parsed)

    async def _back_translate(
        self, text: str, source_lang: str, producer: ModelTier
    ) -> str:
        self.llm_calls += 1
        prompt = render_prompt("back_translate.j2", {"lang": source_lang, "text": text})
        tier = ModelTier.SMART if producer is ModelTier.FAST else ModelTier.FAST
        parsed = await self._complete(prompt, tier, _BACK_SCHEMA)
        return _parse_back(parsed)

    async def _complete(
        self, prompt: str, tier: ModelTier, schema: dict[str, object]
    ) -> str:
        model, url = self._endpoint(tier)
        result = await self.client.complete(
            CompletionRequest(
                messages=(ChatMessage(role="user", content=prompt),),
                model=model,
                base_url=url,
                json_schema=schema,
                timeout_seconds=self.config.timeout_seconds,
            )
        )
        return result.content

    def _endpoint(self, tier: ModelTier) -> tuple[str, str]:
        if tier is ModelTier.FAST:
            return self.config.fast_model, self.config.fast_url
        return self.config.smart_model, self.config.smart_url


def prompt_version() -> str:
    names = ("generate_paragraph.j2", "generate_paragraph_input.j2")
    blob = "".join((_PROMPT_DIR / name).read_text(encoding="utf-8") for name in names)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def task_instruction(lang: str) -> str:
    return render_prompt("generate_paragraph.j2", {"lang": lang}).strip()


def _parse_paragraph(raw: str) -> list[SentenceOut]:
    try:
        return ParagraphOut.model_validate_json(raw).sentences
    except ValidationError as exc:
        raise SchemaInvalid(str(exc)) from exc


def _parse_brief(raw: str) -> str:
    try:
        return SceneBriefResult.model_validate_json(raw).summary_uk.strip()
    except ValidationError as exc:
        raise SchemaInvalid(str(exc)) from exc


def _parse_back(raw: str) -> str:
    try:
        return BackTranslateResult.model_validate_json(raw).text.strip()
    except ValidationError as exc:
        raise SchemaInvalid(str(exc)) from exc


def _record(
    item: SentenceOut, request: ParagraphGenerationRequest, tier: ModelTier
) -> FrankRecord:
    units = request.sense_units
    wanted = tuple(unit for unit in units if unit.sentence_id == item.sentence_id)
    gloss = tuple(
        token for token in request.gloss_tokens if token.sentence_id == item.sentence_id
    )
    return FrankRecord(
        sentence_id=item.sentence_id,
        units=_units(item, wanted),
        idiomatic_uk=item.idiomatic_uk.strip(),
        word_notes=_notes(item.word_notes, gloss),
        tier=tier,
    )


def _units(
    item: SentenceOut, expected: tuple[SenseUnit, ...]
) -> tuple[SenseUnitTranslation, ...]:
    found: list[SenseUnitTranslation] = []
    for index, unit in enumerate(expected):
        raw = item.units[index] if index < len(item.units) else None
        natural = raw.natural_uk.strip() if raw is not None else ""
        literal = None if raw is None else raw.word_for_word_uk
        found.append(
            SenseUnitTranslation(
                source_span=(unit.start_index, unit.end_index),
                natural_uk=natural,
                word_for_word_uk=_literal(natural, literal),
            )
        )
    return tuple(found)


def _literal(natural: str, raw: str | None) -> str | None:
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped or stripped == natural:
        return None
    return stripped


def _notes(raw: list[WordNoteOut], tokens: tuple[Token, ...]) -> tuple[WordNote, ...]:
    leftover = list(raw)
    return tuple(_note_for(token, leftover) for token in tokens)


def _note_for(token: Token, leftover: list[WordNoteOut]) -> WordNote:
    hit = _take_note(token, leftover)
    return WordNote(
        surface=token.surface,
        lemma=token.reunited_lemma or token.lemma,
        morph_note_uk="" if hit is None else hit.morph_note_uk.strip(),
        gloss_uk="" if hit is None else hit.gloss_uk.strip(),
    )


def _take_note(token: Token, leftover: list[WordNoteOut]) -> WordNoteOut | None:
    folded = token.surface.casefold()
    for index, item in enumerate(leftover):
        if item.surface.casefold() == folded:
            return leftover.pop(index)
    if leftover:
        return leftover.pop(0)
    return None


def _payload_json(request: ParagraphGenerationRequest) -> str:
    rows = [_sentence_payload(item, request) for item in request.sentences]
    return json.dumps(rows, ensure_ascii=False)


def _sentence_payload(
    sentence: Sentence, request: ParagraphGenerationRequest
) -> dict[str, object]:
    units = [item for item in request.sense_units if item.sentence_id == sentence.id]
    gloss = [item for item in request.gloss_tokens if item.sentence_id == sentence.id]
    return {
        "sentence_id": sentence.id,
        "text": sentence.text,
        "units": [
            {
                "index": item.index,
                "start": item.start_index,
                "end": item.end_index,
            }
            for item in units
        ],
        "glosses": [
            {
                "surface": item.surface,
                "lemma": item.reunited_lemma or item.lemma,
                "morph": _morph_text(item),
            }
            for item in gloss
        ],
    }


def _morph_text(token: Token) -> str:
    return "|".join(f"{item.key}={item.value}" for item in token.morph.features)
