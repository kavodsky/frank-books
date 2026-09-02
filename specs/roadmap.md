# Roadmap

Audience: LLM coding agents implementing this project step by step.
Rules for implementers:

- Implement phases **in order**. Do not start a phase before the previous phase's
  acceptance criteria pass.
- Every step produces code + tests. Every phase ends with something runnable:
  a CLI command, or (for generation) a materializable Dagster asset.
- **Simplicity rule:** prefer the smaller solution. Do not add a second way to do
  anything that already has one way; do not add abstraction layers, plugin
  systems, or config knobs the roadmap does not ask for.
- All intermediate data lives in **SQLite** (single file per book project) plus a
  content-addressed cache directory. No hidden state.
- Code layout, layering and naming follow **architecture.md** (DDD applied
  selectively). Use its ubiquitous-language terms as identifiers; never invent
  synonyms. Domain logic goes in `frank/domain/services/`, never in a Dagster
  asset or a CLI command.
- All LLM calls go through `frank/infrastructure/llm/` with: model routing
  (FAST / SMART tiers), Pydantic-generated JSON schemas, retries, an
  anti-corruption layer converting model output into domain objects, and full
  request/response logging to disk.
- Language of code, comments, identifiers: English. Generated book content: Ukrainian
  translations of German/Hungarian originals.
- Linguistic rules (transliteration, T/V, igekötő glossing, calque blacklist) live
  in **specs/linguistics.md** — implement from there, and add discovered rules back
  to it. Every non-obvious decision gets an ADR in `specs/adr/`
  (see architecture.md → Documentation rules).

---

## Data model (shared by all phases)

SQLite tables — declared with SQLAlchemy 2.0 in
`infrastructure/persistence/tables.py`; these are STORAGE shapes, not domain
objects (see architecture.md). Simplified; full DDL is defined in Phase 0:

- `book(id, slug, lang, title, author, source_url, license_note, status)`
- `chapter(id, book_id, index, title, summary_uk)`
- `passage(id, chapter_id, index)` — Frank doubling unit: a group of consecutive
  paragraphs (~800–1500 chars of original text; paragraph boundaries respected)
- `paragraph(id, chapter_id, passage_id, index, raw_text, hash, status)`  ← unit of caching/retry
- `sentence(id, paragraph_id, index, text)`
- `token(id, sentence_id, index, surface, lemma, upos, morph_json)`
- `term(id, book_id, kind, surface_forms_json, lemma, translation_uk, note,
  approved_bool)`  — kind ∈ {PERSON, PLACE, ORG, TITLE, IDIOM, DISAMBIG}
- `character(id, book_id, canonical_name, translation_uk, gender, aliases_json,
  role_note)`
- `address_pair(book_id, speaker_id, addressee_id, tv_form)` — tv_form ∈ {T, V, MIXED}
  (ти/Ви in Ukrainian; derived from du/Sie, te/ön/maga)
- `gloss_unit(id, sentence_id, index, source_span, natural_uk, word_for_word_uk, kind)`
- `word_note(id, sentence_id, index, surface, lemma, morph_note_uk, gloss_uk)`
- `qa_result(id, paragraph_id, check_name, passed_bool, detail_json, attempt)`

Cache directory: `cache/{book_slug}/{paragraph_hash}/{step_name}.json`.
A step re-run with an unchanged input hash MUST return the cached result.

---

## Phase 0 — Scaffolding & model harness

**Goal:** repo skeleton, config, LLM client, benchmark harness.

Steps:

- **0.1 Repo scaffold.** `uv init`; create the layered package layout EXACTLY as
  specified in **architecture.md** (`domain/`, `application/`, `infrastructure/`,
  `interfaces/`), plus `tests/` and `books/` (per-book SQLite + cache, gitignored).
  Tooling: ruff (with the rule set from tech-stack.md), mypy strict on
  `domain/` + `application/`, pytest, pre-commit. Code style and pattern rules in
  **architecture.md** are binding for every phase. Add the layer-boundary test now
  (import-linter or AST scan: `frank/domain/` must not import sqlalchemy, httpx,
  dagster, spacy, python-docx) — the boundary is only real if CI checks it.
