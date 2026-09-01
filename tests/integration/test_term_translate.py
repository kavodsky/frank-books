"""SMART term translation is cached; exonyms skip the LLM (roadmap 3.2)."""

from __future__ import annotations

import json

import httpx
import pytest

from frank.application.build_termbase import TranslatePorts, translate_termbase
from frank.domain.model.book import (
    Book,
    BookStatus,
    BookStructure,
    Chapter,
    Paragraph,
    ParagraphStatus,
)
from frank.domain.model.termbase import Exonym, Term, TermKind
from frank.infrastructure.llm.client import OpenAiChatClient, RetryPolicy
from frank.infrastructure.nlp.term_translator import (
    SmartTermTranslator,
    TranslateConfig,
)
from frank.infrastructure.persistence.cache import StepCache
from frank.infrastructure.persistence.repositories import SqliteBookRepository
from frank.infrastructure.persistence.tables import create_book_db


def _ok(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "choices": [{"message": {"role": "assistant", "content": content}}],
        },
    )


def _term(lemma: str, kind: TermKind) -> Term:
    return Term(
        id=f"book-{kind.value}-{lemma}",
        book_id="book",
        kind=kind,
        surface_forms=(lemma,),
        lemma=lemma,
    )


def _structure() -> BookStructure:
    return BookStructure(
        book=Book(
            id="book",
            slug="names",
            lang="de",
            title="T",
            author="",
            source_url="file.txt",
            license_note="",
            status=BookStatus.INGESTED,
        ),
        chapters=(Chapter(id="book-c1", book_id="book", index=1, title="K"),),
        paragraphs=(
            Paragraph(
                id="book-c1-p1",
                chapter_id="book-c1",
                passage_id=None,
                index=1,
                raw_text="Oliver sah Wien.",
                hash="h",
                status=ParagraphStatus.RAW,
            ),
        ),
    )


@pytest.mark.integration
def test_exonym_skips_llm_and_cache_avoids_second_call(tmp_path) -> None:
    hits = {"n": 0}
    body = json.dumps(
        {
            "items": [
                {"lemma": "Oliver", "translation_uk": "Олівер", "note": "ім'я"},
            ]
        }
    )

    def handler(req: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        payload = json.loads(req.content.decode("utf-8"))
        prompt = payload["messages"][0]["content"]
        assert "Oliver" in prompt
        assert "Wien" not in prompt
        return _ok(body)

    repo = SqliteBookRepository(create_book_db(tmp_path / "book.db"))
    repo.save_structure(_structure())
    repo.replace_terms(
        "names",
        (_term("Oliver", TermKind.PERSON), _term("Wien", TermKind.PLACE)),
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    translator = SmartTermTranslator(
        client=OpenAiChatClient(
            retry=RetryPolicy(max_retries=0, min_seconds=0.01, max_seconds=0.02),
            log_dir=tmp_path / "logs",
            http=http,
        ),
        config=TranslateConfig(
            model="smart-model",
            base_url="http://127.0.0.1:8080/v1",
            timeout_seconds=5,
            batch_size=20,
            slug="names",
        ),
        cache=StepCache(tmp_path / "cache"),
    )
    ports = TranslatePorts(
        open_books=lambda _slug: repo,
        open_terms=lambda _slug: repo,
        exonyms=lambda: (Exonym(lemma="wien", translation_uk="Відень"),),
        translator=translator,
    )
    first = translate_termbase(ports, "names")
    assert hits["n"] == 1
    assert first.exonym_count == 1
    assert first.llm_count == 1
    loaded = {item.lemma: item for item in repo.get_terms("names")}
    assert loaded["Wien"].translation_uk == "Відень"
    assert loaded["Oliver"].translation_uk == "Олівер"
    assert loaded["Oliver"].approved is False
    translator.propose((_term("Oliver", TermKind.PERSON),), "de")
    second = translate_termbase(ports, "names")
    assert hits["n"] == 1
    assert translator.llm_calls == 1
    assert second.translated_count == first.translated_count
