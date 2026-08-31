"""Persist sentence rows for an ingested book (roadmap 2.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from frank.application.annotate_chapter import AnnotatePorts, annotate_book
from frank.application.ingest_book import IngestPorts, IngestRequest, ingest_book
from frank.domain.model.annotation import Morphology, ParsedSentence, ParsedToken
from frank.infrastructure.persistence.repositories import SqliteBookRepository
from frank.infrastructure.persistence.tables import create_book_db
from frank.infrastructure.sources.fetch import LocalFileFetcher
from frank.infrastructure.sources.raw_store import FilesystemRawStore

CHAPTERS = Path(__file__).resolve().parents[1] / "fixtures" / "chapters"


class PeriodAnalyzer:
    def analyze(self, text: str) -> tuple[ParsedSentence, ...]:
        parts = [part.strip() for part in text.split(".")]
        kept = tuple(f"{part}." for part in parts if part)
        return tuple(
            ParsedSentence(index=index, text=item, tokens=_word_tokens(item))
            for index, item in enumerate(kept, start=1)
        )

    def second_lemma(self, surface: str, upos: str) -> str:
        if upos == "PUNCT":
            return surface
        return surface.casefold()


def _word_tokens(text: str) -> tuple[ParsedToken, ...]:
    body = text[:-1] if text.endswith(".") else text
    words = [word for word in body.split() if word]
    tokens = [
        ParsedToken(
            index=index,
            surface=word,
            lemma=word.casefold(),
            upos="X",
            morph=Morphology(),
        )
        for index, word in enumerate(words, start=1)
    ]
    if text.endswith("."):
        tokens.append(
            ParsedToken(
                index=len(tokens) + 1,
                surface=".",
                lemma=".",
                upos="PUNCT",
                morph=Morphology(),
            )
        )
    return tuple(tokens)


class UniversalLexicon:
    def contains(self, _form: str) -> bool:
        return True


class IdleArbiter:
    def decide(self, disputed):
        raise AssertionError(f"unexpected lemma arbitration: {len(disputed)}")


def _ingest_ports(tmp_path: Path, lang: str) -> IngestPorts:
    return IngestPorts(
        fetcher=LocalFileFetcher(lang),
        raw_store=FilesystemRawStore(tmp_path),
        open_books=lambda slug: SqliteBookRepository(
            create_book_db(tmp_path / slug / "book.db")
        ),
        books_dir=tmp_path,
    )


def _annotate_ports(tmp_path: Path) -> AnnotatePorts:
    return AnnotatePorts(
        open_books=lambda slug: SqliteBookRepository(
            create_book_db(tmp_path / slug / "book.db")
        ),
        analyzer_for=lambda _lang: PeriodAnalyzer(),
        lexicon_for=lambda _lang: UniversalLexicon(),
        arbiter_for=lambda _lang: IdleArbiter(),
    )


def _request(path: Path, slug: str, lang: str) -> IngestRequest:
    return IngestRequest(
        location=str(path),
        slug=slug,
        lang=lang,
        header_max_chars=60,
        header_min_repeats=3,
        max_paragraph_chars=1500,
        foreign_script_ratio=0.08,
    )


@pytest.mark.integration
def test_annotate_persists_german_and_hungarian_sentences(tmp_path) -> None:
    ingest_book(
        _ingest_ports(tmp_path, "de"),
        _request(CHAPTERS / "de_sample.txt", "de-ch", "de"),
    )
    ingest_book(
        _ingest_ports(tmp_path, "hu"),
        _request(CHAPTERS / "hu_sample.txt", "hu-ch", "hu"),
    )
    de = annotate_book(_annotate_ports(tmp_path), "de-ch")
    hu = annotate_book(_annotate_ports(tmp_path), "hu-ch")
    repo_de = SqliteBookRepository(create_book_db(tmp_path / "de-ch" / "book.db"))
    repo_hu = SqliteBookRepository(create_book_db(tmp_path / "hu-ch" / "book.db"))
    assert de.sentence_count == 3
    assert hu.sentence_count == 3
    assert de.token_count > 0 and hu.token_count > 0
    assert repo_de.get_sentences("de-ch")[0].text.startswith("Es war einmal")
    assert repo_hu.get_sentences("hu-ch")[0].text.startswith("Egyszer volt")
    assert all(token.lemma for token in repo_de.get_tokens("de-ch"))
    assert all(token.lemma for token in repo_hu.get_tokens("hu-ch"))


@pytest.mark.integration
def test_annotate_is_idempotent(tmp_path) -> None:
    ingest_book(
        _ingest_ports(tmp_path, "de"),
        _request(CHAPTERS / "de_sample.txt", "same", "de"),
    )
    ports = _annotate_ports(tmp_path)
    first = annotate_book(ports, "same")
    second = annotate_book(ports, "same")
    repo = SqliteBookRepository(create_book_db(tmp_path / "same" / "book.db"))
    assert first.sentence_count == second.sentence_count
    assert first.token_count == second.token_count
    assert len(repo.get_sentences("same")) == first.sentence_count
    assert len(repo.get_tokens("same")) == first.token_count


@pytest.mark.integration
def test_reingest_drops_sentence_rows(tmp_path) -> None:
    request = _request(CHAPTERS / "de_sample.txt", "wipe", "de")
    ingest_book(_ingest_ports(tmp_path, "de"), request)
    annotate_book(_annotate_ports(tmp_path), "wipe")
    ingest_book(_ingest_ports(tmp_path, "de"), request)
    repo = SqliteBookRepository(create_book_db(tmp_path / "wipe" / "book.db"))
    assert repo.get_sentences("wipe") == ()
    assert repo.get_tokens("wipe") == ()


@pytest.mark.integration
def test_oliver_twist_annotate_tokens_all_have_lemmas(tmp_path) -> None:
    ingest_book(
        _ingest_ports(tmp_path, "de"),
        _request(CHAPTERS / "oliver_twist_de.txt", "oliver-de", "de"),
    )
    report = annotate_book(_annotate_ports(tmp_path), "oliver-de")
    repo = SqliteBookRepository(create_book_db(tmp_path / "oliver-de" / "book.db"))
    tokens = repo.get_tokens("oliver-de")
    assert report.token_count == len(tokens)
    assert tokens
    assert all(token.lemma for token in tokens)
