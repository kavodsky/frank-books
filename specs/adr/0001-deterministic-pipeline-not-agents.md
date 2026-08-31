# ADR 0001 — Deterministic pipeline, not autonomous agents

Date: 2026-08-30. Status: accepted.

## Context
The initial idea was to use planning agents to organize book processing.

## Decision
Use a deterministic DAG with LLM calls inside known steps. LLMs never decide
pipeline structure, never touch rendering, never see the whole book.

## Consequences
+ Reproducible, cacheable, resumable; failures are localized and classified.
+ Cheap: no planning tokens, no re-deliberation per book.
− Adding a new processing stage requires a code change, not a prompt change.
