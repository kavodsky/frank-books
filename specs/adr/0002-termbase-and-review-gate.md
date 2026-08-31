# ADR 0002 — Termbase with a human review gate

Date: 2026-08-30. Status: accepted.

## Context
A whole book does not fit in one prompt, yet names, places and idioms must be
rendered identically across hundreds of independent LLM calls.

## Decision
A global pre-pass builds a termbase (names, places, idioms) plus a character
registry and address matrix BEFORE any translation. Relevant slices are injected
into each paragraph prompt and verified afterwards by deterministic checks.
Generation refuses to start while terms are unapproved (`--yolo` for experiments).

## Consequences
+ Consistency is guaranteed by code, not hoped for from prompting.
+ ~15 minutes of human review per book buys correctness for the whole book.
− Changing a term after generation invalidates the cache for affected paragraphs.
