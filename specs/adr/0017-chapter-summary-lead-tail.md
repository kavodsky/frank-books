# ADR 0017 — Chapter summaries send lead and tail, not chapter text

Date: 2026-09-01. Status: accepted.

## Context
Roadmap 3.5 maps each chapter to a 3–5 sentence Ukrainian summary, then reduces
those summaries into a book StyleCard. A chapter does not fit a SMART call
(ADR 0015). LLMs must not re-analyze source we already parsed.

## Decision
1. Map input per chapter is `summary_lead_sentences` opening sentences plus
   `summary_tail_sentences` closing sentences, and Character names that occur in
   that span. If the chapter is shorter than lead+tail, send every sentence as
   lead and no tail. Never send the middle, and never send paragraph dumps.
2. Clamp the Ukrainian summary to `summary_sentence_max` sentences in domain
   code. Do not pad up to `summary_sentence_min`.
3. StyleCard reduce sees title, author, language, and the chapter summaries —
   not source text.
4. Persist `chapter.summary_uk` and one `style_card` row; also write
   `books/{slug}/style_card.md`.

## Alternatives rejected
- Full-chapter SMART summary: exceeds budget and repeats analyzer work.
- StyleCard from source excerpts: the summaries already compress plot.

## Consequences
+ Same payload shape as 3.3/3.4: types plus a few sentences.
− Characters who appear only in the dropped middle are absent from the brief.