- **0.2 Config.** Pydantic-settings; `config.toml` defines: FAST model name,
  SMART model name, backend (`ollama` | `mlx`), base URLs, token budgets,
  concurrency, target language pair.
- **0.3 LLM client.** One async client speaking ONLY the OpenAI protocol
  (`/v1/chat/completions`) against base URLs on localhost ports from config — no
  backend-specific code paths. Any local server exposing that protocol works
  (Ollama, mlx-lm server, LM Studio, llama.cpp server); FAST and SMART tiers may
  point to different ports. Features: JSON-schema-constrained generation via
  `response_format`, tenacity retries with exponential backoff, per-call timeout,
  full JSONL logging of prompt+response+latency+model.
- **0.4 Benchmark harness.** `frank bench --gold gold/hu_sample.jsonl --models ...`:
  runs a fixed set of 100+ gold sentences (50+ HU, 50+ DE — include detached separable-verb/preverb sentences with reference Ukrainian
  translations, hand-made) through candidate models, reports chrF/BLEU via
  `sacrebleu` plus a SMART-model-as-judge score; writes a markdown report.
  This decides the FAST/SMART assignment; do not hardcode model names elsewhere.

- **0.5 Run tracking & observability.** Foundation for unattended ~2h sessions.
  1. **Domain run log** (independent of any orchestrator):
     `run(id, book_id, started_at, ended_at, status, passages_done,
     last_passage_id, error_class, error_msg)`. `error_class ∈
     {model_unreachable, timeout, schema_invalid, validation_exhausted,
     db_error, termbase_not_approved, unknown}` — classify at raise time, never grep logs later.
  2. **Live progress**: `rich` progress bar over passages with current
     chapter/passage, elapsed, passages/hour.
  3. **Completion notice** (macOS): `osascript -e 'display notification …'` on
     session end AND on crash, including `error_class`. Keep it a 5-line helper.
  4. **Dagster scaffold**: `Definitions` with resources for the LLM client and the
     book DB, `dagster dev` entry point, and `process-compose` service definitions
     for the two model servers + dagster. Wiring of actual assets happens in
     Phase 7 — here only the skeleton and one trivial asset to prove it runs.
  Note for implementers: retries at the HTTP level stay in `frank/llm.py`
  (tenacity). Do NOT hand-roll step-level retry/resume logic anywhere else —
  Phase 7 asset retry policies plus the content-addressed cache cover it.

**Acceptance:** `uv run frank bench` produces a report; unit tests for cache and
LLM client pass with a mocked backend; `dagster dev` starts and materializes the
trivial asset; a simulated crash writes a classified `run` row and fires a
notification.

---

## Phase 1 — Ingestion

**Goal:** from a local file the operator copied (`.txt`, `.html`, `.epub`) to
clean, chapter-structured text in SQLite.

Steps:

- **1.1 Local file.** `frank ingest <path>`. Support: plain `.txt`, `.epub`
  (ebooklib), `.html` (BeautifulSoup + trafilatura fallback). No URL fetch, no
  site-specific adapters (ADR 0013). Store raw bytes untouched in
  `books/{slug}/raw/`. Catalog URL and license go in `books/{slug}/book.toml`.
- **1.2 Normalization.** Unicode NFC; fix soft hyphens, ligatures, typographic quote
  unification per language; collapse whitespace; drop page numbers/headers via
  heuristics (repeated short lines).
- **1.3 Structure detection.** Chapter splitting by heading heuristics (regexes per
  format adapter, overridable in a per-book `book.toml`). Paragraph splitting on
  blank lines. Persist `book/chapter/paragraph` rows. Record license/source note.
- **1.4 Sanity report.** `frank inspect <slug>`: chapters, paragraph count,
  suspicious paragraphs (too long > 1500 chars, non-target-language ratio, leftover
  markup). Ingestion is done only when the report is clean or exceptions are
  whitelisted in `book.toml`.

**Acceptance:** local `.txt`, `.html`, and `.epub` fixtures ingest cleanly;
golden-file tests for normalization; re-running ingest is idempotent.

---

## Phase 2 — Segmentation & morphology

**Goal:** sentences, clause-level sense units, and full morphological annotation.

Steps:

- **2.1 Sentence split.** spaCy `de_core_news_lg` for German, HuSpaCy
  `hu_core_news_lg` for Hungarian. Persist `sentence` rows.
