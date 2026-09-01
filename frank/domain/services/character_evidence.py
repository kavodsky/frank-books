"""Select PERSON evidence sentences per chapter (roadmap 3.3)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from frank.domain.model.annotation import Token
from frank.domain.model.book import BookStructure, Paragraph, Sentence
from frank.domain.model.termbase import (
    ChapterEvidence,
    CharacterEvidenceConfig,
    PersonEvidence,
    Term,
    TermKind,
)


@dataclass(frozen=True)
class CharacterEvidenceRequest:
    structure: BookStructure
    sentences: tuple[Sentence, ...]
    tokens: tuple[Token, ...]
    persons: tuple[Term, ...]
    gender_cues: frozenset[str]
    config: CharacterEvidenceConfig


def collect_chapter_evidence(
    request: CharacterEvidenceRequest,
) -> tuple[ChapterEvidence, ...]:
    """PERSON lemmas plus a few sentences per chapter; never the chapter text.

    German: a sentence with ``Frau`` outranks a bare mention of ``Oliver``.
    Hungarian: ``Sándor úr`` outranks a mention without ``úr`` / ``lány``.
    """
    persons = tuple(item for item in request.persons if item.kind is TermKind.PERSON)
    if not persons:
        return ()
    paragraphs = {item.id: item for item in request.structure.paragraphs}
    tokens_by_sentence = _group_tokens(request.tokens)
    found: list[ChapterEvidence] = []
    for chapter in request.structure.chapters:
        sentences = _chapter_sentences(chapter.id, request.sentences, paragraphs)
        piece = _chapter_persons(persons, sentences, tokens_by_sentence, request)
        if piece:
            found.append(ChapterEvidence(chapter_id=chapter.id, persons=piece))
    return tuple(found)


def _chapter_persons(
    persons: tuple[Term, ...],
    sentences: tuple[Sentence, ...],
    tokens_by_sentence: dict[str, tuple[Token, ...]],
    request: CharacterEvidenceRequest,
) -> tuple[PersonEvidence, ...]:
    found: list[PersonEvidence] = []
    for person in persons:
        picked = _pick_sentences(person, sentences, tokens_by_sentence, request)
        if not picked:
            continue
        found.append(
            PersonEvidence(
                lemma=person.lemma,
                translation_uk=person.translation_uk,
                surface_forms=person.surface_forms,
                sentences=picked,
            )
        )
    return tuple(found)


def _pick_sentences(
    person: Term,
    sentences: tuple[Sentence, ...],
    tokens_by_sentence: dict[str, tuple[Token, ...]],
    request: CharacterEvidenceRequest,
) -> tuple[str, ...]:
    ranked = _rank_mentions(person, sentences, tokens_by_sentence, request.gender_cues)
    limit = request.config.evidence_sentences_per_person
    return tuple(item.text for item in ranked[:limit])


def _rank_mentions(
    person: Term,
    sentences: tuple[Sentence, ...],
    tokens_by_sentence: dict[str, tuple[Token, ...]],
    cues: frozenset[str],
) -> tuple[Sentence, ...]:
    hits: list[tuple[int, int, Sentence]] = []
    for index, sentence in enumerate(sentences):
        tokens = tokens_by_sentence.get(sentence.id, ())
        if not _mentions_person(tokens, person):
            continue
        cue = 0 if _has_gender_cue(tokens, cues) else 1
        hits.append((cue, index, sentence))
    hits.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in hits)


def _mentions_person(tokens: Sequence[Token], person: Term) -> bool:
    lemma = person.lemma.casefold()
    surfaces = {item.casefold() for item in person.surface_forms}
    if any(_token_hits(token, lemma, surfaces) for token in tokens):
        return True
    token_lemmas = tuple(token.lemma.casefold() for token in tokens)
    token_surfaces = tuple(token.surface.casefold() for token in tokens)
    if _window_match(token_lemmas, tuple(lemma.split())):
        return True
    return any(
        _window_match(token_surfaces, tuple(form.casefold().split()))
        for form in person.surface_forms
        if " " in form
    )


def _token_hits(token: Token, lemma: str, surfaces: set[str]) -> bool:
    return token.lemma.casefold() == lemma or token.surface.casefold() in surfaces


def _window_match(values: tuple[str, ...], parts: tuple[str, ...]) -> bool:
    if len(parts) < 2:
        return False
    width = len(parts)
    for index in range(len(values) - width + 1):
        if values[index : index + width] == parts:
            return True
    return False


def _has_gender_cue(tokens: Sequence[Token], cues: frozenset[str]) -> bool:
    return any(
        token.lemma.casefold() in cues or token.surface.casefold() in cues
        for token in tokens
    )


def _chapter_sentences(
    chapter_id: str,
    sentences: tuple[Sentence, ...],
    paragraphs: dict[str, Paragraph],
) -> tuple[Sentence, ...]:
    return tuple(
        item
        for item in sentences
        if paragraphs[item.paragraph_id].chapter_id == chapter_id
    )


def _group_tokens(tokens: tuple[Token, ...]) -> dict[str, tuple[Token, ...]]:
    grouped: dict[str, list[Token]] = {}
    for token in tokens:
        grouped.setdefault(token.sentence_id, []).append(token)
    return {key: tuple(value) for key, value in grouped.items()}
