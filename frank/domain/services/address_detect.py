"""Detect T/V address observations in dialogue (roadmap 3.4). Heuristics only."""

from __future__ import annotations

from dataclasses import dataclass

from frank.domain.model.annotation import Token
from frank.domain.model.book import BookStructure, Paragraph, Sentence
from frank.domain.model.termbase import (
    AddressCues,
    AddressObservation,
    Character,
    TvForm,
)

_SPEECH_OPENERS = ("—", "–", "-", "«", "»", "„", "“", '"', "'")
_SKIP_NAMES = frozenset({"mrs", "mr", "herr", "frau", "úr"})


@dataclass(frozen=True)
class AddressDetectRequest:
    structure: BookStructure
    sentences: tuple[Sentence, ...]
    tokens: tuple[Token, ...]
    characters: tuple[Character, ...]
    cues: AddressCues


def collect_address_observations(
    request: AddressDetectRequest,
) -> tuple[AddressObservation, ...]:
    """T/V in dialogue lines with same-sentence speaker/addressee guesses; no LLM.

    German: ``Willst du mit mir gehen, Oliver? redete ihn Mr. Bumble an`` → T
    Bumble→Oliver. Hungarian: ``Te vagy az, Sándor — mondta Gábor`` → T Gábor→Sándor.
    Narrative ``Sie gingen`` is ignored: only speech-opener paragraphs are scanned.
    """
    if not request.characters:
        return ()
    paragraphs = {item.id: item for item in request.structure.paragraphs}
    tokens_by_sentence = _group_tokens(request.tokens)
    names = _name_index(request.characters)
    found: list[AddressObservation] = []
    for sentence in request.sentences:
        paragraph = paragraphs.get(sentence.paragraph_id)
        if paragraph is None or not _is_dialogue(paragraph):
            continue
        tokens = tokens_by_sentence.get(sentence.id, ())
        form = _tv_form(tokens, request.cues)
        speaker, addressee = _roles(tokens, names, request.cues)
        if form is None and speaker is None and addressee is None:
            continue
        found.append(
            AddressObservation(
                speaker_id=speaker,
                addressee_id=addressee,
                tv_form=form,
                sentence=sentence.text,
            )
        )
    return tuple(found)


def _tv_form(tokens: tuple[Token, ...], cues: AddressCues) -> TvForm | None:
    t_lemmas = set(cues.t_lemmas)
    v_lemmas = set(cues.v_lemmas)
    v_surfaces = set(cues.v_surfaces)
    has_t = any(token.lemma.casefold() in t_lemmas for token in tokens)
    has_v = any(_is_v(token, v_lemmas, v_surfaces) for token in tokens)
    if has_t and has_v:
        return TvForm.MIXED
    if has_t:
        return TvForm.T
    if has_v:
        return TvForm.V
    return None


def _is_v(token: Token, v_lemmas: set[str], v_surfaces: set[str]) -> bool:
    lemma = token.lemma.casefold()
    if not v_surfaces:
        return lemma in v_lemmas
    return token.surface in v_surfaces and lemma in v_lemmas


def _roles(
    tokens: tuple[Token, ...],
    names: tuple[tuple[str, tuple[str, ...]], ...],
    cues: AddressCues,
) -> tuple[str | None, str | None]:
    mentions = _mentions(tokens, names)
    if not mentions:
        return None, None
    verb_at = _speech_index(tokens, cues)
    if verb_at is None:
        return None, mentions[0][1]
    before = [char_id for index, char_id in mentions if index < verb_at]
    after = [char_id for index, char_id in mentions if index > verb_at]
    speaker = after[0] if after else None
    addressee = before[0] if before else None
    if speaker is not None and addressee == speaker:
        addressee = next((item for item in before if item != speaker), None)
    return speaker, addressee


def _mentions(
    tokens: tuple[Token, ...],
    names: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[tuple[int, str], ...]:
    folded = tuple(_norm(token.surface) for token in tokens)
    found: list[tuple[int, str]] = []
    index = 0
    while index < len(folded):
        hit = _longest_name(folded, index, names)
        if hit is None:
            index += 1
            continue
        width, char_id = hit
        found.append((index, char_id))
        index += width
    return tuple(found)


def _longest_name(
    folded: tuple[str, ...],
    start: int,
    names: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[int, str] | None:
    best: tuple[int, str] | None = None
    for char_id, parts in names:
        width = len(parts)
        if start + width > len(folded):
            continue
        if folded[start : start + width] != parts:
            continue
        if best is None or width > best[0]:
            best = (width, char_id)
    return best


def _speech_index(tokens: tuple[Token, ...], cues: AddressCues) -> int | None:
    verbs = set(cues.speech_lemmas)
    for index, token in enumerate(tokens):
        if token.lemma.casefold() in verbs:
            return index
    return None


def _name_index(
    characters: tuple[Character, ...],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    found: list[tuple[str, tuple[str, ...]]] = []
    for item in characters:
        for raw in (item.canonical_name, *item.aliases):
            parts = tuple(part for part in _norm(raw).split() if part)
            if not parts or (len(parts) == 1 and parts[0] in _SKIP_NAMES):
                continue
            found.append((item.id, parts))
    found.sort(key=lambda row: -len(row[1]))
    return tuple(found)


def _norm(text: str) -> str:
    chars = [ch.casefold() if ch.isalnum() else " " for ch in text]
    return " ".join("".join(chars).split())


def _is_dialogue(paragraph: Paragraph) -> bool:
    text = paragraph.raw_text.strip()
    return bool(text) and text.startswith(_SPEECH_OPENERS)


def _group_tokens(tokens: tuple[Token, ...]) -> dict[str, tuple[Token, ...]]:
    grouped: dict[str, list[Token]] = {}
    for token in tokens:
        grouped.setdefault(token.sentence_id, []).append(token)
    return {key: tuple(value) for key, value in grouped.items()}