- **2.2 Token & morphology.** Persist `token` rows: surface, lemma, UPOS, morph
  features (case, number, tense, definiteness, Hungarian possessive suffixes).
- **2.2b Lemma refinement (dual analyzer + LLM arbitration).** spaCy/HuSpaCy
  lemmatizers are imperfect, and lemmas are load-bearing (termbase matching, gloss
  planning first-occurrence tracking, `lemma – gloss` display). Procedure:
  1. Run a second cheap lemmatizer per language (German: `simplemma`; Hungarian:
     emmorph-based analyzer via HuSpaCy components). Where both lemmatizers agree →
     accept, no LLM.
  2. Collect disagreements and OOV forms, dedupe to TYPES
     `(surface, upos, one example sentence)` — never per token. Send to the SMART
     model in batches of ~50 types per call (JSON schema:
     `[{surface, upos, lemma}]`). Store results in
     `lemma_override(surface, upos, lemma, source)`.
  3. Validate each LLM lemma: must occur in the language's frequency/dictionary
     list in `data/`, OR be confirmed by a second LLM vote; otherwise keep the
     analyzer lemma and log. LLM is an arbiter, not ground truth.
  Overrides are applied deterministically to `token.lemma` before 2.3/2.4. The
  whole step is cached by the hash of the disputed-type set; rerun on unchanged
  input makes zero LLM calls. Expected volume: a few thousand types per book →
  tens of batched calls.
- **2.2c Separable-verb / preverb reunification.** German separable verbs
  (`ruft … an` → lemma `anrufen`) and Hungarian preverbs / igekötő
  (`olvasd el`, `el tudta olvasni` → lemma `elolvas`) must be treated as ONE
  lexical unit; plain lemmatizers miss detached forms. Deterministic pairing, then
  lexicon/LLM validation:
  1. **Candidate pairing.** German: token with dep `svp` attached to a verb; plus
     fallback: clause-local particle from the closed prefix list in
     `data/de_separable_prefixes.txt` (ab, an, auf, aus, bei, ein, mit, nach, vor,
     zu, zurück, weg, fest, statt, teil, …) whose finite verb lacks another `svp`.
     Hungarian: token with dep `compound:preverb`, or clause-local match against
     the closed igekötő list `data/hu_igekoto.txt` (meg, el, ki, be, fel/föl, le,
     össze, vissza, át, rá, ide, oda, szét, végig, körül, …). Attachment rule for
     auxiliary constructions: the preverb belongs to the INFINITIVE, not the finite
     auxiliary (`el tudta olvasni` → `el + olvas`, never `el + tud`).
  2. **Validation.** Reunited candidate lemma (`prefix + verb lemma`) must exist in
     the language's frequency/dictionary list in `data/`. Found → accept. Not found,
     or ambiguous prefix (German um-, über-, durch-, unter-, wieder- are separable
     only in some senses) → add the pair (with its sentence) to the SAME batched
     LLM arbitration as 2.2b, schema `{particle, verb, reunited_lemma|null}`.
  3. **Persistence.** `verb_particle(sentence_id, particle_token_id, verb_token_id,
     reunited_lemma, source)`; set `token.reunited_lemma` on the verb token.
  Downstream contract: gloss planning (2.4) keys first-occurrence tracking on the
  REUNITED lemma; word notes (Phase 5) display the reunited lemma with a short
  note (uk: "відокремлюваний префікс" / "igekötő"), and for Hungarian the gloss
  must reflect the preverb's aspectual/directional meaning
  (`olvas – читати` vs `elolvas – прочитати`).
- **2.3 Sense-unit segmentation.** Split each sentence into clause-level units for
  the Frank format using deterministic rules on the dependency parse (split at
  clause boundaries: finite-verb subtrees, coordinations, heavy PPs; target unit
  length 3–8 tokens). Sentences of ≤ 8 tokens are ONE unit — never split short
  sentences. No LLM here. Store as spans over the sentence.
