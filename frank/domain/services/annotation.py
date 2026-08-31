"""Bind analyzer sentences and tokens to a paragraph (roadmap 2.1–2.2)."""

from __future__ import annotations

from collections.abc import Sequence

from frank.domain.model.annotation import (
    Annotation,
    ParsedSentence,
    ParsedToken,
    Token,
)
from frank.domain.model.book import Paragraph, Sentence
from frank.domain.services.sentences import sentences_for_paragraph


def annotate_paragraph(
    paragraph: Paragraph, parsed: Sequence[ParsedSentence]
) -> Annotation:
    """Attach analyzer sentences and tokens; empty lemma falls back to surface.

    German: ``Der Arzt sah das Kind.`` → DET ``der`` keeps Case=Nom.
    Hungarian: ``felállt`` keeps a non-empty lemma (surface if the analyzer
    left the lemma blank).
    """
    kept = tuple(item for item in parsed if item.text.strip())
    sentences = sentences_for_paragraph(paragraph, tuple(item.text for item in kept))
    tokens: list[Token] = []
    for sentence, item in zip(sentences, kept, strict=True):
        tokens.extend(_tokens_for_sentence(sentence, item.tokens))
    return Annotation(sentences=sentences, tokens=tuple(tokens))


def _tokens_for_sentence(
    sentence: Sentence, parsed: Sequence[ParsedToken]
) -> tuple[Token, ...]:
    return tuple(
        Token(
            id=f"{sentence.id}-t{token.index}",
            sentence_id=sentence.id,
            index=token.index,
            surface=token.surface,
            lemma=_lemma(token.surface, token.lemma),
            upos=token.upos or "X",
            morph=token.morph,
        )
        for token in parsed
    )


def _lemma(surface: str, lemma: str) -> str:
    stripped = lemma.strip()
    return stripped if stripped else surface
