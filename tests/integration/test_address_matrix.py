"""SMART address resolve uses pair evidence, not chapter text (roadmap 3.4)."""

from __future__ import annotations

import json

import httpx
import pytest

from frank.application.build_address import AddressPorts, build_address_matrix
from frank.domain.model.annotation import Annotation, Morphology, Token
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
    AddressCues,
    AddressMatrixConfig,
    Character,
    Gender,
    TvForm,
)
from frank.infrastructure.llm.client import OpenAiChatClient, RetryPolicy
from frank.infrastructure.nlp.address_resolver import (
    ResolveConfig,
    SmartAddressResolver,
)
from frank.infrastructure.persistence.cache import StepCache
from frank.infrastructure.persistence.repositories import SqliteBookRepository
from frank.infrastructure.persistence.tables import create_book_db

_CUES = AddressCues(
    t_lemmas=("du",),
    v_lemmas=("sie",),
    v_surfaces=("Sie",),
    speech_lemmas=("sagen",),
)


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
            slug="tv",
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
                id="book-c1-p0",
                chapter_id="book-c1",
                passage_id=None,
                index=1,
                raw_text="CHAPTER_DUMP narrative that must not reach SMART.",
                hash="h0",
                status=ParagraphStatus.RAW,
            ),
            Paragraph(
                id="book-c1-p1",
                chapter_id="book-c1",
                passage_id=None,
                index=2,
                raw_text="«Oliver, komm.» sagte Bumble.",
                hash="h1",
                status=ParagraphStatus.RAW,
            ),
        ),
    )


def _token(index: int, surface: str, lemma: str, upos: str) -> Token:
    return Token(
        id=f"s1-t{index}",
        sentence_id="s1",
        index=index,
        surface=surface,
        lemma=lemma,
        upos=upos,
        morph=Morphology(),
    )


@pytest.mark.integration
def test_unresolved_pair_goes_to_smart_and_cache(tmp_path) -> None:
    hits = {"n": 0}
    prompts: list[str] = []
    body = json.dumps(
        {
            "items": [
                {
                    "speaker_id": "book-char-bumble",
                    "addressee_id": "book-char-oliver",
                    "tv_form": "T",
                }
            ]
        }
    )

    def handler(req: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        payload = json.loads(req.content.decode("utf-8"))
        prompts.append(payload["messages"][0]["content"])
        return _ok(body)

    repo = SqliteBookRepository(create_book_db(tmp_path / "book.db"))
    repo.save_structure(_structure())
    repo.replace_annotation(
        "tv",
        Annotation(
            sentences=(
                Sentence(
                    id="s1",
                    paragraph_id="book-c1-p1",
                    index=1,
                    text="«Oliver, komm.» sagte Bumble.",
                ),
            ),
            tokens=(
                _token(0, "Oliver", "Oliver", "PROPN"),
                _token(1, "komm", "kommen", "VERB"),
                _token(2, "sagte", "sagen", "VERB"),
                _token(3, "Bumble", "Bumble", "PROPN"),
            ),
        ),
    )
    repo.replace_characters(
        "tv",
        (
            Character(
                id="book-char-bumble",
                book_id="book",
                canonical_name="Bumble",
                translation_uk="Бамбл",
                gender=Gender.MALE,
            ),
            Character(
                id="book-char-oliver",
                book_id="book",
                canonical_name="Oliver",
                translation_uk="Олівер",
                gender=Gender.MALE,
            ),
        ),
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    resolver = SmartAddressResolver(
        client=OpenAiChatClient(
            retry=RetryPolicy(max_retries=0, min_seconds=0.01, max_seconds=0.02),
            log_dir=tmp_path / "logs",
            http=http,
        ),
        config=ResolveConfig(
            model="smart-model",
            base_url="http://127.0.0.1:8080/v1",
            timeout_seconds=5,
            batch_size=10,
            slug="tv",
        ),
        cache=StepCache(tmp_path / "cache"),
    )
    ports = AddressPorts(
        open_books=lambda _slug: repo,
        open_terms=lambda _slug: repo,
        cues_for=lambda _lang: _CUES,
        resolver=resolver,
    )
    config = AddressMatrixConfig(evidence_sentences_per_pair=3)
    first = build_address_matrix(ports, "tv", config)
    assert hits["n"] == 1
    assert "Oliver, komm" in prompts[0]
    assert "CHAPTER_DUMP" not in prompts[0]
    assert first.t_count == 1
    assert first.smart_count == 1
    loaded = repo.get_address_pairs("tv")
    assert loaded[0].tv_form is TvForm.T
    second = build_address_matrix(ports, "tv", config)
    assert hits["n"] == 1
    assert resolver.llm_calls == 1
    assert second.pair_count == first.pair_count
