# ADR 0018 — PromptContext token budget is whitespace words

Date: 2026-09-02. Status: accepted.

## Context
Phase 4 must truncate assembled context from the bottom so the total stays at
or under `budgets.prompt_tokens` (default 1800). Domain code cannot import a
model tokenizer. The same inputs must yield a byte-identical `PromptContext`.

## Decision
1. A token is a whitespace-separated word (`str.split()`). Empty text is 0.
2. Sections are filled in roadmap priority (instruction → termbase → speaker →
   rolling window → scene brief → chapter summary → style-card digest). The
   first section that does not fit is clipped to the remaining words; nothing
   below it is kept.
3. Empty sections are omitted, so they do not consume budget.
4. `rolling_window_text` is the last `rolling_window_sentences` source+UK
   pairs, even when the rolling-window *section* is dropped from the prompt —
   Phase 5 hashes that payload, not the truncated rendering.

## Alternatives rejected
- Model tokenizer in domain: violates the layer boundary.
- Character/4 heuristic: another unnamed threshold; word count is named by
  `prompt_tokens` and is stable.

## Consequences
+ Property tests can assert `token_count <= max_tokens` without a server.
− Real BPE length may exceed the estimate on agglutinative Hungarian; the
  generation client still has its own timeout and context window.
