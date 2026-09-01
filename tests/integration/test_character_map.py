"""SMART character map uses PERSON evidence, not chapter text (roadmap 3.3)."""

from __future__ import annotations

import json

import httpx
import pytest

from frank.application.build_characters import (
    CharacterPorts,
    build_character_registry,
)
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
    Character,
    CharacterEvidenceConfig,
    Gender,
    Term,
    TermKind,
)
from frank.infrastructure.llm.client import OpenAiChatClient, RetryPolicy
from frank.infrastructure.nlp.character_mapper import MapConfig, SmartCharacterMapper
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


def _structure() -> BookStructure:
    return BookStructure(
        book=Book(
            id="book",
            slug="cast",
            lang="de",
            title="T",
            author="",
            source_url="file.txt",
            license_note="",
            status=BookStatus.INGESTED,
        ),
        chapters=(
            Chapter(id="book-c1", book_id="book", index=1, title="K1"),
            Chapter(id="book-c2", book_id="book", index=2, title="K2"),
        ),
        paragraphs=(
            Paragraph(
                id="book-c1-p1",
                chapter_id="book-c1",
                passage_id=None,
                index=1,
                raw_text="CHAPTER_DUMP Frau Oliver sprach. Oliver ging. Oliver rief.",
                hash="h1",
                status=ParagraphStatus.RAW,
            ),
            Paragraph(
                id="book-c2-p1",
                chapter_id="book-c2",
                passage_id=None,
                index=1,
                raw_text="Oliver schlief.",
                hash="h2",
                status=ParagraphStatus.RAW,
            ),
        ),
    )


def _sentences() -> tuple[Sentence, ...]:
    return (
        Sentence(
            id="s1", paragraph_id="book-c1-p1", index=1, text="Frau Oliver sprach."
        ),
        Sentence(id="s2", paragraph_id="book-c1-p1", index=2, text="Oliver ging."),
        Sentence(id="s3", paragraph_id="book-c1-p1", index=3, text="Oliver rief."),
        Sentence(id="s4", paragraph_id="book-c2-p1", index=1, text="Oliver schlief."),
    )


def _token(sentence_id: str, index: int, surface: str, lemma: str) -> Token:
    return Token(
        id=f"{sentence_id}-t{index}",
        sentence_id=sentence_id,
        index=index,
        surface=surface,
        lemma=lemma,
        upos="PROPN",
        morph=Morphology(),
        ent_type="PER",
    )


def _tokens() -> tuple[Token, ...]:
    return (
        _token("s1", 1, "Frau", "frau"),
        _token("s1", 2, "Oliver", "oliver"),
        _token("s2", 1, "Oliver", "oliver"),
        _token("s3", 1, "Oliver", "oliver"),
        _token("s4", 1, "Oliver", "oliver"),
    )


def _person() -> Term:
    return Term(
        id="book-PERSON-oliver",
        book_id="book",
        kind=TermKind.PERSON,
        surface_forms=("Oliver",),
        lemma="oliver",
        translation_uk="Олівер",
    )


def _body() -> str:
    return json.dumps(
        {
            "items": [
                {
                    "lemma": "oliver",
                    "canonical_name": "Oliver",
                    "translation_uk": "Олівер",
                    "gender": "male",
                    "aliases": [],
                    "role_note": "хлопець",
                }
            ]
        }
    )


@pytest.mark.integration
def test_map_sends_evidence_sentences_and_cache_skips_rerun(tmp_path) -> None:
    hits = {"n": 0}
    prompts: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        payload = json.loads(req.content.decode("utf-8"))
        prompt = payload["messages"][0]["content"]
        prompts.append(prompt)
        return _ok(_body())

    repo = SqliteBookRepository(create_book_db(tmp_path / "book.db"))
    repo.save_structure(_structure())
    repo.replace_annotation(
        "cast", Annotation(sentences=_sentences(), tokens=_tokens())
    )
    repo.replace_terms("cast", (_person(),))
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    mapper = SmartCharacterMapper(
        client=OpenAiChatClient(
            retry=RetryPolicy(max_retries=0, min_seconds=0.01, max_seconds=0.02),
            log_dir=tmp_path / "logs",
            http=http,
        ),
        config=MapConfig(
            model="smart-model",
            base_url="http://127.0.0.1:8080/v1",
            timeout_seconds=5,
            batch_size=10,
            slug="cast",
        ),
        cache=StepCache(tmp_path / "cache"),
    )
    ports = CharacterPorts(
        open_books=lambda _slug: repo,
        open_terms=lambda _slug: repo,
        gender_cues=lambda _lang: frozenset({"frau"}),
        mapper=mapper,
    )
    config = CharacterEvidenceConfig(evidence_sentences_per_person=2)
    first = build_character_registry(ports, "cast", config)
    assert hits["n"] == 2
    assert "Frau Oliver sprach." in prompts[0]
    assert "Oliver ging." in prompts[0]
    assert "Oliver rief." not in prompts[0]
    assert "CHAPTER_DUMP" not in prompts[0]
    assert "Oliver schlief." in prompts[1]
    loaded = repo.get_characters("cast")
    assert first.character_count == 1
    assert loaded[0].gender is Gender.MALE
    assert loaded[0].canonical_name == "Oliver"
    assert loaded[0].translation_uk == "Олівер"
    second = build_character_registry(ports, "cast", config)
    assert hits["n"] == 2
    assert mapper.llm_calls == 2
    assert second.character_count == first.character_count


@pytest.mark.integration
def test_reingest_drops_characters(tmp_path) -> None:
    repo = SqliteBookRepository(create_book_db(tmp_path / "book.db"))
    repo.save_structure(_structure())
    repo.replace_annotation(
        "cast", Annotation(sentences=_sentences(), tokens=_tokens())
    )
    repo.replace_terms("cast", (_person(),))
    repo.replace_characters(
        "cast",
        (
            Character(
                id="book-char-oliver",
                book_id="book",
                canonical_name="Oliver",
                translation_uk="Олівер",
                gender=Gender.MALE,
            ),
        ),
    )
    repo.save_structure(_structure())
    assert repo.get_characters("cast") == ()
