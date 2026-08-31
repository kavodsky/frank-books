"""Gold files meet the Phase 0 quota (50+ per language, hard cases included)."""

from __future__ import annotations

from pathlib import Path

import pytest

from frank.infrastructure.llm.benchmark import load_gold

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_gold_files_meet_quota() -> None:
    de = load_gold(REPO / "gold" / "de_sample.jsonl")
    hu = load_gold(REPO / "gold" / "hu_sample.jsonl")
    assert len(de) >= 50
    assert len(hu) >= 50
    assert any("separable_verb" in s.tags for s in de)
    assert any("preverb" in s.tags for s in hu)
