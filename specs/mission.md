# Mission

## What we are building

**frank-books** is a local, fully offline pipeline that turns public-domain books in
**German** and **Hungarian** into reading books formatted after the **Ilya Frank reading
method**, with all translations, literal glosses, and commentary written in **Ukrainian**.

The Frank method presents every passage of a book **twice**:

1. **Adapted passage** — the original text, split into short sense units (clauses),
   where each unit is immediately followed by a parenthesized Ukrainian literal
   translation and, where useful, word-level glosses (`lemma – translation`) and short
   grammar notes. Translations and glosses are rendered in green; the original text
   stays black.
2. **Unadapted passage** — the very same passage repeated as plain original text,
   with no insertions.

The reader absorbs vocabulary and grammar through massive comprehensible input,
without ever opening a dictionary.

## Why

Commercial Frank-method books exist for a handful of language pairs and titles.
They do not exist for Hungarian→Ukrainian at all, and the German→Ukrainian selection
is tiny. Local LLMs plus deterministic tooling can generate such books on demand from
free digital libraries (e.g. mek.oszk.hu, Projekt Gutenberg-DE), for personal study.

## Who it is for

- Primary user: the project owner, a developer learning German and Hungarian
  (native Ukrainian speaker), running everything locally on a Mac (M5 Max, 128 GB)
  with Ollama / MLX.
- The pipeline is operated from the command line; no web UI is required in v1.
- Models are served locally and reached over the OpenAI protocol on localhost
  ports; no cloud APIs.
- Operating model: short sessions (~2 hours), passage-by-passage progress; the
  unit of visible progress is the passage (the Frank doubling unit, a group of
  consecutive paragraphs).

## Non-negotiable principles

1. **Deterministic pipeline, not autonomous agents.** Every stage is a known step in
   a DAG orchestrated by Dagster (assets partitioned by chapter). LLMs are called
   inside steps with strict JSON-schema outputs. LLMs never decide pipeline
   structure, never touch rendering, and never see the whole book.
2. **Consistency is enforced by code, not by prompting.** Named entities and key terms
   are translated once (termbase), injected into prompts, and verified after
   generation by deterministic checks with automatic retry.
3. **Context-aware translation.** Every generation call receives assembled context
   (book style card, character registry with genders and T/V address forms, chapter
   summary, rolling window of preceding sentences, termbase slice). See roadmap
   Phase 3 and the Context Assembly spec.
4. **Morphology comes from analyzers, not LLMs.** spaCy (German) and HuSpaCy
   (Hungarian) provide lemmas and morphological features; LLMs only explain them.
5. **Everything is resumable and cached.** Any step can crash and be re-run without
   regenerating finished work; a failed step is re-materialized on its own, and
   errors are classified (not grepped out of logs). Unit of caching: paragraph;
   unit of visible progress: passage.
6. **Primary output is `.docx`** styled in classic Frank colors; other formats are
   derived from it later.
7. **Only public-domain / freely licensed source texts** are processed.

## Success criteria (v1)

- One full Hungarian book and one full German book generated end-to-end into `.docx`,
  accumulated over ordinary ~2-hour work sessions (no overnight runs required):
  every session ends with a valid, readable partial book that has grown by passages.
- 100% of termbase-listed names rendered identically across the whole book
  (verified automatically).
- Every original sentence is covered by a literal translation; every content word of
  the adapted passage appears in a gloss or inside a translated unit.
- A human spot-check of 30 random paragraphs per book finds no more than 2 with a
  meaning-distorting translation error.
