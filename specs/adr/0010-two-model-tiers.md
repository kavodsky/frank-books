# ADR 0010 — Two model tiers (FAST / SMART)

Date: 2026-08-30. Status: accepted.

## Context
A 300-page book implies millions of generated tokens. Most work (literal units,
glosses over pre-supplied morphology) is easy; a minority (idioms, long hypotaxis,
failed validations) is hard. Machine: M5 Max, 128 GB.

## Decision
A fast MoE model does the bulk; a large model handles validation failures,
flagged-hard sentences and term/character analysis. Model names live ONLY in
config and are chosen by the Phase 0 benchmark, never hardcoded.

## Consequences
+ Order-of-magnitude better throughput at similar quality.
− Two servers to keep running; tier split must be monitored in the run report.
