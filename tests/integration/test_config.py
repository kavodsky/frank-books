"""config.example.toml is a valid Settings document."""

from __future__ import annotations

from pathlib import Path

import pytest

from frank.config import load_settings

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_example_config_loads() -> None:
    settings = load_settings(REPO / "config.example.toml")
    assert settings.languages.target == "uk"
    assert settings.concurrency.generation == 1
    assert settings.backend in {"mlx", "ollama"}
    assert settings.fast.base_url.startswith("http://127.0.0.1")
    assert settings.nlp.german_model == "de_core_news_lg"
    assert settings.nlp.hungarian_model == "hu_core_news_lg"
    assert settings.nlp.lemma_batch_size == 50
