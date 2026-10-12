# Implementation Plan: My Team UX and Transfer Exploration

**Branch**: `feature/my-team-ux` | **Date**: 2026-10-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-my-team-ux/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Replace the separate "Edit Team" mode on My Team with direct, selection-based
rearrangement of the starting XI and bench (including bench-to-bench
substitute reordering, excluding the bench goalkeeper), with the result
always re-validated authoritatively server-side against the existing
domain formation rule; hide projected-points information on My Team by
default behind a reveal control; keep "explore transfers" as a distinct,
always-visible per-player action that preserves which player is being
replaced; and change transfer exploration so that candidates in the
existing same-position/not-owned comparison pool are no longer dropped
when they fail a transfer-legality constraint (budget, club limit, squad
composition) — they stay visible, keep their full comparison data, are
clearly marked unavailable with a user-facing reason, and remain
previewable (but not applicable) in Transfer Preview, which already
supports this via its existing `is_legal`/`errors` fields. Transfer Preview
additionally gains an explicit rejection for candidates outside the pool,
which it does not reject today. Backend changes are: (1) the
replacement-ranking domain function and its API response, to stop dropping
unavailable pool candidates; (2) wiring the squad-save path to the
existing, previously-unused `validate_squad`/`validate_starting_formation`
domain rule, which today allows illegal starting formations; (3) an
explicit pool-membership check in the preview service. All other changes
are in `apps/web`, including a single shared mapping from legality reason
codes to user-facing text used by both the candidate comparison and
Transfer Preview.

## Technical Context

**Language/Version**: TypeScript 5.6 (strict mode) for `apps/web`; Python 3.12 (mypy strict) for `apps/api` and `packages/fpl_engine`.

**Primary Dependencies**: Next.js 15.0.0 (App Router) + React 18.3.1 + Tailwind CSS for the frontend; FastAPI 0.114 + Pydantic 2.9 + SQLAlchemy 2.0 + Alembic for the backend; no new dependencies required.

**Storage**: PostgreSQL 16 via the existing `current_squad` / projection tables (Docker Compose locally). No schema change: rearrangement reuses the existing `is_starting`/`bench_order`/`is_captain`/`is_vice_captain` fields already persisted by `saveMyTeam`; selection state and the points reveal/hide toggle are ephemeral client UI state, never persisted.

**Testing**: pytest (`apps/api`, `packages/fpl_engine`); Vitest + Testing Library (`apps/web` unit/component); Playwright Test (`apps/web` e2e, `tests/e2e/`).

**Target Platform**: Web application (browser client against a FastAPI JSON backend).

**Project Type**: Web application — existing 3-layer structure (`apps/web`, `apps/api`, `packages/fpl_engine`); no new projects introduced.

**Performance Goals**: None beyond preserving current My Team / Transfer Explorer responsiveness; the spec defines no new performance targets.

**Constraints**: Transfer and lineup legality remain authoritatively computed in `packages/fpl_engine` (Constitution I) — this plan specifically closes two existing gaps where that wasn't yet true (squad-save formation validation; Preview's pool-boundary check), rather than introducing new rules. Strict TypeScript/mypy preserved; no new infrastructure or dependencies (Constitution VIII, AGENTS.md).

