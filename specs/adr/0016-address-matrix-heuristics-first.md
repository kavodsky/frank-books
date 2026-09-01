# ADR 0016 — Address matrix: heuristics first, SMART only for known pairs

Date: 2026-09-01. Status: accepted.

## Context
Roadmap 3.4 needs speaker→addressee T/V before generation. Literary attribution
is hard, a chapter does not fit a SMART prompt (ADR 0015), and LLMs must not
re-parse morphology we already have.

## Decision
1. Scan only speech-opener paragraphs (same openers as passage grouping).
2. T/V from closed cue lists in `data/address_cues.toml` (German `du` / capitalized
   `Sie`·`Ihnen`; Hungarian `te` / `ön`·`maga`·`tetszik`).
3. Speaker = character mention after a speech verb; addressee = mention before it
   (vocative). Missing either endpoint → drop the observation; no invented pairs.
4. Consistent T or V is stored as-is; T and V on the same pair → MIXED.
5. Both endpoints known but form unknown → SMART with
   `evidence_sentences_per_pair` sentences, never the chapter. Unanswered → MIXED.

## Alternatives rejected
- Full-chapter SMART attribution: budget and coverage theatre.
- MIXED rows for unidentified speakers: Phase 5 cannot use them as pair rules.
- Guessing `Sie` in narrative as V: German `Sie gingen` is 3rd person.

## Consequences
+ Clear `du`/`te` lines with `sagte X` become pair rules without an LLM.
− Most dialogue stays uncovered; generation falls back to the scene-level
  “follow the source” directive (roadmap 3.4).
