"""Clamp chapter summaries and render the StyleCard markdown (roadmap 3.5)."""

from __future__ import annotations

import re

from frank.domain.model.termbase import ChapterBriefConfig, StyleCard

_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def clamp_summary(text: str, config: ChapterBriefConfig) -> str:
    """Keep at most ``summary_sentence_max`` sentences; never pad up to min.

    German/Hungarian source is already cut to lead+tail; this only bounds the
    Ukrainian plot summary (e.g. six sentences → five).
    """
    stripped = text.strip()
    if not stripped:
        return ""
    parts = tuple(part.strip() for part in _SPLIT.split(stripped) if part.strip())
    if not parts:
        return stripped
    kept = parts[: config.summary_sentence_max]
    return " ".join(kept)


def render_style_card_markdown(card: StyleCard) -> str:
    """Stable markdown for ``books/{slug}/style_card.md`` (Phase 4 uses first lines)."""
    return (
        "# Style card\n"
        "\n"
        f"- **Epoch:** {card.epoch}\n"
        f"- **Setting:** {card.setting}\n"
        f"- **Register:** {card.source_register}\n"
        f"- **Narration:** {card.narration}\n"
        f"- **Tone:** {card.tone}\n"
        f"- **Directives:** {card.directives}\n"
    )
