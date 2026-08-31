# ADR 0003 — Morphology and lemmas from analyzers, not from LLMs

Date: 2026-08-30. Status: accepted.

## Context
Hungarian is agglutinative; German has separable verbs. Small local models make
frequent morphological errors, and lemmas are load-bearing (termbase matching,
first-occurrence gloss tracking, `lemma – gloss` display).

## Decision
spaCy (de) and HuSpaCy (hu) produce tokens, lemmas, morphology and parses. LLMs
receive the analysis and only EXPLAIN it. Where lemmatizers are weak, a second
lemmatizer provides a cross-check and an LLM arbitrates disagreements in batched,
type-level calls, validated against a dictionary (roadmap 2.2b).

## Consequences
+ Deterministic, cached, cheap; model errors cannot corrupt the gloss plan.
− Two analyzer stacks to maintain; arbitration adds a step.