- **2.4 Gloss planning (deterministic, sequential, no LLM).** Frank books do NOT
  gloss every word: a word is explained on first occurrence, then dropped; gloss
  density decreases over the book. Implement a single sequential pass over all
  tokens in reading order that maintains per-lemma state
  (`lemma_state(lemma, first_seen_sentence_id, gloss_count, last_glossed_sentence_id,
  occurrences)`) and writes a `gloss_plan(token_id, gloss_bool, reason)` table.
  Rules (all thresholds in config):
  - GLOSS on **first occurrence** of a lemma not in the language's top-N frequency
    list (ship static lists in `data/`; default N = 1000).
  - GLOSS as **reminder** if the lemma was last glossed > X sentences ago AND its
    total occurrence count in the book < 4 (default X = 400).
  - ALWAYS gloss: termbase IDIOM hits; false friends (static de↔uk / hu↔uk lists in
    `data/`); morphological traps (first occurrence of a REUNITED separable-verb /
    igekötő lemma from 2.2c; Hungarian tokens whose morph feature set is rare in
    the book).
  - NEVER gloss: top-300 function words; proper names after first occurrence
    (covered by termbase).
  - **Declining per-sentence quota:** soft cap of glosses per sentence that shrinks
    with chapter index (default: 6 in ch. 1 → 2 from the last third of the book);
    when over quota, drop reminders first, then lowest-rarity first-occurrences.
  `reason ∈ {first_occurrence, reminder, idiom, false_friend, morph_trap}`.
  MUST be a separate pre-pass: gloss decisions depend on reading order, while
  Phase 5 generation is parallelized by chapter — the plan makes generation
  order-independent. Rerun of the pass on unchanged input is byte-identical.
- **2.5 Passage grouping (deterministic).** Group consecutive paragraphs into
  `passage` rows of ~800–1500 chars of original text (config), never splitting a
  paragraph, never crossing a chapter boundary; a run of short dialogue paragraphs
  lands in ONE passage. The passage is the Frank DOUBLING unit for rendering
  (adapted passage → unadapted passage — per-paragraph doubling would make dialogue
  unreadable); generation and caching stay per paragraph.

**Acceptance:** for a fixture chapter, segmentation snapshot tests pass; every token
has a lemma; German separable verbs AND Hungarian detached preverbs are correctly
reunited in ≥ 95% of a hand-checked sample of 100 each (include auxiliary
constructions like `el tudta olvasni` in the Hungarian sample); on a hand-checked sample of 200 disputed types, post-arbitration
lemma accuracy ≥ 95%; rerunning 2.2b on unchanged input makes zero LLM calls.

---

## Phase 3 — Global analysis: termbase & context artifacts

**Goal:** everything needed for consistency and context-aware translation, produced
BEFORE any translation happens. This phase is the answer to "the book does not fit
into one prompt".

Steps:

- **3.1 NER + candidate terms.** spaCy/HuSpaCy NER over the whole book; merge
  surface variants by lemma/edit distance (e.g. HU case-suffixed name forms
  `Budapesten` → `Budapest`). Add high-frequency unknown lemmas and detected
  multiword idioms as DISAMBIG/IDIOM candidates.
- **3.2 Term translation (SMART model).** For each candidate: one approved Ukrainian
  rendering + short note. Names: transliterate per Ukrainian orthography rules
  (§ German/Hungarian onomastics); never localize unless conventional
  (e.g. `Wien → Відень`). Output per the `TermProposal` Pydantic contract.
- **3.3 Character registry (SMART model, map-reduce).** Chapter-by-chapter map
  over PERSON terms that occur in the chapter plus
  `evidence_sentences_per_person` sentences each (prefer closed gender-cue
  hits); never send chapter text (ADR 0015). SMART returns canonical name,
  gender, aliases, role. Deterministic reduce merges drafts that share a lemma,
  canonical name, or alias. Gender is REQUIRED for generation (Ukrainian
  past-tense verbs and adjectives are gendered); unresolved gender is stored as
  `unknown` for 3.6, never guessed.
- **3.4 Address matrix.** Heuristics first on speech-opener paragraphs: T/V from
  closed cue lists, speaker after a speech verb, addressee as vocative
  (ADR 0016). SMART only when both endpoints are known and the form is not.
  Evidence is `evidence_sentences_per_pair` sentences, never the chapter.
  Unanswered or mixed T+V → `tv_form=MIXED`. Do not aim for full coverage;
  unidentified speakers are dropped. Generation later carries a scene-level
  directive for MIXED pairs instead of a pair rule.
