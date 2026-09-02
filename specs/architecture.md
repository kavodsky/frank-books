# Architecture

Code organization follows **DDD principles, applied selectively**. Read the
"Deliberately NOT used" section before adding patterns — the goal is a clear
domain, not a demonstration of DDD.

## Ubiquitous language (use these exact names in code)

| Term | Meaning |
|---|---|
| **Book** | One source text being adapted |
| **Chapter** | Structural division of a book; the parallelism / partition unit |
| **Passage** | Group of consecutive paragraphs; the Frank DOUBLING unit and the unit of visible progress |
| **Paragraph** | Unit of LLM call and of caching |
| **Sentence** | Unit of the generated Frank record |
| **SenseUnit** | Clause-level span of a sentence that receives its own translation |
| **WordNote** | A single `lemma – gloss` explanation attached to a sentence |
| **GlossPlan** | Per-token decision whether a word gets explained, with a reason |
| **Termbase** | Approved renderings of names, places, idioms for one book |
| **CharacterRegistry** | Characters with gender, aliases, and T/V address forms |
| **StyleCard** | Book-level translation directives (epoch, register, tone) |
| **PromptContext** | Assembled, budgeted context for one paragraph's generation |
| **FrankRecord** | Full generated result for one sentence |
| **Adaptation** | The whole act of turning a Book into a Frank book |

Never introduce synonyms (no "chunk", "segment", "block", "fragment" for Passage
or Paragraph).

## Repository layout

This tree is canonical. Create directories only when the phase that needs them
arrives; do not pre-create empty packages.

