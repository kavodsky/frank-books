# AGENTS.md

Entry point for AI coding agents. Read this fully before writing any code.

## What this project is

**frank-books** turns public-domain German and Hungarian books into reading books
formatted after the **Ilya Frank method**, with Ukrainian translations and glosses.
Local LLMs served over the OpenAI protocol on localhost; everything offline.

## Read in this order (binding specs)

1. `specs/mission.md` — goal, principles, success criteria.
2. `specs/architecture.md` — **layering, ubiquitous language, code style,
   allowed patterns**. Binding for every file you write.
3. `specs/tech-stack.md` — pinned tools; do not substitute.
4. `specs/roadmap.md` — phases and steps. Implement **in order**.
5. `specs/linguistics.md` — language rules (transliteration, T/V, igekötő glossing).
6. `specs/adr/` — decisions already made, with rationale. Do not re-litigate them.

If a spec and your instinct disagree, the spec wins. If two specs disagree, stop
and ask — do not pick one silently.

## Commands

```bash
uv sync                       # install
uv run pytest                 # tests
uv run pytest -m unit         # domain-only tests (no DB, no model server, no spaCy)
uv run ruff check --fix .     # lint
uv run ruff format .          # format
uv run mypy frank/domain frank/application   # strict typing where it matters
uv run lint-imports           # layer-boundary check (domain imports nothing external)
uv run frank --help           # hands-on CLI
process-compose up            # model servers + dagster
dagster dev                   # UI; generation is started ONLY from here
```

Before finishing any task: lint, format, mypy, layer check, and tests must pass.

## Non-negotiables (most common failure modes for agents)

1. **`frank/domain/` imports nothing external.** No sqlalchemy, httpx, dagster,
   spacy, python-docx. There is a test for this; it will fail you.
2. **Use the ubiquitous language exactly** (`specs/architecture.md`): Book,
   Chapter, Passage, Paragraph, Sentence, SenseUnit, WordNote, GlossPlan,
   Termbase, PromptContext, FrankRecord. Never invent synonyms like chunk,
   segment, block, fragment.
3. **Do not add patterns outside the allowed table** in `specs/architecture.md`. No
   Singleton, no `BaseService`, no DI framework, no `Manager`/`Helper` classes,
   no inheritance for code reuse.
4. **A class is justified only if it holds state or implements a port.**
   Otherwise write a function.
5. **LLMs explain, they do not analyze.** Morphology, lemmas, sense-unit
   segmentation and gloss decisions come from analyzers and deterministic rules.
   Never "just ask the model" for a lemma or a segmentation.
6. **Validation is deterministic code**, never an LLM judging its own output.
7. **Generation is sequential.** Do not parallelize the generation asset; the
   rolling-window context depends on preceding sentences.
8. **No second way to do anything.** One execution path for generation (Dagster
   asset). Do not add a parallel CLI runner, an alternative config source, or a
   "quick mode".
9. **Never invent thresholds inline.** Every number goes to config with a name.
10. **Do not create `utils.py`, `helpers.py`, `common.py`.**

## When you are unsure

- Missing a linguistic rule → add a question to `specs/linguistics.md` under
  "Open questions", implement the conservative option, and say so in your summary.
- A step seems to need a new dependency → do not add it; propose it and explain
  why the pinned stack cannot cover the need.
- A decision feels wrong → check `specs/adr/` first; if it is there, follow it.
  If not, write a new ADR proposing the change instead of coding around it.

## Definition of done for a roadmap step

- Code in the right layer, following architecture.md.
- Unit tests for domain logic (no I/O), plus a test for the step's acceptance
  criterion from roadmap.md.
- Lint, format, mypy, layer check green.
- Docstring on every public domain service stating the rule it implements, with a
  concrete German/Hungarian example where language-specific.
- If the step changed a schema, a decision, or a linguistic rule: update the
  relevant doc in the same commit.
