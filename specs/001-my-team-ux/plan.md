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
same-position/not-owned/FPL-selectable comparison pool are no longer dropped
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
domain rule, which today allows illegal starting formations; (3) extracting
the candidate-pool rule into a single `fpl_engine` helper, extending it with
upstream `can_select` / `can_transact`, and using it from Preview and Apply so
out-of-pool candidates are rejected, rather than re-implementing the rule in
`apps/api`; (4) retaining those flags through import and an Alembic migration,
removing the repository's playing-status filter, and exposing advisory status
in Explorer and Preview. The legacy inline per-player Transfer / Replacement Player /
Confirm Transfer path that exists only inside Edit Team is removed with the mode
(human-approved; spec FR-007a): the always-visible Explore Transfers → Preview →
Apply journey replaces it. All other changes
are in `apps/web`, including a single shared mapping from legality reason
codes to user-facing text used by both the candidate comparison and
Transfer Preview.

## Technical Context

**Language/Version**: TypeScript 5.6 (strict mode) for `apps/web`; Python 3.12 (mypy strict) for `apps/api` and `packages/fpl_engine`.

**Primary Dependencies**: Next.js 15.0.0 (App Router) + React 18.3.1 + Tailwind CSS for the frontend; FastAPI 0.114 + Pydantic 2.9 + SQLAlchemy 2.0 + Alembic for the backend; no new dependencies required.

**Storage**: PostgreSQL 16 (Docker Compose locally). One Alembic migration adds nullable `players.can_select` / `players.can_transact`, populated by bootstrap refresh, never backfilled from status. Rearrangement reuses existing squad fields; selection/reveal state remains ephemeral. No snapshot/projection schema change.

**Testing**: pytest (`apps/api`, `packages/fpl_engine`); Vitest + Testing Library (`apps/web` unit/component); Playwright Test (`apps/web` e2e, `tests/e2e/`) with the API stubbed via `page.route` and no new `webServer`/full-stack harness. Real-stack browser verification is a separate, manual step (`ui-browser-verification`) that covers normal flows and states actually present in refreshed imported data; artificial flag/status combinations, flag transitions after Preview and unknown/refresh-required combinations are verified only with deterministic domain/API/component tests and stubs, never by mutating development data.

**Target Platform**: Web application (browser client against a FastAPI JSON backend).

**Project Type**: Web application — existing 3-layer structure (`apps/web`, `apps/api`, `packages/fpl_engine`); no new projects introduced.

**Performance Goals**: None beyond preserving current My Team / Transfer Explorer responsiveness; the spec defines no new performance targets.

**Constraints**: Domain-owned lineup/transfer rules and a single pool predicate. Playing status is advisory, never an eligibility or legality rule. Both upstream flags must explicitly permit incoming selection; unknown data surfaces a refresh-required condition, never a status fallback. Apply rechecks the latest imported flags, not live FPL. Existing availability/minutes projections and ranking stay unchanged. Strict typing; no new dependencies/infrastructure. Saving a lineup (`PUT /my-team`) validates squad composition and starting formation only; incoming selectability is not enforced there. Rearrangement preserves the saved bank exactly and My Team displays the saved `bank`, not a figure recomputed from prices. Pool-exclusion precedence: structural (owned / wrong position), then known non-selectable, then unknown selectability. Rearrangement is available only when no optimiser mode is active.