```
frank-books/
  README.md                  # human: what it is, setup, workflow
  AGENTS.md                  # AI agents: entry point + non-negotiables
  pyproject.toml             # uv-managed; project script `frank`
  uv.lock                    # committed
  .pre-commit-config.yaml
  .importlinter              # layer-boundary contract (domain imports nothing external)
  config.example.toml        # committed template
  config.toml                # local, gitignored: model names, ports, budgets
  process-compose.yaml       # model servers + dagster dev

  specs/                     # all binding specifications live here
    mission.md
    architecture.md          # this file
    tech-stack.md
    roadmap.md
    linguistics.md
    adr/
      0001-deterministic-pipeline-not-agents.md
      ...                    # append-only, one decision per file

  data/                      # static linguistic assets, committed
    de_frequency_top.txt
    hu_frequency_top.txt
    de_separable_prefixes.txt
    de_ambiguous_prefixes.txt
    hu_igekoto.txt
    uk_exonyms.toml          # conventional Ukrainian place/person forms
    de_gender_cues.txt       # titles/pronouns that rank character evidence
    hu_gender_cues.txt
    address_cues.toml        # T/V pronouns and speech verbs (roadmap 3.4)
    uk_calques.toml          # Russian-calque blacklist (validation)
    de_false_friends.toml
    hu_false_friends.toml

  templates/
    frank.docx               # style template: FrankOriginal / FrankTranslation / …

  gold/                      # benchmark fixtures, committed
    de_sample.jsonl          # 50+ sentences w/ reference Ukrainian
    hu_sample.jsonl
    lemma_disputed.jsonl     # lemma-arbitration mini-benchmark
    reunion.jsonl            # separable-verb / igekötő pairing mini-benchmark

  books/                     # ALL runtime output, gitignored
    <slug>/
      book.toml              # per-book overrides: chapter regexes, thresholds
      raw/                   # untouched fetched bytes
      book.db                # SQLite (one per book)
      cache/<paragraph_hash>/<step>.json
      logs/                  # JSONL: prompts, responses, latency, model
      style_card.md
      out/                   # rendered .docx

  frank/
    domain/            # pure Python. NO imports of sqlalchemy, httpx, dagster, spacy
      model/           # entities & value objects (Pydantic BaseModel / dataclasses)
        book.py        #   Book, Chapter, Passage, Paragraph, Sentence
        annotation.py  #   Token, Morphology, SenseUnit, GlossDecision
        reunion.py     #   VerbParticle, PrefixInventory, ReunionCandidate
        frank.py       #   FrankRecord, SenseUnitTranslation, WordNote
        layout.py      #   LayoutBook / LayoutRun tree (docx-ignorant)
        termbase.py    #   Term, Character, AddressPair, TvForm, StyleCard
        context.py     #   PromptContext and its budget sections
      services/        # pure domain logic — the real value of this layer
        segmentation.py    # sense-unit rules over Token dep/head (no spaCy)
        gloss_planning.py  # the stateful first-occurrence / quota algorithm
        passage_grouping.py
        term_candidates.py
        term_renderings.py
        character_evidence.py
        character_merge.py
        address_detect.py
        address_merge.py
        chapter_briefs.py
        style_card.py
        termbase_review.py
        termbase_review_toml.py
        reunification.py   # separable verb / igekötő pairing rules
        context_assembly.py# budgeted assembly (Phase 4) — pure function
        validation.py      # all Phase 5.2 predicates, pure
        hard_sentences.py  # irrealis / hypotaxis / idiom → SMART
        layout.py          # adapted/unadapted passage doubling (Phase 6)
      ports/           # abstract interfaces (Protocol / ABC) the domain needs
        repositories.py    # BookRepository, TermbaseRepository, FrankRecordRepository, GlossPlanRepository, RunRepository
        linguistics.py     # LinguisticAnalyzer (tokenize/parse/lemmatize/NER)
        translator.py      # FrankGenerator (paragraph -> list[FrankRecord])
        notifier.py

    application/       # use cases: orchestrate domain + ports. No framework code
      ingest_book.py
      annotate_chapter.py
      build_termbase.py
      build_characters.py
      build_address.py
      build_style.py
      generate_passages.py     # takes a budget, loops passages, calls validation
      render_book.py
      review_termbase.py

    infrastructure/    # all the dirty details; implements the ports
      persistence/
        tables.py            # SQLAlchemy 2.0 DeclarativeBase, Mapped[] columns
        mappers.py           # table row <-> domain object (explicit, boring, tested)
        repositories.py      # concrete repository implementations
        cache.py             # content-addressed step cache
      llm/
        client.py            # OpenAI-protocol HTTP client (httpx + tenacity)
        schemas.py           # Pydantic contracts for LLM I/O; source of response_format
        generator.py         # implements FrankGenerator port; ANTI-CORRUPTION LAYER:
                             #   translates LLM JSON <-> domain objects. Domain never
                             #   sees a raw model response.
        prompts/             # versioned prompt templates (jinja2)
      nlp/
        german.py            # spaCy pipeline -> ParsedSentence VOs
        hungarian.py         # HuSpaCy + emmorph -> ParsedSentence VOs
        lemma_arbiter.py     # dual-lemmatizer + batched LLM arbitration
        reunion_arbiter.py   # separable-verb / igekötő SMART validation
        term_translator.py   # batched SMART term renderings
        character_mapper.py  # SMART map of PERSON evidence → Character drafts
        address_resolver.py  # SMART T/V for unresolved AddressPair rows
        style_builder.py     # SMART chapter summaries + StyleCard reduce
        prefixes.py          # closed particle lists from data/
      sources/
        txt.py, html.py, epub.py   # local files only (ADR 0013)
      rendering/
        docx_renderer.py     # python-docx; consumes domain objects only
      notify/
        macos.py

    interfaces/        # entry points. Thin. No logic
      cli.py           # Typer: ingest, inspect, annotate, terms, review-terms, approve, render, status, report, bench
      dagster_defs.py  # assets, asset checks, resources, RetryPolicy — calls application use cases

    config.py        # pydantic-settings
```

Tests mirror the layers, so a failing path tells you which layer broke:

```
  tests/
    unit/            # domain only: no DB, no model server, no spaCy. Marked `unit`
      test_gloss_planning.py
      test_context_assembly.py
      test_validation.py
      test_reunification.py
      test_segmentation.py
      test_passage_grouping.py
      test_term_candidates.py
      test_term_renderings.py
      test_character_evidence.py
      test_character_merge.py
      test_address_detect.py
      test_address_merge.py
      test_chapter_briefs.py
      test_style_card.py
      test_termbase_review.py
      test_validation.py
      test_hard_sentences.py
      test_generate_passages.py
      test_layout.py
    integration/     # infrastructure against real SQLite / a mocked LLM server
      test_repositories.py
      test_llm_generator.py
      test_generation_session.py
      test_docx_render.py
      test_ingest.py
      test_termbase.py
      test_term_translate.py
      test_character_map.py
      test_address_matrix.py
      test_style.py
      test_review_round_trip.py
    e2e/             # one fixture chapter through the whole pipeline
      test_fixture_chapter.py
    architecture/
      test_layer_boundaries.py   # asserts domain has no external imports
    fixtures/
      chapters/      # small real excerpts (de + hu), committed
      snapshots/     # syrupy snapshots
```

Notes:

- One SQLite file **per book**, not one global DB — books are independent, and a
  corrupted or abandoned book is deleted by removing its directory.
