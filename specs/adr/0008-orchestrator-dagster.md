# ADR 0008 — Dagster as the orchestrator, partitioned by chapter

Date: 2026-08-30. Status: accepted.

## Context
Sessions run unattended; a failed step must be visible, classified and restartable
without redoing finished work, and without hand-rolled retry/resume logic.

## Decision
Dagster. Assets map to phases, partitions to chapters, asset checks to the
Phase 5.2 validations, RetryPolicy to LLM-touching assets. Partition by CHAPTER,
never by passage (thousands of partitions would drown the UI and per-partition
overhead would rival the work). Generation is one sequential asset (ADR 0006).

## Alternatives rejected
- **Prefect 3**: simpler, but models runs of actions rather than freshness of
  artifacts; "re-materialize just this asset" has no direct equivalent.
- **Temporal**: durable execution is the theoretically ideal answer to resume,
  but requires a server plus workers — far too heavy for a single-user local tool.
- **Snakemake**: file-target model fits the cache well, but no UI.
- **Airflow**: schedule-centric; wrong model.

## Consequences
+ No hand-written retry/resume/tracking code; failures nameable in a UI.
+ Owner already knows Dagster (PharmaIntel) — no learning cost.
− A daemon to run locally (via process-compose) and Dagster concepts in the repo.
− Resume correctness still relies on our own content-addressed cache, not Dagster.
