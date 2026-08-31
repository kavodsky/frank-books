"""Bind analyzer sentence strings to a paragraph (roadmap 2.1)."""

from __future__ import annotations

from collections.abc import Sequence

from frank.domain.model.book import Paragraph, Sentence


def sentences_for_paragraph(
    paragraph: Paragraph, texts: Sequence[str]
) -> tuple[Sentence, ...]:
    """Give each non-empty analyzer sentence a stable id and 1-based index.

    German: ``Es war einmal.`` then ``Am Morgen.`` → two Sentence rows.
    Hungarian: ``Egyszer volt.`` then ``A királyfi elindult.`` likewise.
    """
    kept = tuple(text.strip() for text in texts if text.strip())
    return tuple(
        Sentence(
            id=f"{paragraph.id}-s{index}",
            paragraph_id=paragraph.id,
            index=index,
            text=text,
        )
        for index, text in enumerate(kept, start=1)
    )
