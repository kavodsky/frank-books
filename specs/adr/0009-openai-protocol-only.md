# ADR 0009 — Talk to models over the OpenAI protocol only

Date: 2026-08-30. Status: accepted.

## Context
Models are served locally; candidate servers include Ollama, mlx-lm, LM Studio
and llama.cpp, each with its own native API.

## Decision
One client speaking only `/v1/chat/completions` against localhost base URLs from
config. FAST and SMART tiers may point to different ports. No backend-specific
code paths; structured output via `response_format` with schemas generated from
Pydantic models.

## Consequences
+ Swapping a server or a model is a config change.
− Server-specific features (e.g. native Ollama options) are unavailable.