**Scale/Scope**: Two existing pages; ranking and one shared domain pool helper; squad-save validation rewiring; import/model/repository flag propagation and one migration; Explorer/Preview additive fields and early rejection; Apply eligibility recheck; shared frontend legality and advisory-status mappings. No new pages, services, persisted entities, or projection model.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Domain correctness & boundaries | PASS, with two pre-existing gaps closed by this plan rather than left in place: (1) the squad-save path (`UpsertCurrentSquadService`) currently re-implements squad-composition checks by hand in `apps/api` and never calls the domain's `validate_starting_formation` at all — e.g. it would accept an illegal 2-GK starting XI; this plan wires in the existing `fpl_engine.rules.validate_squad` instead of writing a new/duplicate check. (2) Transfer Preview currently evaluates (and returns a legality-aware result for) out-of-pool players instead of rejecting them outright, while the pool rule exists only as a private inline skip inside `rank_replacement_candidates`; this plan extracts that rule into one small pure helper in `packages/fpl_engine` used by both Explorer ranking and the Preview service, so `apps/api` adds no pool-eligibility logic of its own. Both fixes reuse or extract existing domain rules — no new ruleset is introduced, and legality/eligibility decisions live in `packages/fpl_engine`, never in `apps/api` or `apps/web`. |
| II. Human ownership | PASS — plan implements exactly the accepted, clarified spec, plus the two authoritative-validation gaps above, which are a direct consequence of FR-004 ("remains valid under the existing squad/formation rules") and FR-013/FR-017 ("not previewable"), not new scope. |
| III. Small reviewable slices | PASS — plan follows the spec's 4 independently-testable, prioritized user stories (P1–P4), with the two authoritative-validation fixes scoped tightly to the services each story already touches. |
| IV. Test at the owning layer | PASS — domain tests for the ranking change, the pool-eligibility helper, and a 5-2-3 formation passing `validate_squad` (`packages/fpl_engine/tests`); API tests for the Explorer/Preview response and rejection changes and for the squad-save path now rejecting an illegal starting formation (`apps/api/tests`); component tests for the UI changes and the shared reason-mapping (`apps/web/tests`). |
| V. Independent verification | PASS — `tasks.md` (next phase) and completion will apply `.github/skills/code-review` rather than self-attestation. |
| VI. Browser verification | PASS — all four stories are UI/UX changes; `.github/skills/ui-browser-verification` applies, with durable Playwright coverage for the rearrange → explore → preview → apply journey. |
| VII. Safe, isolated integration testing | PASS — no new destructive/integration test setup; existing `TEST_DATABASE_URL`/`ensure_test_database_url` guard is untouched and sufficient for any DB-touching test changes. |
| VIII. No silent scope expansion | PASS — scope is bounded to FR-001–FR-021 plus the two authoritative-validation fixes they directly require; no unrelated domain-rule changes or refactors. |
| IX. Explicit acceptance criteria | PASS — spec.md's clarified acceptance scenarios govern; no implementation starts ahead of them. |
| X. Final review & green gates | Deferred to completion — plan requires full lint/typecheck/test/build gates and a full `git diff` review before the feature is considered done. |

Decision 10 extends assessments I/II/III/IV/VII/VIII: the human-authorized
selectability policy lives in the same pure domain helper used by Explorer,
Preview and Apply; import persistence requires one Alembic migration, not
another ruleset. Require adapter/mapper/upsert/migration tests, domain flag
combination tests, service/router tests for status-independent eligibility
and stale-Preview Apply rejection, plus advisory-status component/browser
coverage. DB checks use only guarded `TEST_DATABASE_URL`. This narrow work
implements FR-013/FR-013a/FR-013b, not unrelated projection work.

Removing the Edit-Team-only inline Transfer path (spec FR-007a) is a
human-approved change recorded in the spec, so it is inside the agreed change
surface (Principles II, VIII, IX) and does not conflict with FR-021. It also
removes a route that saved directly via `PUT /my-team` without Preview.

No unjustified violations. Complexity Tracking is intentionally empty.

**Post-Design Re-check (after Phase 1, revised again)**: Still PASS.
Explorer gains `is_legal`, `unavailable_reasons`, `status`; Preview gains
`player_in_status` and an early 422 rejection; Apply adds fresh eligibility
validation with existing failure/success shapes. Existing comparison types
(including direct-xPts nullability) stay unchanged. One migration retains
authoritative upstream flags on existing players. Eligibility remains one
domain helper; no projection changes, new entities/services/dependencies,
or unguarded DB validation.

## Resolved Decision And Risks

Decision 10 is resolved: same position, not owned, both upstream flags true;
playing status advisory. See [research.md](./research.md) for live evidence,
import gaps and missing-field handling. Existing rows require bootstrap
refresh after migration. Flag semantics are based on upstream field names
and observed payload combinations, not a published exhaustive contract.
Apply uses latest imported data and cannot guarantee live FPL state. No
fallback derives eligibility from status. `tasks.md` has been generated;
implementation remains unauthorized until explicitly started.

Resolved implementation decisions (see research.md decisions 10-13):

