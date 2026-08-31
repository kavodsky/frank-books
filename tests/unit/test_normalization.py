"""Golden-file tests for roadmap 1.2 normalization."""

from __future__ import annotations

from pathlib import Path

import pytest

from frank.domain.services.normalization import NormalizeConfig, normalize_text

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "normalization"


@pytest.mark.unit
def test_german_normalization_matches_golden() -> None:
    config = NormalizeConfig(lang="de", header_max_chars=60, header_min_repeats=2)
    raw = (FIXTURES / "de_input.txt").read_text(encoding="utf-8")
    got = normalize_text(raw, config)
    expected = (FIXTURES / "de_expected.txt").read_text(encoding="utf-8")
    assert got == expected


@pytest.mark.unit
def test_hungarian_normalization_matches_golden() -> None:
    config = NormalizeConfig(lang="hu", header_max_chars=60, header_min_repeats=2)
    raw = (FIXTURES / "hu_input.txt").read_text(encoding="utf-8")
    got = normalize_text(raw, config)
    expected = (FIXTURES / "hu_expected.txt").read_text(encoding="utf-8")
    assert got == expected


@pytest.mark.unit
def test_nfc_composes_decomposed_characters() -> None:
    config = NormalizeConfig(lang="de", header_max_chars=60, header_min_repeats=3)
    assert normalize_text("o\u0308", config).strip() == "ö"
