# ADR 0005 — The passage, not the paragraph, is the doubling unit

Date: 2026-08-30. Status: accepted.

## Context
Frank books repeat a chunk of text twice: adapted, then unadapted. An early draft
doubled per paragraph, which would be unreadable for dialogue with one-line
paragraphs.

## Decision
Group consecutive paragraphs into passages of ~800–1500 chars (never splitting a
paragraph or crossing a chapter) and double per passage. Generation and caching
stay per paragraph; the passage is the unit of visible progress and completeness.

## Consequences
+ Matches the reference books; dialogue reads naturally.
− Two units to keep straight: paragraph (technical), passage (editorial).
