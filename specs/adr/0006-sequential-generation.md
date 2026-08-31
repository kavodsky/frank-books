# ADR 0006 — Generation is strictly sequential

Date: 2026-08-30. Status: accepted.

## Context
Translation quality depends on the preceding text (rolling window of previous
sentences with their translations). Parallel generation would make context
depend on execution order, breaking determinism and cache semantics.

## Decision
Generation runs sequentially in book order, concurrency 1. Parallelism is allowed
only in ingestion, annotation and analysis (phases 1–3), partitioned by chapter.

## Consequences
+ Rolling-window context is always available; contexts are byte-reproducible.
+ Removes a whole class of race and cache-key bugs.
− Throughput is bound by one model at a time; sessions are the mitigation.
