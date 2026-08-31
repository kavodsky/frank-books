"""Project settings loaded from TOML. Model names live only here (ADR 0010)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Backend = Literal["ollama", "mlx"]
SourceLang = Literal["de", "hu"]
TargetLang = Literal["uk"]


class ModelEndpoint(BaseModel):
    name: str
    base_url: str


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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="forbid")

    backend: Backend
    fast: ModelEndpoint
    smart: ModelEndpoint
    budgets: Budgets
    concurrency: Concurrency
    languages: Languages
    ingest: IngestSettings


def load_settings(path: Path | None = None) -> Settings:
    """Load settings from `config.toml` (or an explicit path)."""
    resolved = Path("config.toml") if path is None else path
    with resolved.open("rb") as fh:
        payload = tomllib.load(fh)
    return Settings.model_validate(payload)
