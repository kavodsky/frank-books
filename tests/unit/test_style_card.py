"""Summary length clamp and StyleCard markdown (roadmap 3.5)."""

from __future__ import annotations

import pytest

from frank.domain.model.termbase import ChapterBriefConfig, StyleCard
from frank.domain.services.style_card import clamp_summary, render_style_card_markdown

_CFG = ChapterBriefConfig(
    lead_sentences=8,
    tail_sentences=8,
    summary_sentence_min=3,
    summary_sentence_max=5,
)


@pytest.mark.unit
def test_clamp_drops_extra_ukrainian_sentences() -> None:
    text = "Перша. Друга. Третя. Четверта. П'ята. Шоста."
    clamped = clamp_summary(text, _CFG)
    assert clamped == "Перша. Друга. Третя. Четверта. П'ята."


@pytest.mark.unit
def test_clamp_keeps_short_summary() -> None:
    assert clamp_summary("Одна. Дві.", _CFG) == "Одна. Дві."
    assert clamp_summary("   ", _CFG) == ""


@pytest.mark.unit
def test_style_card_markdown_lists_fields() -> None:
    card = StyleCard(
        book_id="b",
        epoch="XIX ст.",
        setting="Лондон, робітний дім",
        source_register="літературна німецька",
        narration="третя особа, минулий час",
        tone="похмурий, іронічний",
        directives="архаїчний присмак у doubling; глоси сучасною українською",
    )
    markdown = render_style_card_markdown(card)
    assert markdown.startswith("# Style card\n")
    assert "- **Epoch:** XIX ст." in markdown
    assert "- **Directives:** архаїчний присмак" in markdown