- **3.5 Chapter summaries + book style card.** Per chapter: 3–5 sentence Ukrainian
  summary (map). Book style card (reduce): epoch, setting, register, narration
  person/tense, tone, translation directives (e.g. "archaic flavour, but glosses in
  modern Ukrainian"). Store in DB + `books/{slug}/style_card.md`.
- **3.6 Human review gate.** `frank review-terms <slug>` exports termbase +
  characters + address matrix to a single editable TOML; `frank approve <slug>`
  imports it back and sets `approved=true`. Pipeline REFUSES to run Phase 5 while
  unapproved terms exist (overridable with `--yolo` flag for experiments).

**Acceptance:** for the fixture book, termbase covers every PERSON/PLACE occurring
≥ 3 times; every character has a gender; export→edit→import round-trip preserves data.

---

## Phase 4 — Context Assembly (library, no pipeline step)

**Goal:** one pure function used by Phase 5:
`assemble_context(paragraph_id) -> PromptContext`.

Priority-ordered budget (default total ≤ 1800 tokens, configurable; truncate from
the bottom):

1. **Task instruction** (from `infrastructure/llm/prompts/`, versioned).
2. **Termbase slice** — only terms whose surface forms/lemmas occur in THIS
   paragraph (exact match over token lemmas). Hard requirement: rendered as
   "MUST translate X as Y".
3. **Speaker context** — if the paragraph contains dialogue: involved characters
   (name, gender, UK rendering) + their T/V forms toward each other.
4. **Rolling window** — previous 3 sentences of the SAME chapter: original + their
   generated idiomatic Ukrainian translation. Guaranteed available because Phase 5
   processes paragraphs strictly sequentially WITHIN a chapter (parallelism is
   across chapters only). At a chapter start: empty. The rolling-window content
   hash is part of the paragraph's cache key, so context stays deterministic and
   cache-safe.
5. **Local scene brief** — running 2-sentence summary of the current chapter so far
   (updated every K paragraphs by the FAST model; cached).
6. **Chapter summary** (from 3.5).
7. **Style card digest** (from 3.5, first 5 lines).

Determinism requirements: same inputs → byte-identical context (stable ordering,
stable truncation). Log the assembled context alongside every LLM call.

**Acceptance:** property tests: budget never exceeded; termbase slice contains
exactly the terms present in the paragraph; snapshot test of one assembled prompt.

---

## Phase 5 — Generation

**Goal:** per-sentence Frank data via two model tiers.

Output contract per sentence — a Pydantic model in
`infrastructure/llm/schemas.py`, whose `model_json_schema()` is passed as
`response_format`; converted to the domain `FrankRecord` by the anti-corruption
layer. Note the two-level
unit translation — classic Frank style is "natural rendering: «word-for-word»"
when they differ; `word_for_word_uk` is null when the natural rendering IS literal:

```json
{
  "sentence_id": "…",
  "units": [
    {"source_span": [0, 4], "natural_uk": "…", "word_for_word_uk": "…|null"}
  ],
  "idiomatic_uk": "…",
  "word_notes": [
    {"surface": "…", "lemma": "…", "morph_note_uk": "…", "gloss_uk": "…"}
  ]
}
```

Steps:

- **5.1 FAST pass.** Processing is strictly SEQUENTIAL in book reading order —
  no chapter parallelism (session-based operation, see 5.5; sequential order also
  makes the rolling window trivially available). ONE LLM call per PARAGRAPH,
  returning an array of per-sentence objects —
  never one call per sentence: the assembled context is per paragraph, and
  re-sending it per sentence wastes prefill and loses intra-paragraph coherence.
  Call input: paragraph sentences, their sense-unit spans (2.3), morphology of
  tokens with gloss_plan.gloss=true (2.2/2.4).
  The model translates units, writes idiomatic sentence translations, and fills
  word notes from provided lemma+morph (it explains, it does not analyze).
- **5.2 Validation loop (deterministic, no LLM).** Implemented as pure predicate
  functions in `domain/services/validation.py`, called inline during generation
  AND exposed as
  Dagster **asset checks** in Phase 7 (so a red check in the UI names the exact
  failing rule instead of hiding it in a traceback). Checks per sentence:
  schema-valid; every sense unit has `natural_uk`; every token with
  gloss_plan.gloss=true has a word note (word_note lemma is OVERWRITTEN from the
  DB — never trust the model's echo); every termbase surface form in the sentence
  is rendered with the approved translation (substring/lemma match on outputs);
  output-language guard: character-set check — reject any output containing
  Russian-only letters [ыэъё] or lacking Ukrainian markers on longer spans
  (local models drift into Russian; langdetect alone is unreliable on short
  sentences); length ratio of `idiomatic_uk` to source within [0.6, 2.0]; correct
  T/V pronouns in dialogue where the address matrix says so. On failure: retry
  FAST with the failure appended as explicit correction, max 2 attempts.
- **5.3 SMART escalation.** Sentences still failing after 5.2, plus sentences
  flagged hard (subjunctive/irrealis, long hypotaxis, idiom hits) go to SMART with
  the same contract. Persist which tier produced the final result.
- **5.4 Back-translation QA (sampled).** For a configurable sample (default 10% +
  all SMART-escalated): back-translate `idiomatic_uk` to source language using a
  model DIFFERENT from the one that produced the translation (same-model
  back-translation correlates errors); compute chrF against original; below
  threshold → mark paragraph `needs_human` (advisory only — chrF punishes
  legitimate paraphrase; it does not block the pipeline; listed in the final
  report).
- **5.5 Sessions, passages & resume.** The operational unit is the PASSAGE
  (from 2.5). Designed for short work sessions, not overnight runs: the
  generation step takes a time/passage budget from config (run config in Dagster,
  e.g. `max_minutes`, `max_passages`), processes passages in book order and stops
  CLEANLY at the next passage boundary when the budget is reached; interruption
  also finishes the current passage. A passage is COMPLETE only when all its
  paragraphs passed validation (5.2/5.3); completion is recorded per passage.
  Paragraph-level cache keyed by (paragraph_hash, prompt_version, model,
  termbase_version, rolling_context_hash); a rerun skips completed work.
  `frank status <slug>` shows passages done / total and passages-per-hour.

**Acceptance:** fixture chapter generates end-to-end; a budget of 3 passages
completes exactly 3 and stops cleanly; kill -9 mid-run and rerun produces identical output without
re-calling the LLM for finished paragraphs; termbase-consistency check has zero
violations in final output by construction.

---

## Phase 6 — Rendering (docx)

**Goal:** classic Frank-styled `.docx` via `python-docx`. Deterministic; no LLM.

Frank layout — the doubling unit is the PASSAGE (group of paragraphs from 2.5),
NOT a single paragraph:

1. **Adapted passage:** all paragraphs of the passage in order; within each
   sentence, interleave: original unit text (black) + `(` + `natural_uk` (green)
   [+ `: «word_for_word_uk»` (green) when present] [+ `; lemma – gloss_uk` items
   and grammar note (green italic) for planned glosses] + `)`. Punctuation of the
   original preserved. Word-note lemmas come from the DB (`reunited_lemma` when
   set), never from model output.
2. After the whole adapted passage: blank line, then the **unadapted passage** —
   all its paragraphs verbatim (black), original paragraph breaks preserved.

Steps:

- **6.1 Style sheet.** Named character styles in the docx template
  (`templates/frank.docx`): `FrankOriginal` (black), `FrankTranslation` (green
  RGB 0x2E7D32), `FrankGloss` (green italic), `FrankNote` (green italic),
  `FrankUnadapted` (black). Serif font (Georgia/PT Serif), 1.35 line spacing,
  justified. Title page with book metadata + source/license note. Chapter headings
  as Heading 1.
- **6.2 Renderer (incremental by design).** Pure function DB → docx over ALL
  passages completed so far — `frank render <slug>` after any session yields a
  valid, readable partial book ending with a discreet marker line
  ("— згенеровано до пасажу N —"). Re-rendering the whole partial book each time is
  fine (deterministic and fast, no LLM). Also handles: quotes/dashes per Ukrainian
  typography inside translations, keeping original typography in source runs;
  widow/orphan control via paragraph properties; page break before chapters.
- **6.3 Conversion smoke test.** `frank render <slug> --docx out.docx`; verify the
  file also converts via `pandoc` to epub/html without errors (conversion itself is
  out of scope for v1, only the smoke test).

**Acceptance:** golden docx for the fixture chapter opens in Word/Pages with correct
colors/styles; a native-speaker eyeball check confirms the layout matches the
reference screenshot pattern.

---

## Phase 7 — Orchestration & ops (Dagster)

**Goal:** unattended ~2-hour sessions where a crash is visible, classified, and
restartable **step-by-step** without redoing finished work.

**Why Dagster (decision, do not re-litigate):** this project accumulates artifacts
and resumes mid-way, i.e. it is a problem about STATE, not about scheduling
actions. Dagster's assets / partitions / asset-checks map 1:1 onto our phases,
chapters and validations, and "materialize just this one asset" IS the
"restart only the failed step" requirement. (Prefect 3 is simpler but models runs
of actions rather than freshness of artifacts; Temporal is the right tool at a
scale this project will never reach.)

**Parallelism boundary — the most important rule in this phase:**

| Phase | Asset shape | Parallel? |
|---|---|---|
| 1 Ingest | one asset per book | n/a |
| 2 Segment / morphology | partitioned by chapter | YES |
| 3 Analysis (termbase, characters, summaries) | per-chapter assets + reduce assets | YES |
| 5 Generation | partitioned by chapter, executed SEQUENTIALLY in chapter order | NO |
| 6 Render | one asset per book | n/a |

Generation must stay sequential because the rolling window (Phase 4) consumes
translations of immediately preceding sentences. Set concurrency 1 on the
generation asset; parallelism elsewhere is free.

Steps:

- **7.1 Asset graph.** `ingest → segment → analyze → generate → render`. Partition
  key = chapter index (**never passage** — thousands of partitions per book would
  drown the UI and per-partition overhead would rival the work itself).
  Resources: LLM client, book DB, config. RetryPolicy on LLM-touching assets
  (max_retries=2, delay, exponential backoff) — combined with the
  content-addressed cache, a retry re-walks completed passages from cache in
  seconds and continues exactly where it stopped.
- **7.2 Asset checks.** Expose the `domain/services/validation.py` predicates from 5.2 as asset
  checks on the generation asset (termbase consistency, Ukrainian-language guard,
  gloss coverage, sense-unit coverage, T/V compliance) plus one on segmentation
  (every token has a lemma). Consistency checks are BLOCKING; back-translation
  chrF (5.4) is ADVISORY.
- **7.3 Throughput controls.** Concurrency 1 for generation, configurable for
  analysis; token accounting; passages-per-hour and session ETA both in
  `frank status` and as asset metadata so the Dagster UI shows live progress.
- **7.4 Session report.** Written at the end of every run to the `run` row (0.5.1)
  and to asset metadata: passages completed, tier split (FAST vs SMART %), failed checks,
  `needs_human` additions with previews, tokens/time. Notification fires here
  (0.5.3). `frank report <slug>` shows the cumulative book-level picture.
- **7.5 One execution path.** Generation is started ONLY by materializing the
  generation asset in Dagster — there is no second runner and no `frank generate`
  command. The CLI keeps only hands-on commands: `ingest`, `inspect`,
  `annotate`, `review-terms`, `approve`, `render`, `status`, `report`, `bench`.
  Step functions stay pure functions over DB + cache with NO Dagster imports
  inside `frank/steps/` (so they remain unit-testable), but only one caller
  drives generation.

**Acceptance:** a ~2-hour session advances the book and can be interrupted at any
moment without loss; there is exactly one way to start generation; killing the model server mid-run yields a red asset with
`error_class=model_unreachable` plus a notification; re-materializing ONLY that
chapter partition afterwards completes it without re-calling the LLM for already
finished passages; `frank render` immediately afterwards produces a valid partial
docx.

---

## Phase 8 — Quality iteration (post-v1, keep as backlog)

- Human feedback loop: `frank fix <slug> <paragraph_id>` opens the JSON for manual
  edit, re-renders only affected output.
- Per-book fine-grained frequency lists → adaptive gloss density (later chapters
  gloss less, as in real Frank books).
- Anki export of `word_note` entries (reuse the existing genanki know-how from the
  Memory Castle project).
- EPUB/HTML renderers as first-class outputs.
