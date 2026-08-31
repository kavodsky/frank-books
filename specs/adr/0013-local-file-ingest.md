# ADR 0013 — Operator copies the source file; no site fetchers

Date: 2026-08-31. Status: accepted.

## Context
Roadmap 1.1 specified URL fetchers and site-specific adapters for mek.oszk.hu
and Projekt Gutenberg-DE. Those sites change markup, block bots, and mix chrome
with text. The operator already downloads a public-domain `.txt`, `.html`, or
`.epub` by hand.

## Decision
`frank ingest` accepts only a local path. Format adapters (txt / html / epub)
turn that file into plain text. Catalog URL and license note live in
`books/{slug}/book.toml`, filled in by the operator. No HTTP, no MEK/Gutenberg
parsers.

## Alternatives rejected
- Keep site adapters as optional: a second ingest path, forbidden by the
  simplicity rule.
- Fetch-by-URL with a generic HTML extractor: still couples the pipeline to
  live sites and their chrome.

## Consequences
+ One ingest path; site redesigns cannot break the pipeline.
+ Raw bytes in `books/{slug}/raw/` are exactly the file the operator chose.
− The operator must copy the file and record source/license in `book.toml`.
