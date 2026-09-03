"""config.example.toml is a valid Settings document."""

from __future__ import annotations

from pathlib import Path

import pytest

from frank.config import load_settings

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_example_config_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRANK_FAST_API_KEY", raising=False)
    monkeypatch.delenv("FRANK_SMART_API_KEY", raising=False)
    settings = load_settings(REPO / "config.example.toml")
    assert settings.languages.target == "uk"
    assert settings.concurrency.generation == 1
    assert settings.budgets.asset_max_retries == 2
    assert settings.budgets.asset_retry_delay_seconds == 1.0
    assert settings.backend in {"mlx", "ollama"}
    assert settings.fast.base_url.startswith("http://127.0.0.1")
    assert settings.nlp.german_model == "de_core_news_lg"
    assert settings.nlp.hungarian_model == "hu_core_news_lg"
    assert settings.nlp.lemma_batch_size == 50
    assert settings.nlp.short_sentence_max_tokens == 8
    assert settings.nlp.sense_unit_min_tokens == 3
    assert settings.nlp.sense_unit_max_tokens == 8
    assert settings.nlp.heavy_pp_min_tokens == 6
    assert settings.gloss.frequency_top_n == 1000
    assert settings.gloss.function_word_top_n == 300
    assert settings.gloss.reminder_gap_sentences == 400
    assert settings.gloss.quota_chapter_start == 6
    assert settings.gloss.quota_last_third == 2
    assert settings.passage.min_chars == 800
    assert settings.passage.max_chars == 1500
    assert settings.passage.dialogue_max_chars == 160
    assert settings.context.rolling_window_sentences == 3
    assert settings.context.scene_brief_sentences == 2
    assert settings.context.style_card_digest_lines == 5
    assert settings.context.scene_brief_every_paragraphs == 4
    assert settings.generation.fast_retry_attempts == 2
    assert settings.generation.length_ratio_min == 0.6
    assert settings.generation.length_ratio_max == 2.0
    assert settings.generation.ukrainian_marker_min_chars == 20
    assert settings.generation.backtranslation_sample_rate == 0.10
    assert settings.generation.backtranslation_chrf_min == 40
    assert settings.generation.hard_sentence_min_tokens == 24
    assert settings.termbase.entity_min_occurrences == 3
    assert settings.termbase.unknown_lemma_min_count == 5
    assert settings.termbase.merge_max_edit_distance == 2
    assert settings.termbase.translation_batch_size == 20
    assert settings.termbase.evidence_sentences_per_person == 3
    assert settings.termbase.character_map_batch_size == 10
    assert settings.termbase.evidence_sentences_per_pair == 3
    assert settings.termbase.address_map_batch_size == 10
    assert settings.termbase.summary_lead_sentences == 8
    assert settings.termbase.summary_tail_sentences == 8
    assert settings.termbase.summary_sentence_min == 3
    assert settings.termbase.summary_sentence_max == 5
    assert settings.fast.api_key is None
    assert settings.smart.api_key is None


@pytest.mark.integration
def test_api_key_from_env_when_toml_omits_it(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FRANK_FAST_API_KEY", raising=False)
    monkeypatch.setenv("FRANK_SMART_API_KEY", "sk-from-env")
    path = tmp_path / "config.toml"
    path.write_text((REPO / "config.example.toml").read_text(encoding="utf-8"))
    settings = load_settings(path)
    assert settings.smart.api_key is not None
    assert settings.smart.api_key.get_secret_value() == "sk-from-env"
    assert settings.fast.api_key is None


@pytest.mark.integration
def test_toml_api_key_wins_over_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRANK_SMART_API_KEY", "sk-from-env")
    text = (REPO / "config.example.toml").read_text(encoding="utf-8")
    text = text.replace(
        'base_url = "http://127.0.0.1:8080/v1"',
        'base_url = "http://127.0.0.1:8080/v1"\napi_key = "sk-from-toml"',
        1,
    )
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    settings = load_settings(path)
    assert settings.smart.api_key is not None
    assert settings.smart.api_key.get_secret_value() == "sk-from-toml"
