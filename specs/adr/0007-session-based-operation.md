# ADR 0007 — Session-based operation, no overnight runs

Date: 2026-08-30. Status: accepted.

## Context
The owner works in ~2-hour blocks and does not want to babysit or leave the
machine running overnight.

## Decision
Generation takes a time/passage budget, stops cleanly at a passage boundary, and
records completion per passage. Rendering is incremental: after any session,
`frank render` yields a valid partial book marked "— згенеровано до пасажу N —".
Crashes are classified (`error_class`) and announced by a macOS notification.

## Consequences
+ Progress accumulates in usable increments; nothing is lost on interruption.
− A full book takes many sessions; pace must be tracked (`frank status`).