- Incoming selectability stays out of `PUT /my-team`; it only gains authoritative squad/formation validation.
- Rearrangement preserves the saved bank, and My Team displays the saved bank.
- Exclusion precedence: structural, then known non-selectable, then unknown.
- Unknown selectability makes Explorer return `selectability_unknown`; a refresh normally resolves it and an upstream omission intentionally keeps the diagnostic.
- The migration and bootstrap refresh are an operational gate placed immediately after the persistence tasks and before any real-backend verification. US1 can be done and verified before the migration exists.
- Playwright stays API-stubbed (one non-`a`-but-selectable case); real-stack verification is separate and limited to states present in refreshed data.
- Known limitation: a lineup save sends the whole squad from the page snapshot, so a stale page can overwrite a concurrent change. Fixing it needs optimistic concurrency/versioning or a narrower mutation endpoint, outside this feature.

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
│   ├── schemas/transfers.py                # candidate legality + advisory status
│   ├── schemas/transfer_preview.py         # additive player_in_status
│   ├── services/get_transfer_explorer.py   # calls the shared pool helper per profile before projections (unknown → `selectability_unknown`), passes through legality/status fields
│   ├── services/candidate_pool_failures.py # new: translates pool-exclusion reasons into failure messages (no eligibility rules)
│   ├── services/get_transfer_preview.py    # calls the shared fpl_engine pool-eligibility helper before loading projections/evaluating legality
│   ├── services/apply_transfer.py          # fresh incoming pool check before evaluation/save
│   ├── adapters/fpl/, services/import_fpl_data.py # retain upstream flags
│   ├── models/entities.py, repositories/   # persist/read flags; `list_available_by_position` → `list_by_position` with the status filter removed
│   └── services/current_squad.py           # _validate rewired onto fpl_engine.rules.validate_squad
├── alembic/versions/                       # one nullable-flag migration, no status backfill
└── tests/transfers/, tests/team/, tests/fpl/, tests/services/, tests/repositories/   # service/router/adapter/guarded-DB tests (incl. `list_by_position` status-filter test)

apps/web/
├── src/components/team/
│   ├── my-team-board.tsx                   # direct selection/rearrange (actual lineup only, saved bank preserved and displayed), points reveal; Edit Team mode and inline Transfer path removed
│   ├── squad-player-card.tsx               # selection/valid-target/unavailable visual states
│   ├── bench.tsx / squad-pitch.tsx          # render selection state, unchanged layout contract
│   └── recommendation-summary.tsx           # projected-points panel hidden behind the same reveal control
├── src/components/transfers/
│   ├── transfer-explorer.tsx                # unchanged orchestration; passes availability through
│   ├── replacement-table.tsx                # shows unavailable candidates + mapped reason; Preview action stays enabled for them (only Apply, inside Preview, is disabled)
│   ├── legality-reasons.ts                  # new: shared code → user-facing text mapping
│   ├── playing-status.ts                    # new: shared advisory status mapping, no legality logic
│   └── transfer-preview.tsx                 # renders errors via the shared mapping instead of raw codes
└── tests/team/, tests/transfers/, tests/e2e/my-team-ux.spec.ts   # Vitest component tests; one API-stubbed Playwright spec

packages/fpl_engine/
├── src/fpl_engine/transfers/
│   ├── candidate_pool.py                    # new: same position, not owned, both incoming flags true
│   ├── replacement_ranking.py               # PricedPlayer flag inputs; retain illegal-candidate metrics; shared pool helper
│   └── single_transfer.py                   # unchanged; already the source of per-candidate errors/comparison data
├── src/fpl_engine/rules/squad.py             # unchanged; validate_squad/validate_starting_formation now consumed by apps/api
├── src/fpl_engine/domain/entities.py        # Player retains nullable upstream flags
└── tests/test_replacement_ranking.py, tests/test_candidate_pool.py   # retained-but-unavailable candidates with full data; pool-eligibility helper
```

**Structure Decision**: Reuse the existing `apps/web` (Next.js) / `apps/api`
(FastAPI) / `packages/fpl_engine` (domain) layering as-is. Every change
either reuses an existing domain function/rule (`evaluate_single_transfer`,
`validate_squad`) or is additive on an existing API response; no new
projects, services, or persisted entities are introduced.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — this section is intentionally empty.
