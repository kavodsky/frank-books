"""Anti-corruption: paragraph JSON becomes FrankRecords (roadmap 5.1)."""

from __future__ import annotations

import json

import httpx
import pytest

from frank.domain.model.annotation import MorphFeature, Morphology, SenseUnit, Token
from frank.domain.model.book import Sentence
from frank.domain.model.context import PromptContext
from frank.domain.model.frank import ModelTier
from frank.domain.ports.translator import ParagraphGenerationRequest
from frank.infrastructure.llm.client import OpenAiChatClient, RetryPolicy
from frank.infrastructure.llm.generator import GeneratorConfig, LlmFrankGenerator


def _ok(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "choices": [{"message": {"role": "assistant", "content": content}}],
        },
    )


def _client(tmp_path, handler) -> OpenAiChatClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    return OpenAiChatClient(
        retry=RetryPolicy(max_retries=0, min_seconds=0.01, max_seconds=0.02),
        log_dir=tmp_path / "logs",
        http=http,
    )


def _request() -> ParagraphGenerationRequest:
    token = Token(
        id="s1-t1",
        sentence_id="s1",
        index=1,
        surface="ruft",
        lemma="rufen",
        upos="VERB",
        morph=Morphology(features=(MorphFeature(key="Person", value="3"),)),
        reunited_lemma="anrufen",
    )
    return ParagraphGenerationRequest(
        context=PromptContext(
            paragraph_id="p1",
            sections=(),
            rendered="TASK",
            token_count=1,
            rolling_window_text="",
        ),
        sentences=(Sentence(id="s1", paragraph_id="p1", index=1, text="Er ruft an."),),
        sense_units=(
            SenseUnit(id="u1", sentence_id="s1", index=1, start_index=1, end_index=3),
        ),
        gloss_tokens=(token,),
        lang="de",
    )


@pytest.mark.integration
def test_generate_fast_overwrites_lemma_and_does_not_repeat_instruction(
    tmp_path,
) -> None:
    seen: list[str] = []
    body = json.dumps(
        {
            "sentences": [
                {
                    "sentence_id": "s1",
                    "units": [
                        {
                            "source_span": [9, 9],
                            "natural_uk": "він телефонує",
                            "word_for_word_uk": None,
                        }
                    ],
                    "idiomatic_uk": "Він телефонує.",
                    "word_notes": [
                        {
                            "surface": "ruft",
                            "lemma": "hallucinated",
                            "morph_note_uk": "3 ос.",
                            "gloss_uk": "телефонує",
                        }
                    ],
                }
            ]
        }
    )

    def handler(req: httpx.Request) -> httpx.Response:
        payload = json.loads(req.content)
        seen.append(payload["messages"][0]["content"])
        return _ok(body)

    generator = LlmFrankGenerator(
        client=_client(tmp_path, handler),
        config=GeneratorConfig(
            fast_model="fast-model",
            fast_url="http://127.0.0.1:11434/v1",
            smart_model="smart-model",
            smart_url="http://127.0.0.1:8080/v1",
            timeout_seconds=5,
            scene_brief_sentences=2,
        ),
    )
    records = generator.generate_fast(_request())
    assert generator.llm_calls == 1
    assert records[0].tier is ModelTier.FAST
    assert records[0].units[0].source_span == (1, 3)
    assert records[0].word_notes[0].lemma == "anrufen"
    assert records[0].word_notes[0].gloss_uk == "телефонує"
    prompt = seen[0]
    assert prompt.startswith("TASK")
    assert "Paragraph JSON" in prompt
    assert prompt.count("You produce Ilya Frank data") == 0
