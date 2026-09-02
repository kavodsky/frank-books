"""Budgeted PromptContext for one paragraph (roadmap Phase 4).

Same inputs yield a byte-identical rendering. Sections stay in priority order;
overflow is truncated from the bottom. Token weight is whitespace-separated
words (ADR 0018).

German: a paragraph whose tokens include lemma ``Oliver`` gets
``MUST translate Oliver as Олівер``. Hungarian: lemma ``Sándor`` gets
``MUST translate Sándor as Шандор``. Dialogue adds gender and T/V
(``du``/``te`` → ти, ``Sie``/``ön`` → Ви).
"""

from __future__ import annotations

import re

from frank.domain.model.annotation import Token
from frank.domain.model.context import (
    ContextAssemblyRequest,
    ContextSectionName,
    PromptContext,
    PromptSection,
    RollingSentence,
)
from frank.domain.model.termbase import AddressPair, Character, StyleCard, Term, TvForm
from frank.domain.services.address_detect import (
    characters_in_tokens,
    is_dialogue_paragraph,
)
from frank.domain.services.style_card import render_style_card_markdown

_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_TV_LABEL = {
    TvForm.T: "T (ти)",
    TvForm.V: "V (Ви)",
    TvForm.MIXED: "MIXED — do not lock T/V; gloss a switch",
}


def assemble_context(request: ContextAssemblyRequest) -> PromptContext:
    """Assemble one paragraph's generation context; never exceed ``max_tokens``."""
    window = request.rolling_window[-request.config.rolling_window_sentences :]
    sections = _fit(_drafts(request, window), request.config.max_tokens)
    rendered = "\n\n".join(item.text for item in sections)
    return PromptContext(
        paragraph_id=request.paragraph.id,
        sections=sections,
        rendered=rendered,
        token_count=count_tokens(rendered),
        rolling_window_text=_window_payload(window),
    )


def count_tokens(text: str) -> int:
    """Whitespace-separated token estimate used by the Phase 4 budget (ADR 0018)."""
    return len(text.split())


def _drafts(
    request: ContextAssemblyRequest, window: tuple[RollingSentence, ...]
) -> tuple[PromptSection, ...]:
    parts = (
        (ContextSectionName.TASK_INSTRUCTION, request.task_instruction.strip()),
        (ContextSectionName.TERMBASE_SLICE, _render_termbase(_slice_terms(request))),
        (ContextSectionName.SPEAKER_CONTEXT, _render_speaker(request)),
        (
            ContextSectionName.ROLLING_WINDOW,
            _labeled("Window:", _render_rolling(window)),
        ),
        (
            ContextSectionName.SCENE_BRIEF,
            _labeled(
                "Scene:",
                _first_sentences(
                    request.scene_brief, request.config.scene_brief_sentences
                ),
            ),
        ),
        (
            ContextSectionName.CHAPTER_SUMMARY,
            _labeled("Chapter:", request.chapter_summary.strip()),
        ),
        (
            ContextSectionName.STYLE_CARD_DIGEST,
            _style_digest(request.style_card, request.config.style_card_digest_lines),
        ),
    )
    return tuple(PromptSection(name=name, text=text) for name, text in parts if text)


def _fit(
    drafts: tuple[PromptSection, ...], max_tokens: int
) -> tuple[PromptSection, ...]:
    kept: list[PromptSection] = []
    remaining = max_tokens
    for draft in drafts:
        used = count_tokens(draft.text)
        if used <= remaining:
            kept.append(draft)
            remaining -= used
            continue
        clipped = _clip(draft.text, remaining)
        if clipped:
            kept.append(PromptSection(name=draft.name, text=clipped))
        break
    return tuple(kept)


