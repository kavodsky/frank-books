"""Chapter and paragraph splitting (roadmap 1.3)."""

from __future__ import annotations

import pytest

from frank.domain.services.structure import split_chapters, split_paragraphs


@pytest.mark.unit
def test_hash_headings_split_german_and_hungarian() -> None:
    text = "# Erstes Kapitel\n\nEs war einmal.\n\n# Zweites Kapitel\n\nAm Morgen.\n"
    drafts = split_chapters(text, r"^# (.+)$", "Das Buch")
    assert [d.title for d in drafts] == ["Erstes Kapitel", "Zweites Kapitel"]
    hu = split_chapters("# Első fejezet\n\nEgyszer volt.\n", r"^# (.+)$", "A könyv")
    assert hu[0].title == "Első fejezet"


@pytest.mark.unit
def test_no_heading_is_one_chapter() -> None:
    drafts = split_chapters("Csak egy bekezdés.", r"^# (.+)$", "Cím")
    assert len(drafts) == 1
    assert drafts[0].title == "Cím"


@pytest.mark.unit
def test_blank_line_paragraphs_drop_empty() -> None:
    assert split_paragraphs("A\n\n\nB\n\n") == ("A", "B")
