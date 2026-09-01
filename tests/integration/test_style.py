"""SMART summaries use lead/tail; StyleCard persists (roadmap 3.5)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from frank.application.build_style import StylePorts, build_style_card
from frank.domain.model.annotation import Annotation
from frank.domain.model.book import (
    Book,
    BookStatus,
    BookStructure,
    Chapter,
    Paragraph,
    ParagraphStatus,
    Sentence,
)
from frank.domain.model.termbase import (
    ChapterBriefConfig,
    Character,
    Gender,
)
from frank.infrastructure.llm.client import OpenAiChatClient, RetryPolicy
from frank.infrastructure.nlp.style_builder import SmartStyleBuilder, StyleConfig
from frank.infrastructure.persistence.cache import StepCache
from frank.infrastructure.persistence.repositories import SqliteBookRepository
from frank.infrastructure.persistence.tables import create_book_db

_CFG = ChapterBriefConfig(
    lead_sentences=3,
    tail_sentences=3,
    summary_sentence_min=3,
    summary_sentence_max=5,
)
_DUMP = "CHAPTER_DUMP"


def _ok(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "choices": [{"message": {"role": "assistant", "content": content}}],
        },
    )


def _structure() -> BookStructure:
    return BookStructure(
        book=Book(
            id="book",
            slug="plot",
            lang="de",
            title="Oliver Twist",
            author="Dickens",
            source_url="file.txt",
            license_note="",
            status=BookStatus.INGESTED,
        ),
        chapters=(Chapter(id="book-c1", book_id="book", index=1, title="I"),),
        paragraphs=(
            Paragraph(
                id="book-c1-p1",
                chapter_id="book-c1",
                passage_id=None,
                index=1,
                raw_text="x",
                hash="h",
                status=ParagraphStatus.RAW,
            ),
        ),
    )


def _sentences() -> tuple[Sentence, ...]:
    texts = [f"Oliver satz {index}." for index in range(1, 21)]
    texts[9] = f"{_DUMP} in der Mitte."
    return tuple(
        Sentence(id=f"s{index}", paragraph_id="book-c1-p1", index=index, text=text)
        for index, text in enumerate(texts, start=1)
    )


def _summary_body() -> str:
    return json.dumps(
        {
            "summary_uk": (
                "Олівер народжується. Його віддають до робітного дому. "
                "Він просить ще каші. Наглядач лютує. Рада вирішує його віддати. "
                "Шоста зайва."
            )
        }
    )


def _style_body() -> str:
    return json.dumps(
        {
            "epoch": "XIX ст.",
            "setting": "Лондон",
            "source_register": "літературна німецька",
            "narration": "третя особа, минулий час",
            "tone": "похмурий",
            "directives": "глоси сучасною українською",
        }
    )


@pytest.mark.integration
def test_summaries_use_lead_tail_and_cache(tmp_path: Path) -> None:
    hits = {"n": 0}
    prompts: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        payload = json.loads(req.content.decode("utf-8"))
        prompt = payload["messages"][0]["content"]
        prompts.append(prompt)
        if "epoch" in prompt:
            return _ok(_style_body())
        return _ok(_summary_body())

    repo = SqliteBookRepository(create_book_db(tmp_path / "book.db"))
    repo.save_structure(_structure())
    repo.replace_annotation("plot", Annotation(sentences=_sentences(), tokens=()))
    repo.replace_characters(
        "plot",
        (
            Character(
                id="c-oliver",
                book_id="book",
                canonical_name="Oliver",
                translation_uk="Олівер",
                gender=Gender.MALE,
            ),
        ),
    )
    written: list[str] = []
    builder = SmartStyleBuilder(
        client=OpenAiChatClient(
            retry=RetryPolicy(max_retries=0, min_seconds=0.01, max_seconds=0.02),
            log_dir=tmp_path / "logs",
            http=httpx.AsyncClient(
                transport=httpx.MockTransport(handler), trust_env=False
            ),
        ),
        config=StyleConfig(
            model="smart-model",
            base_url="http://127.0.0.1:8080/v1",
            timeout_seconds=5,
            slug="plot",
            summary_sentence_min=3,
            summary_sentence_max=5,
        ),
        cache=StepCache(tmp_path / "cache"),
    )
    ports = StylePorts(
        open_books=lambda _slug: repo,
        open_terms=lambda _slug: repo,
        summarizer=builder,
        composer=builder,
        write_markdown=lambda _slug, text: written.append(text),
    )
    report = build_style_card(ports, "plot", _CFG)
    assert report.summarized_count == 1
    assert report.style_card is True
    assert hits["n"] == 2
    assert all(_DUMP not in prompt for prompt in prompts)
    assert "Oliver satz 1." in prompts[0]
    assert "Oliver satz 20." in prompts[0]
    assert "Олівер" in prompts[0]
    summary = repo.get_structure("plot").chapters[0].summary_uk
    assert summary is not None
    assert summary.startswith("Олівер народжується.")
    assert "Шоста зайва" not in summary
    card = repo.get_style_card("plot")
    assert card is not None
    assert card.epoch == "XIX ст."
    assert written[0].startswith("# Style card")
    second = build_style_card(ports, "plot", _CFG)
    assert second.style_card is True
    assert hits["n"] == 2
    repo.save_structure(_structure())
    assert repo.get_structure("plot").chapters[0].summary_uk is None
    assert repo.get_style_card("plot") is None
