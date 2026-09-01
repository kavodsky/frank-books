"""Build the Character registry from PERSON evidence (roadmap 3.3)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from frank.domain.model.termbase import (
    Character,
    CharacterEvidenceConfig,
    Gender,
)
from frank.domain.ports.linguistics import CharacterMapper
from frank.domain.ports.repositories import BookRepository, TermbaseRepository
from frank.domain.services.character_evidence import (
    CharacterEvidenceRequest,
    collect_chapter_evidence,
)
from frank.domain.services.character_merge import merge_characters


@dataclass(frozen=True)
class CharacterPorts:
    open_books: Callable[[str], BookRepository]
    open_terms: Callable[[str], TermbaseRepository]
    gender_cues: Callable[[str], frozenset[str]]
    mapper: CharacterMapper


class CharacterReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    character_count: int
    female_count: int
    male_count: int
    unknown_gender_count: int
    chapter_passes: int


def build_character_registry(
    ports: CharacterPorts, slug: str, config: CharacterEvidenceConfig
) -> CharacterReport:
    books = ports.open_books(slug)
    terms_repo = ports.open_terms(slug)
    structure = books.get_structure(slug)
    terms = terms_repo.get_terms(slug)
    evidence = collect_chapter_evidence(
        CharacterEvidenceRequest(
            structure=structure,
            sentences=books.get_sentences(slug),
            tokens=books.get_tokens(slug),
            persons=terms,
            gender_cues=ports.gender_cues(structure.book.lang),
            config=config,
        )
    )
    drafts = tuple(
        draft
        for chapter in evidence
        for draft in ports.mapper.map_chapter(chapter, structure.book.lang)
    )
    characters = merge_characters(structure.book.id, drafts, terms)
    terms_repo.replace_characters(slug, characters)
    return _report(slug, characters, len(evidence))


def render_character_report(report: CharacterReport) -> str:
    return (
        f"characters: {report.character_count}\n"
        f"female: {report.female_count}\n"
        f"male: {report.male_count}\n"
        f"unknown_gender: {report.unknown_gender_count}\n"
        f"chapter_passes: {report.chapter_passes}\n"
    )


def _report(
    slug: str, characters: tuple[Character, ...], chapter_passes: int
) -> CharacterReport:
    genders = [item.gender for item in characters]
    return CharacterReport(
        slug=slug,
        character_count=len(characters),
        female_count=genders.count(Gender.FEMALE),
        male_count=genders.count(Gender.MALE),
        unknown_gender_count=genders.count(Gender.UNKNOWN),
        chapter_passes=chapter_passes,
    )
