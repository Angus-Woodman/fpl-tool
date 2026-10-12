# Implementation Plan: My Team UX and Transfer Exploration

**Branch**: `feature/my-team-ux` | **Date**: 2026-10-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-my-team-ux/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Replace the separate "Edit Team" mode on My Team with direct, selection-based
rearrangement of the starting XI and bench (including bench-to-bench
substitute reordering, excluding the bench goalkeeper); hide projected-points
information on My Team by default behind a reveal control; keep "explore
transfers" as a distinct, always-visible per-player action that preserves
which player is being replaced; and change transfer exploration so that
candidates in the existing same-position/not-owned comparison pool are no
longer dropped when they fail a transfer-legality constraint (budget, club
limit, squad composition) — they stay visible, are clearly marked
unavailable with a reason, and remain previewable (but not applicable) in
Transfer Preview, which already supports this via its existing `is_legal`/
`errors` fields. The only backend change required is extending the
replacement-ranking domain function (`packages/fpl_engine`) and its API
response to surface unavailable pool candidates with a reason instead of
silently filtering them out; all other changes are in `apps/web`.

## Technical Context

**Language/Version**: TypeScript 5.6 (strict mode) for `apps/web`; Python 3.12 (mypy strict) for `apps/api` and `packages/fpl_engine`.

**Primary Dependencies**: Next.js 15.0.0 (App Router) + React 18.3.1 + Tailwind CSS for the frontend; FastAPI 0.114 + Pydantic 2.9 + SQLAlchemy 2.0 + Alembic for the backend; no new dependencies required.

**Storage**: PostgreSQL 16 via the existing `current_squad` / projection tables (Docker Compose locally). No schema change: rearrangement reuses the existing `is_starting`/`bench_order`/`is_captain`/`is_vice_captain` fields already persisted by `saveMyTeam`; selection state and the points reveal/hide toggle are ephemeral client UI state, never persisted.

**Testing**: pytest (`apps/api`, `packages/fpl_engine`); Vitest + Testing Library (`apps/web` unit/component); Playwright Test (`apps/web` e2e, `tests/e2e/`).

**Target Platform**: Web application (browser client against a FastAPI JSON backend).

**Project Type**: Web application — existing 3-layer structure (`apps/web`, `apps/api`, `packages/fpl_engine`); no new projects introduced.

**Performance Goals**: None beyond preserving current My Team / Transfer Explorer responsiveness; the spec defines no new performance targets.

**Constraints**: Transfer legality remains authoritatively computed in `packages/fpl_engine` (Constitution I); strict TypeScript/mypy preserved; no new infrastructure or dependencies (Constitution VIII, AGENTS.md).

**Scale/Scope**: Two pages (`/my-team`, `/transfers`), ~7 existing frontend components, one domain ranking function, one API response schema addition. No new pages, services, or persisted entities.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Domain correctness & boundaries | PASS — legality stays computed in `packages/fpl_engine` (`evaluate_single_transfer` / `rank_replacement_candidates`); `apps/api` and `apps/web` only consume and present the result, never reimplement legality. |
| II. Human ownership | PASS — plan implements exactly the accepted, clarified spec; no new product decisions introduced here. |
| III. Small reviewable slices | PASS — plan follows the spec's 4 independently-testable, prioritized user stories (P1–P4). |
| IV. Test at the owning layer | PASS — domain test for the ranking change (`packages/fpl_engine/tests`), API test for the response schema change (`apps/api/tests`), component tests for the UI changes (`apps/web/tests`). |
| V. Independent verification | PASS — `tasks.md` (next phase) and completion will apply `.github/skills/code-review` rather than self-attestation. |
| VI. Browser verification | PASS — all four stories are UI/UX changes; `.github/skills/ui-browser-verification` applies, with durable Playwright coverage for the rearrange → explore → preview → apply journey. |
| VII. Safe, isolated integration testing | PASS — no new destructive/integration test setup; existing `TEST_DATABASE_URL`/`ensure_test_database_url` guard is untouched and sufficient for any DB-touching test changes. |
| VIII. No silent scope expansion | PASS — scope is bounded to FR-001–FR-021; no My Team/transfer domain-rule changes, no unrelated refactors. |
| IX. Explicit acceptance criteria | PASS — spec.md's clarified acceptance scenarios govern; no implementation starts ahead of them. |
| X. Final review & green gates | Deferred to completion — plan requires full lint/typecheck/test/build gates and a full `git diff` review before the feature is considered done. |

No violations. Complexity Tracking is intentionally empty.

**Post-Design Re-check (after Phase 1)**: Still PASS, unchanged. `data-model.md`
and `contracts/transfer-explorer-get.md` are additive only (new optional
fields sourced from an existing domain evaluation); no new entities,
services, dependencies, or persisted state were introduced during design.

## Project Structure

### Documentation (this feature)

```text
specs/001-my-team-ux/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── transfer-explorer-get.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This feature uses the repository's existing web-application structure.
No new projects, services, or directories are introduced.

```text
apps/api/
├── src/api/
│   ├── routers/my_team.py                  # transfer explorer endpoint (response shape change only)
│   ├── schemas/transfers.py                # RankedTransferCandidateResponse gains availability fields
│   └── services/get_transfer_explorer.py   # passes through the extended ranking result
└── tests/transfers/                        # service/router tests for the schema change

apps/web/
├── src/components/team/
│   ├── my-team-board.tsx                   # replaces Edit Team mode with direct selection/rearrange + points reveal
│   ├── squad-player-card.tsx               # selection/valid-target/unavailable visual states
│   ├── bench.tsx / squad-pitch.tsx          # render selection state, unchanged layout contract
│   └── recommendation-summary.tsx           # projected-points panel hidden behind the same reveal control
├── src/components/transfers/
│   ├── transfer-explorer.tsx                # unchanged orchestration; passes availability through
│   ├── replacement-table.tsx                # shows unavailable candidates + reason, disabled row action
│   └── transfer-preview.tsx                 # already legality-aware; no contract change expected
└── tests/team/, tests/transfers/, tests/e2e/

packages/fpl_engine/
├── src/fpl_engine/transfers/
│   ├── replacement_ranking.py               # stop discarding illegal candidates; attach is_legal/errors
│   └── single_transfer.py                   # unchanged; already the source of per-candidate errors
└── tests/test_replacement_ranking.py         # new cases for retained-but-unavailable candidates
```

**Structure Decision**: Reuse the existing `apps/web` (Next.js) / `apps/api`
(FastAPI) / `packages/fpl_engine` (domain) layering as-is. The only
cross-layer change is additive (new optional fields on an existing response
schema, sourced from an existing domain evaluation); everything else is
contained within `apps/web`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — this section is intentionally empty.
