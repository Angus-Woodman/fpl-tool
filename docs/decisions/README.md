# Architecture Decision Records

This directory holds lightweight ADRs for durable architectural decisions.

## When an ADR is justified

Write an ADR only when a decision is:

- **durable** — it shapes the codebase for an extended period, not a single
  PR;
- **contested** — there were meaningful alternatives that a future reader
  would otherwise have to rediscover;
- **consequential** — getting it wrong or reversing it later is costly.

Do not write an ADR for routine implementation choices, decisions with only
one reasonable option, or to retroactively document existing behaviour that
isn't being revisited.

## Format

Each ADR is a single markdown file: `NNNN-short-title.md` (zero-padded,
sequential). Keep it short:

```markdown
# NNNN: Title

Status: proposed | accepted | superseded by NNNN

## Context
What problem/forces led to this decision.

## Decision
What was decided.

## Alternatives considered
Other options and why they were rejected.

## Consequences
What this makes easier/harder going forward.
```
