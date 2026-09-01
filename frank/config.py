"""Project settings loaded from TOML. Model names live only here (ADR 0010)."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_FAST_API_KEY_ENV = "FRANK_FAST_API_KEY"
_SMART_API_KEY_ENV = "FRANK_SMART_API_KEY"

Backend = Literal["ollama", "mlx"]
SourceLang = Literal["de", "hu"]
TargetLang = Literal["uk"]


class ModelEndpoint(BaseModel):
    name: str
    base_url: str
    api_key: SecretStr | None = None


class Budgets(BaseModel):
    prompt_tokens: int
    llm_timeout_seconds: float
    llm_max_retries: int
    llm_retry_min_seconds: float
    llm_retry_max_seconds: float
    session_max_minutes: int
    session_max_passages: int


class Concurrency(BaseModel):
    analysis: int = Field(ge=1)
    generation: int = Field(ge=1, le=1)


class Languages(BaseModel):
    source: SourceLang
    target: TargetLang


class IngestSettings(BaseModel):
    max_paragraph_chars: int = Field(ge=1)
    header_max_chars: int = Field(ge=1)
    header_min_repeats: int = Field(ge=2)
    foreign_script_ratio: float = Field(gt=0, lt=1)


class NlpSettings(BaseModel):
    german_model: str
    hungarian_model: str
    lemma_batch_size: int = Field(ge=1, le=200)
    short_sentence_max_tokens: int = Field(ge=1)
    sense_unit_min_tokens: int = Field(ge=1)
    sense_unit_max_tokens: int = Field(ge=1)
    heavy_pp_min_tokens: int = Field(ge=1)


class GlossSettings(BaseModel):
    frequency_top_n: int = Field(ge=1)
    function_word_top_n: int = Field(ge=1)
    reminder_gap_sentences: int = Field(ge=1)
    reminder_max_occurrences: int = Field(ge=1)
    quota_chapter_start: int = Field(ge=1)
    quota_last_third: int = Field(ge=1)
    rare_morph_max_count: int = Field(ge=1)


class PassageSettings(BaseModel):
    min_chars: int = Field(ge=1)
    max_chars: int = Field(ge=1)
    dialogue_max_chars: int = Field(ge=1)


class TermbaseSettings(BaseModel):
    entity_min_occurrences: int = Field(ge=1)
    unknown_lemma_min_count: int = Field(ge=1)
    idiom_min_occurrences: int = Field(ge=1)
    merge_max_edit_distance: int = Field(ge=0)
    merge_min_stem_chars: int = Field(ge=1)
    translation_batch_size: int = Field(ge=1, le=200)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="forbid")

    backend: Backend
    fast: ModelEndpoint
    smart: ModelEndpoint
    budgets: Budgets
    concurrency: Concurrency
    languages: Languages
    ingest: IngestSettings
    nlp: NlpSettings
    gloss: GlossSettings
    passage: PassageSettings
    termbase: TermbaseSettings


def load_settings(path: Path | None = None) -> Settings:
    """Load settings from `config.toml` (or an explicit path)."""
    resolved = Path("config.toml") if path is None else path
    with resolved.open("rb") as fh:
        payload = tomllib.load(fh)
    return _with_env_api_keys(Settings.model_validate(payload))


def _with_env_api_keys(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "fast": _endpoint_key_from_env(settings.fast, _FAST_API_KEY_ENV),
            "smart": _endpoint_key_from_env(settings.smart, _SMART_API_KEY_ENV),
        }
    )


def _endpoint_key_from_env(endpoint: ModelEndpoint, env_name: str) -> ModelEndpoint:
    if _secret_text(endpoint.api_key) is not None:
        return endpoint
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return endpoint
    return endpoint.model_copy(update={"api_key": SecretStr(raw)})


def _secret_text(key: SecretStr | None) -> str | None:
    if key is None:
        return None
    value = key.get_secret_value().strip()
    return value or None
