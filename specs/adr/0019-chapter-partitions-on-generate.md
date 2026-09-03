# ADR 0019 — Chapter partitions on generate; segment and analyze stay book-level

Date: 2026-09-03. Status: accepted.

## Context
Roadmap Phase 7 maps assets to `ingest → segment → analyze → generate → render`
and says generation is partitioned by chapter (never by passage). Gloss planning
(2.4) walks the whole book for frequency and a declining quota. Termbase,
characters, and the T/V matrix (Phase 3) are book-wide reduces. Two books are
separate SQLite files, so a bare chapter index would collide in the Dagster UI.

## Decision
1. Partition key is `{slug}:{chapter.index}` (1-based). Ingest, segment, and
   analyze register those keys on the `chapter` dynamic partition set.
2. `segment` and `analyze` are unpartitioned book assets. They call the existing
   `annotate_book` and `analyze_book` use cases. Splitting them per chapter would
   change gloss-quota and term-merge semantics already covered by Phase 2–3 tests.
3. `generate` is the sequential partitioned asset (concurrency 1, `pool=generation`,
   `BackfillPolicy.multi_run(1)`). Session budget applies per materialization.
4. `render` depends on `analyze`, not on every generate partition, so a partial
   session can still write a docx. `frank render` remains the hands-on path.
5. Application use cases are the step functions; there is no `frank/steps/`
   package and no `frank generate` command.

## Alternatives rejected
- Partition segment by chapter: gloss planning needs book-wide token counts.
- Unpartitioned generate: the acceptance criterion is rematerializing one chapter.
- Partition key = chapter index only: two books would share keys.

## Consequences
+ One execution path for generation (Dagster `generate`).
+ Resume of a chapter is rematerialize of that partition; finished paragraphs
  hit the content-addressed cache.
− Analysis parallelism from `concurrency.analysis` is unused until those assets
  are split; generation is sequential as required.