- `books/` is entirely disposable: everything in it is re-derivable from `raw/`
  plus the committed specs, config and data.
- Prompts live in `frank/infrastructure/llm/prompts/` (versioned with the code
  that sends them), NOT in a top-level `prompts/` directory — a prompt change is
  a code change and must invalidate the cache key.
- No top-level `schemas/`: JSON schemas are generated from Pydantic models.
- No `scripts/` directory: one-off scripts become CLI commands or disappear.

## Rules for implementers

1. **`domain/` imports nothing external** except `pydantic`/`typing`/stdlib. A test
   asserting this (import-linter or a simple AST scan) is part of Phase 0.
2. **Domain objects are persistence-ignorant.** SQLAlchemy tables live in
   `infrastructure/persistence/tables.py`; conversion happens in `mappers.py`.
   Do NOT use SQLModel — merging table and domain model defeats this boundary.
3. **Ports are declared where they are needed (domain), implemented in
   infrastructure.** Application use cases receive port implementations by
   constructor injection; Dagster resources wire them in `interfaces/`.
4. **LLM I/O contracts are Pydantic models in `infrastructure/llm/schemas.py`**, and
   the JSON schema sent as `response_format` is generated from them via
   `model_json_schema()`, then made OpenAI-strict (ADR 0014). There is no
   hand-written `schemas/*.json` directory.
5. **The anti-corruption layer is mandatory:** if a model returns garbage, malformed
   fields, or hallucinated lemmas, that is handled in `llm/generator.py`. Domain
   objects are always valid by construction.
6. **Pure domain services are where the interesting logic lives** (gloss planning,
   context assembly, validation predicates, reunification rules). They are
   unit-tested without a database, without a model server, and without spaCy.
7. **No logic in `interfaces/`.** A Dagster asset body is: build ports from
   resources → call one application use case → emit metadata.
