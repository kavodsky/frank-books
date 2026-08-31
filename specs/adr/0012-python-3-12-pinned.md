# ADR 0012 — Python 3.12 pinned for the interpreter, not just as a floor

Date: 2026-08-31. Status: accepted.

## Context
tech-stack.md requires Python ≥ 3.12, which leaves the actual interpreter open.
The load-bearing dependencies are not pure Python: spaCy `de_core_news_lg` and
HuSpaCy `hu_core_news_lg` ship compiled wheels and model packages that lag new
    10|CPython releases by months, and a missing wheel for the Hungarian model would
block Phase 2 entirely. Newer interpreters (3.13, 3.14) are installed on the
machine and would otherwise be picked up by uv.

## Decision
Pin the interpreter to CPython 3.12 via `.python-version` (uv-managed download)
and keep `requires-python = ">=3.12"` in `pyproject.toml`. Revisit only when both
language models publish wheels for a newer version.

## Alternatives rejected
    20|- Leave the interpreter unpinned: the environment then differs between machines
  and after every Homebrew upgrade, and the failure shows up as an unbuildable
  NLP wheel rather than as a version mismatch.
- Pin 3.13/3.14 for speed: the gain is irrelevant here — the pipeline is bound by
  local LLM inference, not by interpreter throughput.

## Consequences
+ One reproducible interpreter; `uv sync` is deterministic.
+ Phase 2 can add spaCy and HuSpaCy without a wheel hunt.
− No access to newer stdlib and typing features until the models catch up.
