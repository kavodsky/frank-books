# Tech Stack

Code layout and layering are specified separately in **architecture.md** (DDD,
applied selectively). This file pins the tools.

Hard requirements: **Python**, managed with **uv**. Everything runs locally on
macOS (Apple Silicon, M5 Max, 128 GB). No cloud services, no external APIs.

## Runtime & tooling

| Area | Choice | Notes |
|---|---|---|
| Language | Python ≥ 3.12 | |
| Env & deps | **uv** (`uv init`, `uv add`, `uv run`, lockfile committed) | Never call pip directly; never create requirements.txt |
| CLI | Typer | Single entry point `frank` (project script in `pyproject.toml`) |
| Config | pydantic-settings + `config.toml` / per-book `book.toml` | |
| Templating | jinja2 for versioned prompt templates | `infrastructure/llm/prompts/` |
| Layer enforcement | import-linter (or an AST test) asserting `domain/` imports nothing external | Part of Phase 0; the boundary is only real if it is tested |
| Lint/format | ruff (lint + format) | Enable rules that enforce architecture.md: `C901` (complexity ≤ 8), `PLR0913` (max args 4), `ANN` (type hints), `SIM`, `RET`, `TRY` (exception hygiene), `N` (naming), `ARG`. Max line length 88 |
| Type checking | mypy strict on `frank/domain/` and `frank/application/`, normal elsewhere | The domain is where types must be airtight |
| Tests | pytest, pytest-asyncio, syrupy (snapshot tests) | Domain services tested with no DB, no model server, no spaCy |
| Hooks | pre-commit | |

## LLM serving

| Area | Choice | Notes |
|---|---|---|
| Serving | Any local server exposing the **OpenAI protocol** on a localhost port (Ollama, mlx-lm server, LM Studio, llama.cpp server) | One internal client (`frank/llm.py`) speaks ONLY OpenAI `/v1/chat/completions`; zero backend-specific code. FAST and SMART tiers may live on different ports. MLX-based servers preferred for prefill-heavy prompts on M5 |
| Structured output | JSON-schema-constrained generation (Ollama structured outputs / `response_format`) | Never parse free text |
| Model tiers | FAST (high-throughput MoE, e.g. Qwen3.x-A3B class) and SMART (large MoE, e.g. DeepSeek V4 Flash / gpt-oss-120b class) | Exact models are decided by the Phase 0 benchmark and set ONLY in config — never hardcode model names in code or prompts |
| HTTP | httpx (async) | |
| Retries | tenacity | |

## NLP

| Area | Choice | Notes |
|---|---|---|
| German | spaCy + `de_core_news_lg` | Sentence split, lemmas, morph, NER, dependency parse (separable verbs via `prt`) |
| Hungarian | **HuSpaCy** `hu_core_news_lg` | Same duties; agglutinative morphology is why we do NOT let LLMs analyze |
| Lemma cross-check | simplemma (de), emmorph-based analyzer via HuSpaCy (hu) | Second opinion for step 2.2b; LLM arbitrates disagreements in batched type-level calls |
| MT metrics | sacrebleu (chrF/BLEU) | Benchmark harness + back-translation QA |
| Lang detect | fast lang-id lib (e.g. lingua or langdetect) | Output-language guard in validation |
| Frequency lists | static top-N lemma lists per language, shipped in `data/` | Gloss-worthiness tagging |

## Storage

| Area | Choice | Notes |
|---|---|---|
| DB | SQLite, one file per book (`books/{slug}/book.db`) | **SQLAlchemy 2.0** (`DeclarativeBase`, `Mapped[]`) in `infrastructure/persistence/tables.py`. NOT SQLModel — merging table and domain model breaks the DDD persistence-ignorance boundary (see architecture.md) |
| Domain objects | Pydantic v2 models / dataclasses in `frank/domain/model/` | Persistence-ignorant; explicit mappers convert to/from table rows |
| LLM contracts | Pydantic v2 models in `infrastructure/llm/schemas.py`; `response_format` generated via `model_json_schema()` | Single source of truth for the JSON schema — no hand-written `schemas/*.json` |
| Cache | content-addressed JSON files `cache/{slug}/{paragraph_hash}/{step}.json` | Cache key includes prompt version + model + termbase version |
| Logs | JSONL per run (`books/{slug}/logs/`) with full prompts/responses | Essential for debugging quality issues |
| Run state | `run` table with classified `error_class` | Domain-level history independent of Dagster's own run log |

## Ingestion

| Area | Choice | Notes |
|---|---|---|
| EPUB | ebooklib | Local `.epub` the operator copied |
| HTML | BeautifulSoup4 + trafilatura fallback | Local `.html`/`.htm` only (ADR 0013) |
| Encoding | charset-normalizer | Old saved MEK files vary |

## Output

| Area | Choice | Notes |
|---|---|---|
| Primary | **python-docx** with a styles template (`templates/frank.docx`) | Named character styles: FrankOriginal (black), FrankTranslation (green 0x2E7D32), FrankGloss/FrankNote (green italic), FrankUnadapted (black) |
| Conversion | pandoc (smoke test only in v1) | docx → epub/html later |

## Orchestration

| Area | Choice | Notes |
|---|---|---|
| Default | **Dagster** (local `dagster dev`), assets partitioned by CHAPTER, asset checks for validations, RetryPolicy on LLM assets | Chosen because the project is about artifact state + mid-way resume, not action scheduling; "materialize one asset" = "restart the failed step". Owner already uses Dagster (PharmaIntel) |
| Generation concurrency | 1 (sequential in chapter order) | Rolling-window context depends on preceding sentences; parallelism allowed in phases 2–3 only |
| Execution paths | exactly ONE for generation (Dagster asset materialization); CLI only for hands-on commands (ingest, inspect, review-terms, approve, render, status, report, bench) | No duplicate runner to keep in sync; step functions stay import-clean and unit-testable |
| Considered & rejected | Prefect 3 (models action runs, not artifact freshness), Temporal (durable execution, far too heavy), Snakemake (no UI), Airflow (schedule-centric) | |
| Process mgmt | process-compose for local services (model servers + dagster) | Matches existing local setup |
| Progress UI | rich (progress bar) + macOS `osascript` notification on finish/crash | So a 2-hour unattended session reports itself without watching logs |

## Explicitly NOT used (and why)

- **LangChain / LlamaIndex / agent frameworks** — the pipeline is a deterministic
  DAG; frameworks add indirection without value here.
- **LLM-based text parsing/regex-free "smart" extraction for validation** —
  all consistency checks are deterministic code.
- **Vector databases** — context is assembled by exact lemma matching and stored
  summaries; no semantic retrieval needed in v1.
- **pip / poetry / conda** — uv only.
