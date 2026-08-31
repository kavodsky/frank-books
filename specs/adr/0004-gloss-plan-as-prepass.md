# ADR 0004 — Gloss decisions in a sequential pre-pass

Date: 2026-08-30. Status: accepted.

## Context
The Frank method glosses a word on first occurrence and thins out over the book.
"First occurrence" depends on reading order, but generation is chunked.

## Decision
A single sequential pass over all tokens in reading order writes
`gloss_plan(token_id, gloss, reason)` with a declining per-sentence quota.
Generation only reads the plan.

## Consequences
+ Gloss density is order-correct and reproducible; generation stays order-agnostic.
+ Density is tunable without re-running any LLM.
− The plan must be recomputed if the frequency lists or thresholds change.
