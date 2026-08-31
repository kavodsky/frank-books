# ADR 0011 — DDD applied selectively; SQLAlchemy over SQLModel

Date: 2026-08-30. Status: accepted.

## Context
Readability and a clean layout are explicit requirements. Full DDD would add
aggregates, domain events and CQRS to what is essentially a text-transformation
pipeline with a single user and no write contention.

## Decision
Keep: ubiquitous language, inward-only layering (domain / application /
infrastructure / interfaces), ports and adapters, repositories as plain gateways,
value objects, and an anti-corruption layer around LLM output.
Drop: aggregates as transactional boundaries, domain events, CQRS, bounded
contexts as packages, generic Unit of Work.
Consequently the domain must be persistence-ignorant, so **SQLAlchemy 2.0** is
used for tables with explicit mappers, and **SQLModel is rejected** because it
merges table and domain model in one class.

## Consequences
+ Domain logic is testable with no DB, no model server, no spaCy — enforced by an
  import-boundary test in CI.
+ Vocabulary is shared between specs, code and prompts.
− Explicit mapper code between rows and domain objects (boring but cheap).
