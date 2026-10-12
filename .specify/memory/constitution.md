# fpl-tool Constitution

## Core Principles

### I. Domain Correctness & Architectural Boundaries
FPL rules and legality live in `packages/fpl_engine` as framework-independent
domain code; `apps/api` owns FastAPI/application/infrastructure concerns;
`apps/web` owns presentation. Domain code MUST NOT depend on FastAPI.
External API calls belong in infrastructure adapters. Authoritative rule
enforcement MUST exist in the domain layer — UI-side validation is a UX
optimisation only, never a substitute. Domain behaviour MUST NOT be
duplicated across layers without justification, and authoritative
server/domain validation MUST remain even when duplicated for UX. Database
schema changes require Alembic migrations.

### II. Human Ownership of Product & Architecture
The human retains responsibility for product direction, architecture,
trade-offs and correctness. Specs and plans MUST NOT silently expand scope
or bundle adjacent improvements merely because they appear useful.
Significant architectural departures from an accepted plan MUST be
explained before being made.

### III. Small Reviewable Slices
Implementation plans MUST decompose work into the smallest coherent slices
that can be independently implemented, reviewed and verified. Avoid plans
that require large, monolithic changes when a staged approach is viable.

### IV. Test at the Owning Layer
Every plan MUST identify, for each piece of new behaviour, which layer owns
it and require tests at that layer: domain tests in `packages/fpl_engine`,
service/router/integration tests in `apps/api`, component tests in
`apps/web`. Tests MUST NOT be substituted with tests at the wrong layer for
convenience.

### V. Independent Verification
A task is not complete because the implementing agent states it works.
Plans and task breakdowns MUST include explicit verification steps
(automated checks, and independent review per `.github/skills/code-review`)
separate from the implementation narrative.

### VI. Browser Verification for UI Changes
Any plan containing substantial UI/UX changes MUST include verification of
the rendered application (see `.github/skills/ui-browser-verification`),
not just component tests. Important, regression-sensitive journeys MUST
gain durable Playwright Test coverage.

### VII. Safe, Isolated Destructive/Integration Testing
Plans involving database-touching integration tests MUST use the dedicated
`_test` database via `TEST_DATABASE_URL` and the existing
`ensure_test_database_url` safeguard. Destructive setup MUST NEVER target
the development database. If the dedicated test database is unavailable,
fail or skip per the existing explicit mechanism rather than falling back
to development data.

### VIII. No Silent Scope Expansion
Specs, plans and tasks define the agreed change surface. Implementation
MUST NOT exceed that surface without the human being informed and agreeing
to the change. Unrelated refactors are out of scope by default.

### IX. Explicit Acceptance Criteria Before Implementation
Substantial implementation MUST NOT begin until governing acceptance
criteria are identified or written, along with the proposed approach and
material assumptions/risks.

### X. Final Review & Green Quality Gates
Before a feature is considered done: the full diff MUST be reviewed for
unintended scope, the relevant quality gates (lint, type checks, tests,
build) MUST pass, and completion MUST be reported against the acceptance
criteria with any unverified aspects called out explicitly.

## Relationship to AGENTS.md

This constitution governs how substantial feature work is specified and
planned under Spec Kit (`.specify/`). `AGENTS.md` provides standing,
always-on repository instructions to coding agents regardless of whether
Spec Kit is in use. Where both apply, they must not conflict; this document
does not restate `AGENTS.md` material in full.

## Governance

This constitution supersedes ad-hoc practice for any work done through the
Spec Kit specify/plan/tasks/implement workflow. Amendments require updating
this file directly, incrementing the version below, and recording the
rationale in the amendment's commit message. Plans and task lists MUST note
any deliberate deviation from a principle here and why.

**Version**: 1.0.0 | **Ratified**: 2026-10-12 | **Last Amended**: 2026-10-12
