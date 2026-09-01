"""Persist sentence rows for an ingested book (roadmap 2.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from frank.application.annotate_chapter import (
    AnnotateConfig,
    AnnotatePorts,
    LemmaSupport,
    annotate_book,
)
from frank.application.ingest_book import IngestPorts, IngestRequest, ingest_book
from frank.domain.model.annotation import (
    GlossLists,
    GlossPlanConfig,
    GlossReason,
    Morphology,
    ParsedSentence,
    ParsedToken,
    SegmentationConfig,
)
from frank.domain.model.book import PassageGroupingConfig
from frank.infrastructure.nlp.prefixes import load_inventory
from frank.infrastructure.persistence.repositories import SqliteBookRepository
from frank.infrastructure.persistence.tables import create_book_db
from frank.infrastructure.sources.fetch import LocalFileFetcher
from frank.infrastructure.sources.raw_store import FilesystemRawStore

CHAPTERS = Path(__file__).resolve().parents[1] / "fixtures" / "chapters"
_SEG = SegmentationConfig(
    short_sentence_max_tokens=8,
    unit_min_tokens=3,
    unit_max_tokens=8,
    heavy_pp_min_tokens=6,
)
_GLOSS = GlossPlanConfig(
    frequency_top_n=1000,
    function_word_top_n=300,
    reminder_gap_sentences=400,
    reminder_max_occurrences=4,
    quota_chapter_start=6,
    quota_last_third=2,
    rare_morph_max_count=2,
)
_CONFIG = AnnotateConfig(
    segmentation=_SEG,
    gloss=_GLOSS,
    grouping=PassageGroupingConfig(
        min_chars=800, max_chars=1500, dialogue_max_chars=160
    ),
)


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

    def decide_reunions(self, pending):
        raise AssertionError(f"unexpected reunion arbitration: {len(pending)}")


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
        lemma_support_for=lambda lang: LemmaSupport(
            lexicon=UniversalLexicon(),
            inventory=load_inventory(lang),
        ),
        arbiter_for=lambda _lang: IdleArbiter(),
        gloss_lists_for=lambda _lang: GlossLists(),
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


def _unit_surfaces(repo: SqliteBookRepository, slug: str) -> tuple[str, ...]:
    tokens = repo.get_tokens(slug)
    found: list[str] = []
    for unit in repo.get_sense_units(slug):
        piece = [
            token.surface
            for token in tokens
            if token.sentence_id == unit.sentence_id
            and unit.start_index <= token.index <= unit.end_index
        ]
        found.append(" ".join(piece))
    return tuple(found)


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
    de = annotate_book(_annotate_ports(tmp_path), "de-ch", _CONFIG)
    hu = annotate_book(_annotate_ports(tmp_path), "hu-ch", _CONFIG)
    repo_de = SqliteBookRepository(create_book_db(tmp_path / "de-ch" / "book.db"))
    repo_hu = SqliteBookRepository(create_book_db(tmp_path / "hu-ch" / "book.db"))
    assert de.sentence_count == 3
    assert hu.sentence_count == 3
    assert de.token_count > 0 and hu.token_count > 0
    assert repo_de.get_sentences("de-ch")[0].text.startswith("Es war einmal")
    assert repo_hu.get_sentences("hu-ch")[0].text.startswith("Egyszer volt")
    assert all(token.lemma for token in repo_de.get_tokens("de-ch"))
    assert all(token.lemma for token in repo_hu.get_tokens("hu-ch"))
    assert de.sense_unit_count == de.sentence_count
    assert hu.sense_unit_count == hu.sentence_count
    assert len(repo_de.get_sense_units("de-ch")) == de.sense_unit_count
    assert _unit_surfaces(repo_de, "de-ch") == (
        "Es war einmal ein armer Mann .",
        "Er lebte am Waldrand .",
        "Am Morgen stand er auf .",
    )
    assert _unit_surfaces(repo_hu, "hu-ch") == (
        "Egyszer volt, hol nem volt .",
        "A királyfi elindult .",
        "Megérkezett a várba .",
    )
    plan_de = repo_de.get_gloss_plan("de-ch")
    assert de.gloss_count == 13
    assert hu.gloss_count > 0
    assert len(plan_de) == de.gloss_count
    assert all(item.gloss for item in plan_de)
    assert de.passage_count >= 1
    assert hu.passage_count >= 1
    assert repo_de.get_passages("de-ch")
    assert repo_hu.get_passages("hu-ch")
    assert all(item.passage_id for item in repo_de.get_structure("de-ch").paragraphs)


@pytest.mark.integration
def test_annotate_is_idempotent(tmp_path) -> None:
    ingest_book(
        _ingest_ports(tmp_path, "de"),
        _request(CHAPTERS / "de_sample.txt", "same", "de"),
    )
    ports = _annotate_ports(tmp_path)
    first = annotate_book(ports, "same", _CONFIG)
    repo = SqliteBookRepository(create_book_db(tmp_path / "same" / "book.db"))
    first_plan = repo.get_gloss_plan("same")
    first_passages = repo.get_passages("same")
    second = annotate_book(ports, "same", _CONFIG)
    assert first.sentence_count == second.sentence_count
    assert first.token_count == second.token_count
    assert first.sense_unit_count == second.sense_unit_count
    assert first.gloss_count == second.gloss_count
    assert first.passage_count == second.passage_count
    assert len(repo.get_sentences("same")) == first.sentence_count
    assert len(repo.get_tokens("same")) == first.token_count
    assert len(repo.get_sense_units("same")) == first.sense_unit_count
    assert repo.get_gloss_plan("same") == first_plan
    assert repo.get_passages("same") == first_passages


@pytest.mark.integration
def test_reingest_drops_sentence_rows(tmp_path) -> None:
    request = _request(CHAPTERS / "de_sample.txt", "wipe", "de")
    ingest_book(_ingest_ports(tmp_path, "de"), request)
    annotate_book(_annotate_ports(tmp_path), "wipe", _CONFIG)
    ingest_book(_ingest_ports(tmp_path, "de"), request)
    repo = SqliteBookRepository(create_book_db(tmp_path / "wipe" / "book.db"))
    assert repo.get_sentences("wipe") == ()
    assert repo.get_tokens("wipe") == ()
    assert repo.get_sense_units("wipe") == ()
    assert repo.get_gloss_plan("wipe") == ()
    assert repo.get_passages("wipe") == ()


@pytest.mark.integration
def test_oliver_twist_annotate_tokens_all_have_lemmas(tmp_path) -> None:
    ingest_book(
        _ingest_ports(tmp_path, "de"),
        _request(CHAPTERS / "oliver_twist_de.txt", "oliver-de", "de"),
    )
    report = annotate_book(_annotate_ports(tmp_path), "oliver-de", _CONFIG)
    repo = SqliteBookRepository(create_book_db(tmp_path / "oliver-de" / "book.db"))
    tokens = repo.get_tokens("oliver-de")
    structure = repo.get_structure("oliver-de")
    assert report.token_count == len(tokens)
    assert tokens
    assert all(token.lemma for token in tokens)
    assert report.passage_count == len(structure.passages) >= 1
    passage_chapter = {item.id: item.chapter_id for item in structure.passages}
    for paragraph in structure.paragraphs:
        assert paragraph.passage_id is not None
        assert passage_chapter[paragraph.passage_id] == paragraph.chapter_id


class _SeparableAnalyzer:
    def analyze(self, _text: str) -> tuple[ParsedSentence, ...]:
        tokens = (
            ParsedToken(
                index=1,
                surface="Er",
                lemma="er",
                upos="PRON",
                morph=Morphology(),
                dep="sb",
                head_index=2,
            ),
            ParsedToken(
                index=2,
                surface="ruft",
                lemma="rufen",
                upos="VERB",
                morph=Morphology(),
                dep="ROOT",
                head_index=0,
            ),
            ParsedToken(
                index=3,
                surface="an",
                lemma="an",
                upos="PART",
                morph=Morphology(),
                dep="svp",
                head_index=2,
            ),
            ParsedToken(
                index=4,
                surface=".",
                lemma=".",
                upos="PUNCT",
                morph=Morphology(),
                dep="punct",
                head_index=2,
            ),
        )
        return (ParsedSentence(index=1, text="Er ruft an.", tokens=tokens),)

    def second_lemma(self, surface: str, upos: str) -> str:
        _ = upos
        lemmas = {"Er": "er", "ruft": "rufen", "an": "an", ".": "."}
        return lemmas.get(surface, surface.casefold())


@pytest.mark.integration
def test_annotate_persists_reunited_separable_verb(tmp_path) -> None:
    src = tmp_path / "anrufen.txt"
    src.write_text("Er ruft an.\n", encoding="utf-8")
    ingest_book(_ingest_ports(tmp_path, "de"), _request(src, "anrufen", "de"))
    ports = AnnotatePorts(
        open_books=lambda slug: SqliteBookRepository(
            create_book_db(tmp_path / slug / "book.db")
        ),
        analyzer_for=lambda _lang: _SeparableAnalyzer(),
        lemma_support_for=lambda lang: LemmaSupport(
            lexicon=UniversalLexicon(),
            inventory=load_inventory(lang),
        ),
        arbiter_for=lambda _lang: IdleArbiter(),
        gloss_lists_for=lambda _lang: GlossLists(),
    )
    report = annotate_book(ports, "anrufen", _CONFIG)
    repo = SqliteBookRepository(create_book_db(tmp_path / "anrufen" / "book.db"))
    tokens = repo.get_tokens("anrufen")
    particles = repo.get_particles("anrufen")
    verb = next(token for token in tokens if token.surface == "ruft")
    assert report.particle_count == 1
    assert verb.reunited_lemma == "anrufen"
    assert particles[0].reunited_lemma == "anrufen"
    assert particles[0].verb_token_id == verb.id
    plan = {item.token_id: item for item in repo.get_gloss_plan("anrufen")}
    assert plan[verb.id].reason is GlossReason.MORPH_TRAP
    assert report.gloss_count == len(plan)
