# ADR 0015 — Character map sends PERSON evidence, not chapter text

Date: 2026-09-01. Status: accepted.

## Context
Roadmap 3.3 is a chapter-by-chapter SMART map-reduce. A chapter does not fit a
SMART call, and LLMs must not re-analyze text we already parsed. 3.1 already
has PERSON terms; 3.2 already has Ukrainian renderings. Gender still needs a
few local sentences (Hungarian `ő` is not a cue; `Frau` / `úr` are).

## Decision
1. Map input per chapter is the PERSON terms that occur there plus
   `evidence_sentences_per_person` sentences each, preferring hits from the
   closed cue lists `data/de_gender_cues.txt` / `data/hu_gender_cues.txt`.
2. One SMART object per input lemma. Diminutives share `canonical_name` and
   put the nickname in `aliases`.
3. Reduce is deterministic (shared lemma, canonical name, or alias). No second
   LLM call over the book.
4. Unresolvable gender is `unknown`, persisted for the 3.6 review gate, never
   guessed.

## Alternatives rejected
- Send the full chapter: exceeds budget and repeats analyzer work.
- SMART reduce over all drafts: the merge keys are already in the drafts.
- Drop characters with unknown gender: 3.6 could not correct them.

## Consequences
+ Same payload shape as lemma arbitration: types plus a few example sentences.
− Sparse chapters leave gender unknown until human review.
