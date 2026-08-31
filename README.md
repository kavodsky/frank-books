# frank-books

Generates reading books in the **Ilya Frank method** from public-domain German and
Hungarian texts, with Ukrainian translations and glosses. Runs entirely locally
against LLMs served on localhost.

Output: `.docx` in classic Frank styling (original in black, translations and
glosses in green), convertible to EPUB/HTML with pandoc.

## Status

See `specs/roadmap.md` for phases and what is implemented.

## Requirements

- macOS on Apple Silicon (developed on M5 Max, 128 GB)
- Python ≥ 3.12, [uv](https://docs.astral.sh/uv/)
- Two local model servers exposing the OpenAI protocol (Ollama / mlx-lm /
  LM Studio / llama.cpp) — a fast tier and a large tier
- pandoc (optional, for format conversion)

## Setup

```bash
uv sync
uv run python -m spacy download de_core_news_lg
# hu_core_news_lg (HuSpaCy, spaCy 3.8): https://huggingface.co/huspacy/hu_core_news_lg
cp config.example.toml config.toml   # set model names, ports, language pair
process-compose up                   # model servers + dagster
```

## Workflow for one book

```bash
uv run frank ingest path/to/book.html --slug pecsenye --lang hu
uv run frank inspect pecsenye                    # sanity report; fix book.toml if needed
uv run frank annotate pecsenye                   # sentence split (spaCy / HuSpaCy)
# morphology + analysis: later roadmap steps, then Dagster for generation
uv run frank review-terms pecsenye > terms.toml   # export termbase + characters
$EDITOR terms.toml                              # ~15 min: check names, genders, T/V
uv run frank approve pecsenye < terms.toml
# generate: materialize the generation asset in Dagster with a session budget
uv run frank render pecsenye                      # partial or complete .docx
uv run frank status pecsenye                      # passages done, pace
```

Generation is started only from Dagster (`dagster dev`) — there is deliberately no
second runner. It stops cleanly at a passage boundary when the session budget runs
out, and can be resumed any time.

## Documentation

| File | What it is |
|---|---|
| `AGENTS.md` | Entry point for AI coding agents; read first |
| `specs/mission.md` | Goal, principles, success criteria |
| `specs/architecture.md` | Layering, ubiquitous language, code style, allowed patterns |
| `specs/tech-stack.md` | Pinned tools and rationale |
| `specs/roadmap.md` | Phased implementation plan with acceptance criteria |
| `specs/linguistics.md` | Transliteration, T/V, igekötő, gloss rules |
| `specs/adr/` | Decision records — read before changing an approach |

## Sources

Only public-domain or freely licensed texts: copy a `.txt`, `.html`, or `.epub`
from [MEK](https://mek.oszk.hu/) (Hungarian) or Projekt Gutenberg-DE / zeno.org
(German) and pass that file to `frank ingest`. Source URL and license are recorded
in `book.toml` and printed on the title page.
