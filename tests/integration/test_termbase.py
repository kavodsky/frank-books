"""Persist NER Term candidates (roadmap 3.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from frank.application.annotate_chapter import (
    AnnotateConfig,
    AnnotatePorts,
    LemmaSupport,
    annotate_book,
)
from frank.application.build_termbase import TermbasePorts, build_termbase
from frank.application.ingest_book import IngestPorts, IngestRequest, ingest_book
from frank.domain.model.annotation import (
    GlossLists,
    GlossPlanConfig,
    Morphology,
    ParsedSentence,
    ParsedToken,
    SegmentationConfig,
)
from frank.domain.model.book import PassageGroupingConfig
from frank.domain.model.termbase import TermCollectConfig, TermKind
from frank.infrastructure.nlp.prefixes import load_inventory
from frank.infrastructure.persistence.repositories import SqliteBookRepository
from frank.infrastructure.persistence.tables import create_book_db
from frank.infrastructure.sources.fetch import LocalFileFetcher
from frank.infrastructure.sources.raw_store import FilesystemRawStore

_CONFIG = AnnotateConfig(
    segmentation=SegmentationConfig(
        short_sentence_max_tokens=8,
        unit_min_tokens=3,
        unit_max_tokens=8,
        heavy_pp_min_tokens=6,
    ),
    gloss=GlossPlanConfig(
        frequency_top_n=1000,
        function_word_top_n=300,
        reminder_gap_sentences=400,
        reminder_max_occurrences=4,
        quota_chapter_start=6,
        quota_last_third=2,
        rare_morph_max_count=2,
    ),
    grouping=PassageGroupingConfig(
        min_chars=800, max_chars=1500, dialogue_max_chars=160
    ),
)
_TERMS = TermCollectConfig(
    entity_min_occurrences=3,
    unknown_lemma_min_count=99,
    idiom_min_occurrences=1,
    merge_max_edit_distance=2,
    merge_min_stem_chars=4,
)
_ENT = {"Oliver": "PER", "Budapest": "LOC", "Budapesten": "LOC"}


class NamedAnalyzer:
    def analyze(self, text: str) -> tuple[ParsedSentence, ...]:
        parts = [part.strip() for part in text.split(".")]
        kept = tuple(f"{part}." for part in parts if part)
        return tuple(
            ParsedSentence(index=index, text=item, tokens=_tokens(item))
            for index, item in enumerate(kept, start=1)
        )

    def second_lemma(self, surface: str, upos: str) -> str:
        _ = upos
        return surface.casefold()


class UniversalLexicon:
    def contains(self, _form: str) -> bool:
        return True


class IdleArbiter:
    def decide(self, disputed):
        raise AssertionError(f"unexpected lemma arbitration: {len(disputed)}")

    def decide_reunions(self, pending):
        raise AssertionError(f"unexpected reunion arbitration: {len(pending)}")


def _tokens(text: str) -> tuple[ParsedToken, ...]:
    body = text[:-1] if text.endswith(".") else text
    words = [word for word in body.split() if word]
    found = [
        ParsedToken(
            index=index,
            surface=word,
            lemma=word.casefold(),
            upos="PROPN" if word in _ENT else "X",
            morph=Morphology(),
            ent_type=_ENT.get(word, ""),
        )
        for index, word in enumerate(words, start=1)
    ]
    if text.endswith("."):
        found.append(
            ParsedToken(
                index=len(found) + 1,
                surface=".",
                lemma=".",
                upos="PUNCT",
                morph=Morphology(),
            )
        )
    return tuple(found)


def _ingest_ports(tmp_path: Path) -> IngestPorts:
    return IngestPorts(
        fetcher=LocalFileFetcher("de"),
        raw_store=FilesystemRawStore(tmp_path),
        open_books=lambda slug: SqliteBookRepository(
            create_book_db(tmp_path / slug / "book.db")
        ),
        books_dir=tmp_path,
    )


def _open(tmp_path: Path, slug: str) -> SqliteBookRepository:
    return SqliteBookRepository(create_book_db(tmp_path / slug / "book.db"))


def _annotate_ports(tmp_path: Path) -> AnnotatePorts:
    return AnnotatePorts(
        open_books=lambda slug: _open(tmp_path, slug),
        analyzer_for=lambda _lang: NamedAnalyzer(),
        lemma_support_for=lambda lang: LemmaSupport(
            lexicon=UniversalLexicon(),
            inventory=load_inventory(lang),
        ),
        arbiter_for=lambda _lang: IdleArbiter(),
        gloss_lists_for=lambda _lang: GlossLists(),
    )


def _term_ports(tmp_path: Path) -> TermbasePorts:
    return TermbasePorts(
        open_books=lambda slug: _open(tmp_path, slug),
        open_terms=lambda slug: _open(tmp_path, slug),
        lexicon_for=lambda _lang: UniversalLexicon(),
        lists_for=lambda _lang: GlossLists(),
    )


def _request(path: Path) -> IngestRequest:
    return IngestRequest(
        location=str(path),
        slug="names",
        lang="de",
        header_max_chars=60,
        header_min_repeats=3,
        max_paragraph_chars=1500,
        foreign_script_ratio=0.08,
    )


@pytest.mark.integration
def test_termbase_covers_person_and_place_at_min_count(tmp_path) -> None:
    src = tmp_path / "names.txt"
    src.write_text(
        "Oliver ging nach Budapest.\n\n"
        "Oliver sah Budapesten.\n\n"
        "Oliver rief Budapest.\n",
        encoding="utf-8",
    )
    ingest_book(_ingest_ports(tmp_path), _request(src))
    annotate_book(_annotate_ports(tmp_path), "names", _CONFIG)
    report = build_termbase(_term_ports(tmp_path), "names", _TERMS)
    repo = _open(tmp_path, "names")
    terms = repo.get_terms("names")
    kinds = {item.kind: item for item in terms}
    assert any(token.ent_type == "PER" for token in repo.get_tokens("names"))
    assert report.person_count == 1
    assert report.place_count == 1
    assert kinds[TermKind.PERSON].lemma == "oliver"
    assert kinds[TermKind.PLACE].lemma == "budapest"
    assert "Budapesten" in kinds[TermKind.PLACE].surface_forms
    assert all(not item.approved for item in terms)
    assert all(item.translation_uk == "" for item in terms)
    again = build_termbase(_term_ports(tmp_path), "names", _TERMS)
    assert again.term_count == report.term_count
    assert repo.get_terms("names") == terms


@pytest.mark.integration
def test_reingest_drops_terms(tmp_path) -> None:
    src = tmp_path / "names.txt"
    src.write_text(
        "Oliver ging nach Budapest.\n\nOliver sah Budapest.\n\nOliver rief Budapest.\n",
        encoding="utf-8",
    )
    request = _request(src)
    ingest_book(_ingest_ports(tmp_path), request)
    annotate_book(_annotate_ports(tmp_path), "names", _CONFIG)
    build_termbase(_term_ports(tmp_path), "names", _TERMS)
    ingest_book(_ingest_ports(tmp_path), request)
    assert _open(tmp_path, "names").get_terms("names") == ()