def _clip(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    words = text.split()
    if len(words) <= max_tokens:
        return text
    return " ".join(words[:max_tokens])


def _slice_terms(request: ContextAssemblyRequest) -> tuple[Term, ...]:
    found = [
        term
        for term in request.terms
        if term.translation_uk and _term_matches(term, request.tokens)
    ]
    found.sort(key=lambda term: (term.lemma.casefold(), term.id))
    return tuple(found)


def _term_matches(term: Term, tokens: tuple[Token, ...]) -> bool:
    keys = _token_keys(tokens)
    if term.lemma.casefold() in keys:
        return True
    return any(_phrase_in(tokens, keys, form) for form in term.surface_forms)


def _token_keys(tokens: tuple[Token, ...]) -> set[str]:
    keys: set[str] = set()
    for token in tokens:
        keys.add(token.lemma.casefold())
        keys.add(token.surface.casefold())
        if token.reunited_lemma:
            keys.add(token.reunited_lemma.casefold())
    return keys


def _phrase_in(tokens: tuple[Token, ...], keys: set[str], phrase: str) -> bool:
    parts = tuple(phrase.casefold().split())
    if not parts:
        return False
    if len(parts) == 1:
        return parts[0] in keys
    width = len(parts)
    last = len(tokens) - width + 1
    surfaces = tuple(token.surface.casefold() for token in tokens)
    lemmas = tuple(token.lemma.casefold() for token in tokens)
    for start in range(max(last, 0)):
        if surfaces[start : start + width] == parts:
            return True
        if lemmas[start : start + width] == parts:
            return True
    return False


def _render_termbase(terms: tuple[Term, ...]) -> str:
    if not terms:
        return ""
    return "\n".join(
        f"MUST translate {term.lemma} as {term.translation_uk}" for term in terms
    )


def _render_speaker(request: ContextAssemblyRequest) -> str:
    if not is_dialogue_paragraph(request.paragraph):
        return ""
    involved = characters_in_tokens(request.tokens, request.characters)
    if not involved:
        return ""
    names = {item.id: item for item in involved}
    lines = [_character_line(item) for item in involved]
    lines.extend(_address_lines(request.address_pairs, names))
    return "\n".join(lines)


def _character_line(item: Character) -> str:
    return f"{item.canonical_name} / {item.translation_uk} ({item.gender.value})"


def _address_lines(
    pairs: tuple[AddressPair, ...], involved: dict[str, Character]
) -> list[str]:
    rows = [
        pair
        for pair in pairs
        if pair.speaker_id in involved and pair.addressee_id in involved
    ]
    rows.sort(key=lambda pair: _pair_sort(pair, involved))
    return [_address_line(pair, involved) for pair in rows]


def _pair_sort(pair: AddressPair, involved: dict[str, Character]) -> tuple[str, str]:
    speaker = involved[pair.speaker_id].canonical_name.casefold()
    addressee = involved[pair.addressee_id].canonical_name.casefold()
    return speaker, addressee


def _address_line(pair: AddressPair, involved: dict[str, Character]) -> str:
    speaker = involved[pair.speaker_id].canonical_name
    addressee = involved[pair.addressee_id].canonical_name
    return f"{speaker} → {addressee}: {_TV_LABEL[pair.tv_form]}"


def _render_rolling(window: tuple[RollingSentence, ...]) -> str:
    lines: list[str] = []
    for item in window:
        source = item.source.strip()
        uk = item.idiomatic_uk.strip()
        if source:
            lines.append(source)
        if uk:
            lines.append(uk)
    return "\n".join(lines)


def _window_payload(window: tuple[RollingSentence, ...]) -> str:
    return "\n".join(
        f"{item.source.strip()}\n{item.idiomatic_uk.strip()}" for item in window
    )


def _first_sentences(text: str, limit: int) -> str:
    stripped = text.strip()
    if not stripped or limit <= 0:
        return ""
    parts = tuple(part.strip() for part in _SPLIT.split(stripped) if part.strip())
    if not parts:
        return stripped
    return " ".join(parts[:limit])


def _labeled(label: str, body: str) -> str:
    if not body:
        return ""
    return f"{label}\n{body}"


def _style_digest(card: StyleCard | None, line_count: int) -> str:
    if card is None or line_count <= 0:
        return ""
    lines = render_style_card_markdown(card).splitlines()
    return "\n".join(lines[:line_count]).rstrip()