8. **One way to do anything** (see roadmap's simplicity rule). No repository base
   class hierarchies, no generic `BaseService`, no dependency-injection framework.

## Code style & readability (non-negotiable)

Readability is a primary requirement, not a nicety. Optimize for the owner
returning to this code in three months.

**Functions**

- One function does ONE thing at ONE level of abstraction. Target ≤ 20 lines,
  hard ceiling 40 (excluding docstring). If it needs a comment saying "now we do
  X", then X is a function.
- Max 4 parameters; beyond that pass a value object (`PromptContext`,
  `GlossPlanConfig`).
- No boolean flag parameters that switch behaviour (`process(x, strict=True)`) —
  write two named functions.
- Guard clauses over nested conditionals; max nesting depth 3.
- Name by intent, not mechanics: `should_gloss(token)` not `check_token_flag()`;
  `reunite_separable_verb()` not `handle_prefix()`.
- Pure by default. Functions touching DB, network or clock are clearly named and
  live in `infrastructure/` or `application/`, never mixed into domain rules.

**Modules**

- One module = one coherent responsibility, ≤ ~300 lines. When a module grows,
  split by concept, not by size (`gloss_planning.py` → `gloss_rules.py` +
  `gloss_quota.py` is fine; `gloss_planning_2.py` is not).
- No `utils.py`, `helpers.py`, `common.py`, `misc.py`. Every function has a real
  home.
- Explicit imports only; no wildcard imports.

**Types & data**

- Full type hints everywhere; `from __future__ import annotations`.
- Prefer value objects over primitives for domain concepts: `ChapterIndex`,
  `Lemma`, `TvForm` — not bare `int`/`str`. Enums for every closed set
  (`GlossReason`, `TermKind`, `ErrorClass`, `ModelTier`).
- Domain objects immutable (`frozen=True`) unless mutation is the point.
- No dicts as ad-hoc records in domain code. A dict crossing a function boundary
  is a missing model.

**Errors**

- Domain raises domain exceptions (`TermbaseNotApproved`, `ValidationExhausted`),
  never `HTTPError` or `OperationalError`. Infrastructure translates.
- One hierarchy rooted at `FrankError`; every raise site sets an `ErrorClass`
  (roadmap 0.5.1).
- No bare `except:`; no `except Exception` without re-raising or classifying.

**Comments & docs**

- Comments explain WHY (a linguistic reason, a rule of the Frank method), never
  WHAT. Docstrings on public domain services: one line of purpose plus the rule
  implemented, with a concrete example for anything language-specific.
- Any threshold or magic number lives in config with a name, never inline.

## Patterns: where they earn their place

Use these where listed. Do NOT introduce patterns not on this list, and do not
apply a listed pattern outside its listed use — pattern-hunting is a defect here.

| Pattern | Where | Why |
|---|---|---|
| **Ports & Adapters** | `domain/ports/` + `infrastructure/` implementations | The backbone of the layering |
| **Strategy** | `LinguisticAnalyzer` per language (`german.py`, `hungarian.py`); FAST/SMART tier routing | The only real axis of variation in the project |
| **Adapter** | `infrastructure/sources/*` (TXT, HTML, EPUB) | Each file format is genuinely different |
| **Anti-Corruption Layer** | `infrastructure/llm/generator.py` | Untrusted model output must not reach the domain |
| **Repository** | one per persisted concept, plain gateway | Persistence ignorance; no base-class hierarchy |
| **Value Object** | `Lemma`, `SenseUnit`, `PromptContext`, `TvForm` | Kills primitive obsession; self-documenting signatures |
| **Specification / named predicates** | `domain/services/validation.py` — each 5.2 check is a named predicate, composed into a list | Individually testable AND individually reportable as Dagster asset checks |
| **Pipeline of pure functions** | `annotate → plan glosses → group passages`; the validation chain | Matches the domain literally; no framework needed |
| **Factory function** | building analyzers / repositories / ports from config | Plain functions, not factory classes |

**Explicitly do not use:** inheritance for code reuse (compose instead; ABCs only
for ports), Singleton, Service Locator, generic `BaseService`/`BaseRepository`
hierarchies, decorators that hide control flow, metaclasses, `getattr`-dispatch
magic, DI frameworks, `Manager`/`Helper`/`Processor`-suffixed classes.

**A class is justified only when it holds state or implements a port.** Otherwise
write a function — most of `domain/services/` should be module-level functions.

## Documentation rules

Docs are part of the code, not an afterthought. Principle: **one fact, one place** —
if something is specified in a doc, code must not re-explain it, and no doc may
duplicate another.

Specifications (binding, read before coding) live in `specs/`. `README.md` and
`AGENTS.md` sit at the repo root because they are entry points. There is no
`docs/` directory — a second documentation folder is exactly how two versions of
the same fact appear.

| Document | Owns | Updated when |
|---|---|---|
| `README.md` | how to install and run, for a human | setup or CLI changes |
| `AGENTS.md` | entry point + non-negotiables for AI agents | a rule for agents changes |
| `specs/mission.md` | goal, principles, success criteria | scope changes |
| `specs/architecture.md` | layering, ubiquitous language, style, patterns, docs rules | structure or conventions change |
| `specs/tech-stack.md` | pinned tools + rejected alternatives | a dependency changes |
| `specs/roadmap.md` | phases, steps, acceptance criteria | a step is added or reshaped |
| `specs/linguistics.md` | language rules and their reasoning | a linguistic rule is learned or overturned |
| `specs/adr/NNNN-*.md` | one decision each: context, decision, alternatives, consequences | a decision is made or superseded |

Rules:

1. **Every non-obvious decision gets an ADR** before or with the code. Format:
   context / decision / alternatives rejected / consequences, ~20 lines, dated.
   ADRs are append-only: to change a decision, write a new one marked
   "supersedes NNNN" and set the old one's status to superseded. Never edit
   history.
2. **Linguistic reasoning goes to `specs/linguistics.md`**, not into code comments.
   The code comment says WHY in one line and points to the rule.
3. **Docstrings on public domain services** state the rule implemented plus a
   concrete German/Hungarian example. Where an example is exact, write it as a
   doctest so pytest catches drift.
4. **Generated, never hand-written:** the DB schema diagram and the asset graph
   (`frank docs schema`, Dagster UI). Do not paste schemas into prose — they rot.
5. **A doc that contradicts the code is a bug** of the same severity as a failing
   test. Fix it in the same commit as the change, not "later".
6. Keep prose short and declarative. No changelog sections inside docs (git has
   that), no aspirational "we plan to" content — roadmap owns the future tense.

## Deliberately NOT used

- **Aggregates with transactional boundaries / aggregate roots.** Single user,
  single process, sequential generation — there is no contention to protect.
  Repositories are plain persistence gateways.
- **Domain events / event sourcing / CQRS.** Progress tracking is a `run` table and
  Dagster's own run log; that is enough.
- **Bounded contexts as separate packages.** One context (Adaptation). Splitting it
  would be organizational theater.
- **Generic Unit of Work abstraction.** SQLAlchemy sessions used directly inside
  repository implementations.

The point of this document is a clean dependency direction and a shared vocabulary,
not pattern completeness. If a DDD pattern is not listed above, do not add it
without an explicit request.