**Scale/Scope**: Two pages (`/my-team`, `/transfers`), ~7 existing frontend components, one domain ranking function, one squad-save validation rewiring (reusing an existing domain rule), one preview-service pool-boundary check, two API response/behaviour changes (Explorer additive fields, Preview new rejection case), one shared frontend reason-mapping module. No new pages, services, persisted entities, or domain rules.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Domain correctness & boundaries | PASS, with two pre-existing gaps closed by this plan rather than left in place: (1) the squad-save path (`UpsertCurrentSquadService`) currently re-implements squad-composition checks by hand in `apps/api` and never calls the domain's `validate_starting_formation` at all — e.g. it would accept an illegal 2-GK starting XI; this plan wires in the existing `fpl_engine.rules.validate_squad` instead of writing a new/duplicate check. (2) Transfer Preview currently evaluates (and returns a legality-aware result for) out-of-pool players instead of rejecting them outright; this plan adds an explicit pool check before evaluation. Both fixes reuse existing domain rules/evaluations — no new ruleset is introduced, and legality/eligibility decisions remain in `packages/fpl_engine` or the service layer that directly wraps it, never in `apps/web`. |
| II. Human ownership | PASS — plan implements exactly the accepted, clarified spec, plus the two authoritative-validation gaps above, which are a direct consequence of FR-004 ("remains valid under the existing squad/formation rules") and FR-013/FR-017 ("not previewable"), not new scope. |
| III. Small reviewable slices | PASS — plan follows the spec's 4 independently-testable, prioritized user stories (P1–P4), with the two authoritative-validation fixes scoped tightly to the services each story already touches. |
| IV. Test at the owning layer | PASS — domain tests for the ranking change and for a 5-2-3 formation passing `validate_squad` (`packages/fpl_engine/tests`); API tests for the Explorer/Preview response and rejection changes and for the squad-save path now rejecting an illegal starting formation (`apps/api/tests`); component tests for the UI changes and the shared reason-mapping (`apps/web/tests`). |
| V. Independent verification | PASS — `tasks.md` (next phase) and completion will apply `.github/skills/code-review` rather than self-attestation. |
| VI. Browser verification | PASS — all four stories are UI/UX changes; `.github/skills/ui-browser-verification` applies, with durable Playwright coverage for the rearrange → explore → preview → apply journey. |
| VII. Safe, isolated integration testing | PASS — no new destructive/integration test setup; existing `TEST_DATABASE_URL`/`ensure_test_database_url` guard is untouched and sufficient for any DB-touching test changes. |
| VIII. No silent scope expansion | PASS — scope is bounded to FR-001–FR-021 plus the two authoritative-validation fixes they directly require; no unrelated domain-rule changes or refactors. |
| IX. Explicit acceptance criteria | PASS — spec.md's clarified acceptance scenarios govern; no implementation starts ahead of them. |
| X. Final review & green gates | Deferred to completion — plan requires full lint/typecheck/test/build gates and a full `git diff` review before the feature is considered done. |

No unjustified violations. Complexity Tracking is intentionally empty.

**Post-Design Re-check (after Phase 1, revised)**: Still PASS. `data-model.md`
and `contracts/` remain additive/behaviour-scoped: the Explorer response
gains two fields with no existing field changed or made optional; the
Preview response schema is unchanged (only a new, earlier rejection path);
the squad-save path swaps a duplicate, incomplete check for the existing
authoritative domain rule. No new entities, services, dependencies, or
persisted state were introduced during design.

## Project Structure

### Documentation (this feature)

```text
specs/001-my-team-ux/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   ├── transfer-explorer-get.md
│   └── transfer-preview-get.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This feature uses the repository's existing web-application structure.
No new projects, services, or directories are introduced.

```text
apps/api/
├── src/api/
│   ├── routers/my_team.py                  # transfer explorer/preview endpoints (response/rejection changes only)
│   ├── schemas/transfers.py                # RankedTransferCandidateResponse gains is_legal/unavailable_reasons
│   ├── services/get_transfer_explorer.py   # passes through the extended (non-filtering) ranking result
│   ├── services/get_transfer_preview.py    # new pool-membership check before legality evaluation
│   └── services/current_squad.py           # _validate rewired onto fpl_engine.rules.validate_squad
└── tests/transfers/, tests/team/           # service/router tests for the schema, rejection, and validation changes

apps/web/
├── src/components/team/
│   ├── my-team-board.tsx                   # replaces Edit Team mode with direct selection/rearrange + points reveal
│   ├── squad-player-card.tsx               # selection/valid-target/unavailable visual states
│   ├── bench.tsx / squad-pitch.tsx          # render selection state, unchanged layout contract
│   └── recommendation-summary.tsx           # projected-points panel hidden behind the same reveal control
├── src/components/transfers/
│   ├── transfer-explorer.tsx                # unchanged orchestration; passes availability through
│   ├── replacement-table.tsx                # shows unavailable candidates + mapped reason, disabled row action
│   ├── legality-reasons.ts                  # new: shared code → user-facing text mapping
│   └── transfer-preview.tsx                 # renders errors via the shared mapping instead of raw codes
└── tests/team/, tests/transfers/, tests/e2e/

packages/fpl_engine/
├── src/fpl_engine/transfers/
│   ├── replacement_ranking.py               # stop discarding illegal candidates; keep full per-gameweek data
│   └── single_transfer.py                   # unchanged; already the source of per-candidate errors/comparison data
├── src/fpl_engine/rules/squad.py             # unchanged; validate_squad/validate_starting_formation now consumed by apps/api
└── tests/test_replacement_ranking.py         # new cases for retained-but-unavailable candidates with full data
```

**Structure Decision**: Reuse the existing `apps/web` (Next.js) / `apps/api`
(FastAPI) / `packages/fpl_engine` (domain) layering as-is. Every change
either reuses an existing domain function/rule (`evaluate_single_transfer`,
`validate_squad`) or is additive on an existing API response; no new
projects, services, or persisted entities are introduced.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — this section is intentionally empty.
