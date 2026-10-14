---
description: "Dependency-ordered implementation tasks for Planner Foundations"
---

# Tasks: Planner Foundations

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [API contract](contracts/planner-api.md), [validation guide](quickstart.md) and the completed [requirements-quality checklist](checklists/planner-foundations.md).

**Authority**: FR-001 through FR-049, SC-001 through SC-009, R-01 through R-12 and resolved Q-1 through Q-7. The approved first-saved-GW legacy boundary and permanent-prefix rebase decisions remain fixed. This document schedules implementation; it does not change the specification or claim any implementation is complete.

**Tests**: Required by the specification's reference scenarios, accepted plan and constitution. Write the relevant tests first, observe the expected failure, implement the owning behavior, then run the smallest relevant checks before advancing. Reuse existing builders/modules. Proposed filenames below are implementation targets, not files claimed to exist already.

**Organization**: Shared prerequisites precede six user-story phases in specification priority order. Shared replay and transport are deliberately foundational because every story must use one authority and one guarded writer. Story tasks add their integration, presentation and acceptance proof rather than implementing competing engines.

## Format And Constraints

- Task format: `- [ ] Tnnn [P?] [USn?] Description with exact path`.
- `[P]` marks disjoint files that may be worked on concurrently only after their stated prerequisites. It is not permission to skip phase gates or run destructive SQL fixtures together.
- Use mise-pinned tools, local uv/pnpm dependencies and existing libraries. No new service, runtime dependency, application scaffold or general workflow/state framework is required.
- API captures observations and persists; `fpl_engine` owns rules/replay; web submits field/domain intent. No live price fetch, FastAPI, SQLAlchemy or projection dependency in the engine.
- DB tests must use `TEST_DATABASE_URL`, a database name ending `_test`, and `ensure_test_database_url`; never fall back to development data. Migration fixtures must be isolated from other SQL suites.
- No Explorer navigation/redesign/pricing changes, My Team financial changes, xPts changes, history/versioning, speculative prices, same-GW round trips, optimisation or broad visual redesign.
- Every phase is an internal reviewable increment. Do not switch persistent application writers until additive schema, explicit operator initialization and the matching web/API release are ready. No half-migrated legacy write adapter is allowed.

## Phase 1: Setup (Existing Project And Fixtures)

**Purpose**: Confirm the existing toolchain and verification entrypoints, without re-scaffolding the monorepo or mutating persistent data.

- [X] T001 Confirm the current Alembic head, mise versions, existing test entrypoints and guarded test-DB prerequisites; record any actual command/head corrections in `specs/002-planner-foundations/quickstart.md` without running initialization or downgrade on development data.
- [X] T002 [P] Extend deterministic legal multi-club squad/ownership/quote builders in `packages/fpl_engine/tests/test_planning.py` for independent hand-calculated assertions; do not derive expected results by calling the evaluator under test.
- [X] T003 [P] Extend shared API builders in `apps/api/tests/conftest.py` and add reusable stateful Planner browser/component fixtures in `apps/web/tests/fixtures/planner.ts`, including revisions, mutable receipts, frozen quotes and deferred outcomes; preserve existing unrelated fixtures.

**Checkpoint**: Existing commands and safe fixture boundaries are known; no new infrastructure or production data changes.

## Phase 2: Foundational (Single Authority And Guarded Mutation Path)

**Purpose**: Build the minimal shared engine, canonical persistence and transport needed by all six stories. Complete this phase before story integration. After each test/implementation pair, run its focused suite; do not defer all validation until T028.

### Pure Domain Foundation

- [X] T004 Add input/value-contract tests in `packages/fpl_engine/tests/test_planning.py` for stable slot/ownership identity, 15-player boundaries, independent per-GW slot lineups, positive integer prices and negative evaluated banks; reject malformed identities, duplicate net changes and same-GW round trips.
- [X] T005 Add immutable canonical boundary, ownership/provenance, transfer, lineup, intent and evaluation values in `packages/fpl_engine/src/fpl_engine/planning/models.py`; preserve the data-model constraints "Price inputs are positive integers; evaluated bank can be negative", "Each configuration contains XI/bench priority/C/VC over the 15 slot IDs, not a second player-membership list", and "Unique outgoing/incoming players per GW; no same-player out/in, duplicated acquisition, zero-price or same-GW round-trip decisions". Preserve "Starting purchase provenance separates original source from `assumed`/`user_confirmed`/`authoritative` confirmation"; a carried acquisition keeps `basis_kind=planned_acquisition` with confirmation N/A rather than becoming assumed historical purchase data.
- [X] T006 Add hand-calculated primitive cases to `packages/fpl_engine/tests/test_rules.py` and `packages/fpl_engine/tests/test_planning.py`: sale P50/M48,50,51,52,53,54 gives 48,50,50,51,51,52; WC/FH available N=0..5 uses `min(5,max(N-1,0)+1)`; BB/TC remain ordinary; GW1 feeds FT1 into GW2; no season top-up.
- [X] T007 Implement integer-tenths sale arithmetic in `packages/fpl_engine/src/fpl_engine/planning/prices.py` and correct WC/FH rollover in `packages/fpl_engine/src/fpl_engine/rules/transfers.py`, reusing existing unlimited/hit/ordinary primitives and intentionally updating only obsolete rule expectations.
- [X] T008 Add explicit-decision replay/intent tests in `packages/fpl_engine/tests/test_planning.py` for permanent versus FH branches, first-GW counting, unchanged local slot roles, ownership-bound outgoing decisions, Examples A/B and unavailable dependent accounting instead of invented transfers/totals. Cover the core add/edit/remove/net-repair, chip activate/remove/move and horizon handlers needed before T028: valid-prefix rebase with inline provenance/FT/bank/applicable chips/FH19, hypothetical earlier starts, final-FH extension, trims, unchanged retained quotes/lineups and named chip availability/conflict reasons.
- [X] T009 Implement deterministic ordered replay in `packages/fpl_engine/src/fpl_engine/planning/evaluate.py` using canonical decisions only: apply each unordered GW net set atomically to entering ownership, restore permanent state after FH, retain WC bases, and return structured blocked diagnostics; never consume materialized membership or fetch current prices.
- [X] T010 Add Q2/Q7 comparison tests in `packages/fpl_engine/tests/test_planning.py` for saved-market dependent sales, provisional dependency propagation, FH financial edges, mixed-correction rejection and the accepted repair `(-1,-3)->(0,-2)` with earliest failure moving to GW10. Also start with multiple independent legacy structural diagnostics, repair one while another remains, and accept if no unrelated invalidity is introduced or worsened; reject new/worse blockers and unverified edits beyond a blocked dependency. Assert dependent accounting remains unavailable, never a fabricated bank/shortfall used in comparison.
- [X] T011 Implement the core intent handlers and whole-candidate validation in `packages/fpl_engine/src/fpl_engine/planning/mutations.py`, using `packages/fpl_engine/src/fpl_engine/rules/chips.py` for declaration-aware availability/reasons: existing lineup field intents, rename, chip activate/remove/move, transfer add/edit/remove/atomic repair, horizon changes and starting-basis correction/confirmation must work before T018/T028. Horizon handling owns valid permanent-prefix capture, stable slots/ownership/inline provenance/bank assumptions/FT/applicable chip use/FH19, unresolved-prefix rejection, hypothetical earlier starts, permanent extension after FH and trimmed decisions; preserve retained quotes/lineups. Corrections preserve original captures/frozen boundary bank and use saved-market Q7 replay. Ordinary edits require `S_candidate(g) <= S_previous(g)` per evaluable retained GW, new GW baseline zero; explicitly compare pre-existing structural diagnostics so repairing one independent legacy issue is accepted while another unchanged issue remains, without new/worse unrelated invalidity. Never substitute bank/shortfall values for blocked accounting or authorize unverified edits beyond that dependency. Q7 bypasses financial comparison only, never new structural/input violations; derive all deficits/chains on replay and reject correction/confirmation batches mixed with planning intents. Later T034/T041/T048/T058 harden this implementation rather than introduce these handlers again.

### Canonical Persistence And Server Transport

- [X] T012 Add canonical storage/constraint tests in `apps/api/tests/repositories/test_plan_repository.py` using guarded SQL fixtures for 15 boundary slots, plan-scoped identities, transfer parents, positive monetary inputs, receipt uniqueness, delete cascades and canonical chip clearing without legacy fallback.
- [X] T013 Extend `apps/api/src/api/models/entities.py` and add an additive Alembic revision under `apps/api/alembic/versions/` after the actual head: store "nonnegative `revision`", "`foundation_state` (`legacy_pending`/`ready`)", "nullable `starting_free_transfers` (0..5; N/A at GW1)", "boundary origin (`my_team_capture`, `legacy_first_gameweek_assumed`, `rebased_plan`, `earlier_horizon_assumed`)", "exactly 15 entries, unique `(plan_id, player_id)` and `(plan_id, slot_id)`", stable UUIDs/provenance/initial lineup, initial bank/declarations/initialization version/time and required `selling_price_tenths`. Transfer records include decision ID/GW FK, outgoing player/ownership, incoming player/acquisition ownership, saved outgoing market/incoming price and observation source/time/origin. Add "an additive nullable `planned_chip` field as the canonical chip input" and receipt "Unique `(plan_id, mutation_id)`" with "status `validated_pending`/`committed`", digest/expected revision, evaluator/rule fingerprint excluding live prices and minimal pending inputs/committed revision. Enforce FKs/basic value constraints in SQL and aggregate composition in the engine; quarantine original columns/rows, with no new accounting/status/member caches or rollback payloads.
- [X] T014 Add repository loading/atomicity tests in `apps/api/tests/repositories/test_plan_repository.py` for a consistent parent/children revision snapshot, minimal pending inputs, sale-materialization writes, revision increments and rollback; use `TEST_DATABASE_URL` and the existing `_test` guard before setup.
- [X] T015 Implement coherent aggregate loading, plan-row locking, canonical delta persistence and receipt lifecycle in `apps/api/src/api/repositories/plan_repository.py`; retain IDs/digests and unresolved pending inputs for the plan lifetime, drop only redundant committed quote payloads, cascade on plan deletion, and store no old base or full candidate snapshots.
- [X] T016 Define strict read/envelope/intent/result/error schemas in `apps/api/src/api/schemas/plans.py` from the API contract: UUID mutation IDs, expected revision, field intents, explicit decision/source IDs, integer `_tenths`, GW1 N/A and blocked accounting nullability; reject browser-authored quotes, derived bank and whole-GW membership writes; preserve existing name/horizon bounds rather than inventing new ones.
- [X] T017 Add service/route contract cases in `apps/api/tests/plans/test_plan_services.py` and `apps/api/tests/plans/test_plans_router.py` for all documented 200/409/422/503 outcomes, receipt lookup/404, pre-acceptance failure, durable accepted-not-saved failure, uncertain COMMIT and retired writers; distinguish domain 422 from schema 422. Exercise the T011 horizon/transfer/chip/correction handlers through this path before T028, including revision-aware rename success, technical failure/retry and stale revision, with no fallback to PATCH and non-writing 410 from that retired route.
- [X] T018 Implement the one-call mutation orchestrator in `apps/api/src/api/services/plans.py`: lock/check ID/digest before revision, capture prices only for new/explicitly edited decisions, evaluate and durably save the minimal pending receipt, then in a second bounded transaction recheck receipt status/digest under the final lock before base compatibility and atomically write canonical inputs/sales/revision/commit receipt. Integrate all core handlers assigned to T011, including rename/horizon/transfer/repair and starting-basis correction/confirmation, with checked decimal-to-tenths stored-price adapters, source decision IDs and atomic dependent sale updates before T028. Return `already_committed` for a duplicate committed between stages; never describe both stages as one atomic transaction. T049/T059 add hardening, not another orchestration/capture path.
- [X] T019 Add `POST /plans/{plan_id}/mutations` and `GET /plans/{plan_id}/mutations/{mutation_id}` in `apps/api/src/api/routers/plans.py`; implement compatible pending replay, stale `revision_conflict`/`stale_reprepare_required`, changed-digest `mutation_id_reused` and uncertain `outcome_unknown`; return non-writing 410 `planner_writer_retired` from old PATCH/full-GW PUT, retaining ordinary create/delete resource semantics and no public prepare/commit endpoints.
- [X] T020 Prove actual SQL receipt/transaction races in `apps/api/tests/repositories/test_plan_repository.py`: competing expected revisions, duplicate creation and duplicate final-lock arrival, pre/post-acceptance failures, partial-write rollback, uncertain COMMIT reconciliation, response/enrichment loss after commit, retry after later revision, stale rule context, and zero canonical/legacy changes through both retired writers; do not substitute fake-router results for SQL proof.
- [X] T021 Add once-only initialization cases in `apps/api/tests/plans/test_plan_services.py` for first-saved-GW assumed boundary, leading FH, period crossing, illegal legacy inputs, missing prices/players, checked decimal conversion, deterministic pairing, rerun skipping and no external FPL/My Team substitution. After initialization, submit a repair through the guarded mutation path for one of multiple independent legacy structural diagnostics; accept/save/reopen with the other unchanged diagnostic retained, no new/worse unrelated invalidity, and dependent accounting unavailable beyond a blocked dependency rather than invented bank/totals.
- [X] T022 Implement the initialization service in `apps/api/src/api/services/initialize_planner_foundations.py` and `--check`/`--apply` entrypoint in `apps/api/src/api/scripts/initialize_planner_foundations.py`: lock each plan and initialize atomically from stored observations; retain old bank/FT, no pre-used chips, assumed FH19 where applicable, copied slot lineups/chips and `legacy_initialized_estimate` quotes; use same-position-first/player-ID pairing once against inferred permanent state. Missing data leaves `legacy_pending` with explicit retryable diagnostics; GET never initializes and reruns never reprice.
- [X] T023 Add isolated guarded migration round-trip tests in `apps/api/tests/db/test_planner_foundations_migrations.py` for upgrade/backfill/downgrade/re-upgrade with unchanged original rows/values, nullable canonical chip clearing, no rollback copies, preservation of new plans, and refusal of unsafe in-place downgrade after new-only writes; implement the downgrade guard in the additive revision under `apps/api/alembic/versions/` and require backup/export plus explicit conversion/restore after new edits.
- [X] T024 Replace competing snapshot/accounting derivation in `apps/api/src/api/services/plan_accounting.py` and `apps/api/src/api/services/get_plan_view.py` with engine replay adapters; GET stays read-only/coherent, derives selling prices rather than trusting materialization, exposes blocked/initialization diagnostics and preserves existing projection enrichment/chip points effects without letting enrichment reprice saved decisions. Map the T011 chip availability/reasons and named conflicting GWs now, before the T028 controls and T037 verification; T042 only hardens this existing mapping/presentation.

### Minimal Shared Client Path

- [X] T025 Add strict Planner read/intent/mutation/receipt/error mappings in `apps/web/src/lib/api.ts`; migrate both board and plan-list rename clients away from full-GW PUT/PATCH, with no implicit-identity compatibility writer or fallback to retired PATCH, and preserve current live/read-only projection fields alongside integer canonical finances.
- [X] T026 Add coordinator tests in `apps/web/tests/plans/plan-save-coordinator.test.ts` for acknowledged revision, one in-flight immutable envelope, field-only queue dispatch, basic same-ID retry and navigation-independent state, using the stateful fixtures from T003. Add plan-list rename regression cases in `apps/web/tests/plans/plans-list.test.tsx` for obtaining the current plan/revision before constructing the guarded rename intent, successful acknowledgement/list refresh, stale revision, visible technical failure with retryable same-ID context and no false saved claim; assert POST mutation requests and zero PATCH fallback.
- [X] T027 Implement the minimal plan-scoped coordinator in `apps/web/src/lib/plan-save-coordinator.ts`: construct envelopes/IDs only at dispatch against the latest acknowledgement, never queue captured lineups/squads, pause behind unresolved accepted/unknown outcomes and maintain distinct acknowledged, pending-intent and accepted-unsaved state.
- [X] T028 Wire existing Planner name/horizon/chip/captain/transfer callers in `apps/web/src/components/plans/plan-board.tsx` and the rename flow in `apps/web/src/components/plans/plans-list.tsx` to the coordinator and source decision IDs; the list obtains the current plan/revision before dispatch, updates after acknowledged rename and retains visible retryable failure context without PATCH fallback. Remove manual Save Gameweek/full-snapshot writes, show basic persistence/initialization status and render all engine-provided chip states/reasons, including used-before versus planned-elsewhere and named conflict GW. Require T011 core handlers, T018 orchestration and T024 read mapping to pass before this gate; run their focused suites, T026 rename/coordinator regressions and guarded T012/T014/T020/T023 SQL cases per `specs/002-planner-foundations/quickstart.md`. No handler, reason rendering or caller migration required here is deferred to a story task.

**Checkpoint**: One replay authority and guarded writer serve the existing Planner controls; new editing is unavailable for uninitialized plans. Canonical write, retry and migration guarantees have owning-layer evidence. This is not approval to deploy a partial feature.

## Phase 3: User Story 1 - Establish A Plan's Starting State (Priority: P1)

**Goal**: Establish and revise remaining FT, applicable used chips/FH19 and visible editable plan-specific purchase bases without blocking confirmation or reconnecting to My Team.

**Independent Test**: Create a GW12 plan with FT3 and WC used before the plan; reload and verify FT3, WC unavailable in GW12-19 with the stated reason and available from GW20. Confirm estimated starting bases do not block use, and a contradictory used-chip edit names the conflicting planned GW and changes nothing.

### Tests

- [X] T029 [P] [US1] Add starting-state/default/contradiction cases in `packages/fpl_engine/tests/test_planning.py`: FT whole integers 0..5/default1 after GW1, GW1 N/A/no declarations, GW20 only FH19/no used second-period chips, GW25 second-period declarations, and conflicting planned-GW diagnostics (FR-001-FR-007; SC-001).
- [X] T030 [P] [US1] Add creation/legacy-independence/horizon tests in `apps/api/tests/plans/test_plan_services.py`: My Team FT differs from default1, capture membership/bank once, preserve old FT on migration, moving start earlier/later across periods and FH19, reject unresolved prefixes, preserve retained quotes/lineups and editable carried acquisition provenance (FR-008; Q5-Q7).
- [X] T031 [P] [US1] Add starting-panel tests in `apps/web/tests/plans/plan-board.test.tsx` for all boundary modes, lightweight per-player Estimated and concise plan indication, correction/confirmation without an all-15 gate, automatic saving and explicit contradictory-edit feedback.

### Implementation And Verification

- [X] T032 [US1] Implement starting FT/declaration and conflict validation in `packages/fpl_engine/src/fpl_engine/planning/mutations.py` using the shared chip authority in `packages/fpl_engine/src/fpl_engine/rules/chips.py`; enforce "No used chips at GW1 or second-period used chips at GW20" and preserve conflicting decisions rather than clearing them.
- [X] T033 [US1] Update creation and starting-state orchestration in `apps/api/src/api/services/plans.py` to capture an independent My Team boundary once, default post-GW1 FT to1 rather than copying My Team, initialize unknown prices as assumed, preserve original source separately from confirmation, and keep legacy initialization/readiness explicit.
- [X] T034 [US1] Harden the T011/T018 horizon implementation with integration regressions in `apps/api/tests/plans/test_plan_services.py`: rebase only a valid permanent prefix, preserve slots/ownership/inline provenance/bank assumptions/FT/applicable chip use/FH19, and verify hypothetical earlier starts, final-FH extension and trims. Exercise repeated rebase/extend/trim followed by starting-field edits and reopen; reject unresolved prefixes and prove no dangling deleted acquisition sources or changed retained quotes/lineups. Repair only defects exposed by these cases in `packages/fpl_engine/src/fpl_engine/planning/mutations.py` or `apps/api/src/api/services/plans.py`; do not reimplement the handlers already required before T028.
- [X] T035 [US1] Add the starting-state panel to `apps/web/src/components/plans/plan-board.tsx` with remaining-FT numeric input, period-specific chip toggles, FH19 control when applicable, editable basis/confirmation and lightweight provenance; use coordinator intents, preserve frozen boundary bank and original captures when correcting a rebased basis, and leave starting membership/bank noneditable.
- [X] T036 [US1] Add durable creation/reload and rebased-plan edit journeys to `apps/web/tests/e2e/planner-foundations.spec.ts` (validation-guide journeys1/7): FT/chips/basis, no confirmation gate, independent My Team capture, retained transfer edit after rebase, preserved sources and no fabricated history; use deterministic stateful fixtures.
- [X] T037 [US1] Run starting-state engine/API/component cases and T036's browser cases, including FT0 first-GW accounting and GW1/20/25 boundaries; verify used-before/planned-elsewhere/rule explanations and named conflicts through the T011/T024/T028 chip path, plus retained transfer/horizon/correction edits through T011/T018. These implementations are prerequisites already completed, not work deferred to US2/US3/US4; record actual SC-001 and relevant SC-005/006 evidence or limitations in `specs/002-planner-foundations/quickstart.md` without weakening this gate.

**Checkpoint**: Starting state can be established, edited, saved and reopened without another story's UI. Full price inspection/resolution UX is completed in US4; comprehensive autosave failure UX is completed in US5.

## Phase 4: User Story 2 - Plan Chips Across Both Periods (Priority: P1)

**Goal**: Offer only legal chip choices with distinct used-before/planned-elsewhere/rule reasons, including cross-boundary FH restrictions.

**Independent Test**: In GW17-22 with first-period FH used before the plan, place WC18; verify WC elsewhere in17-19 names18, FH17-19 says used before, both reset in20-22, and clearing WC18 restores first-period availability. Direct illegal requests must reject identically.

### Tests

- [ ] T038 [P] [US2] Extend `packages/fpl_engine/tests/test_rules.py` for exactly WC/FH/BB/TC, once per period, one per GW, unused first-period lapse, WC/FH GW1 rejection and BB/TC acceptance, FH19/20 rejection in either order/declaration direction, chip moves/removals and named conflicts (FR-009-FR-018; R-01-R-04).
- [ ] T039 [P] [US2] Add bypass/move/remove/read-model cases in `apps/api/tests/plans/test_plans_router.py` for the same rule messages and canonical `planned_chip=null` despite populated quarantined `chip`; assert rejection writes nothing.
- [ ] T040 [P] [US2] Add chip-state component cases in `apps/web/tests/plans/plan-board.test.tsx` for available/planned-here/planned-elsewhere/used-before/rule-unavailable and visible conflicting GW; BB/TC activation alone changes neither allowance nor bank.

### Implementation And Verification

- [ ] T041 [US2] Harden the T011 chip handlers in `packages/fpl_engine/src/fpl_engine/rules/chips.py` and `packages/fpl_engine/src/fpl_engine/planning/mutations.py` against T038/T039's full two-period matrix, atomic moves to an occupied GW and reversed FH19/20 conflicts; fix only demonstrated gaps, preserving contradictory decisions and frozen quotes. Core availability/reasons and activate/remove/move already work before T028; do not implement a second rule path.
- [ ] T042 [US2] Harden the T024/T028 chip mapping/presentation in `apps/api/src/api/services/get_plan_view.py` and `apps/web/src/components/plans/plan-board.tsx` using T039/T040's clear/move/period-reset scenarios: verify reason updates after acknowledgement, canonical null without legacy fallback and distinct used-before/planned-elsewhere states. Fix only additional integration defects; core controls/reasons were required before T037, with no frontend rule authority or projected-points changes.
- [ ] T043 [US2] Extend `apps/web/tests/e2e/planner-foundations.spec.ts` with period-reset, forbidden GW1/FH19-20, planned/used reasons, clear/move and FH/WC toggle journeys; assert no phantom downstream transfer or quote refresh (journeys1/4).
- [ ] T044 [US2] Run chip rule/router/component cases and T043's browser cases and record SC-003/004 plus direct-request SC-009 results in `specs/002-planner-foundations/quickstart.md`.

**Checkpoint**: All chip states are understandable and enforced by the engine through direct requests, independently of transfer-exploration features.

## Phase 5: User Story 3 - Transfers, Hits And Squad Flow (Priority: P1)

**Goal**: Make every GW's FT/count/hit/next FT/bank and plan total hit follow explicit net decisions, permanent/FH ownership and local lineup choices.

**Independent Test**: Start GW8 FT2, make1/0/4 transfers in8/9/10; available FT2/2/3, GW10 hit4, GW11 FT1. WC11 with available1 leaves nextFT1; WC with available3 leaves nextFT3. FH restores permanent membership/bank before subsequent decisions, with first-GW transfers counted.

### Tests

- [ ] T045 [P] [US3] Extend `packages/fpl_engine/tests/test_planning.py` with the independent FT/count/hit chain, cap5, starting0, first/last chip, adjacent FH/WC, BB/TC ordinary cases, cross-GW buy-back identities, unordered simultaneous net sets and local lineup preservation (FR-019-FR-029, FR-033, FR-047; SC-002).
- [ ] T046 [P] [US3] Extend `apps/api/tests/plans/test_plan_accounting.py` and `apps/api/tests/plans/test_get_plan_view_service.py` to assert read labels/counts/bank derive from the same replay, Example A toggles never infer transfers, Example B rejects upstream-only change, and explicit repair batches remove/replace the chosen downstream decision atomically.
- [ ] T047 [P] [US3] Add accounting/inline-transfer component cases to `apps/web/tests/plans/plan-board.test.tsx` for first-GW moves, unlimited display, nextFT/total hit, blocked-GW unavailable totals, intended missing outgoing identity and explicit repair choices rather than automatic retargeting.

### Implementation And Verification

- [ ] T048 [US3] Harden T011's existing transfer/net-repair validation in `packages/fpl_engine/src/fpl_engine/planning/mutations.py` and `packages/fpl_engine/src/fpl_engine/planning/evaluate.py` with adversarial ownership/rebuy/atomic-set cases in `packages/fpl_engine/tests/test_planning.py`. Explicitly repair one of multiple independent legacy structural diagnostics while another remains: accept if no unrelated invalidity is introduced or worsened, retain unavailable accounting beyond blocked dependencies, reject unverified downstream edits and never fabricate bank/shortfall values. Preserve frozen quotes, forbid same-GW acquired outgoings and reject new blockers under Q2; do not recreate core handlers already completed before T028.
- [ ] T049 [US3] Harden the T018/T024 transfer integration in `apps/api/src/api/services/plans.py` and `apps/api/src/api/services/get_plan_view.py` against explicit atomic repair batches and repeated same-GW acquisition selection: prove source ownership/decision IDs select the original acquisition edit, not a round trip, and deterministic impact diagnostics match the engine. Use `apps/api/tests/plans/test_get_plan_view_service.py` for blocked-state/read-label regressions and fix only exposed adapter defects; orchestration and removal of competing arithmetic were completed in T018/T024, not repeated here.
- [ ] T050 [US3] Extend the T028 inline-transfer integration in `apps/web/src/components/plans/plan-board.tsx` with FT available/made/hit/nextFT/bank/total-hit display and explicit impact-repair controls; use user-chosen remove/replacement batches, preserve the previous accepted state on rejection and unavailable totals when blocked. Reuse existing guarded transfer wiring; do not redesign inline transfer discovery or link to Explorer.
- [ ] T051 [US3] Add direct API legality/repair/reopen cases to `apps/api/tests/plans/test_plan_services.py` for formation/club/squad/captain constraints after propagated transfers, rejected wrong ownership episodes and completed-GW transfer edits using current prices only for the edited record. Cover multiple independent legacy diagnostics: repair one through a guarded atomic mutation, retain another unchanged diagnostic after save/reopen, reject new/worse unrelated invalidity and unverified edits beyond a blocked dependency, and assert downstream accounting is unavailable rather than invented.
- [ ] T052 [US3] Extend `apps/web/tests/e2e/planner-foundations.spec.ts` with hand-calculated accounting, Example A, Example B rejection plus explicit atomic repair, FH/WC edges and independent per-GW lineup roles (journey4).
- [ ] T053 [US3] Run transfer-rule/replay/accounting/view/router/component cases, including T010/T021/T048/T051's independent legacy repair and blocked-accounting cases, and T052's browser cases; record SC-002/009, FR-008/027/040 repair acceptance and no-competing-accounting/no-phantom-decision evidence in `specs/002-planner-foundations/quickstart.md`.

**Checkpoint**: Deterministic carried state and accounting are correct through first-GW, chip and explicit dependency-repair cases. No saved output creates a new command.

## Phase 6: User Story 4 - Official Selling Prices And Financial Resolution (Priority: P1)

**Goal**: Preserve captured financial assumptions while correctly carrying ownership bases, accepting truthful provenance corrections and exposing/repairing derived shortfalls.

**Independent Test**: P50 with market53 sells51; market48 sells48. Save P50/M54/sale52, move live market to56, correct starting basis48: sale51, incoming price and M54 unchanged, bank decreases1. Persist/reopen any resulting deficit, repair `(-1,-3)->(0,-2)`, and derive GW10 as the new earliest issue.

### Tests

- [ ] T054 [P] [US4] Extend `packages/fpl_engine/tests/test_planning.py` for all sale steps, retained/new WC bases, later buy-back, temporary/restored FH sales, upstream acquisition edits versus Q7, confirmation-only provenance, branch-aware provisional status and deficits persisting through later positive bank (FR-030-FR-036, FR-048/FR-049; SC-005).
- [ ] T055 [P] [US4] Add price-capture/correction/refresh service tests to `apps/api/tests/plans/test_plan_services.py`: P50/M54/live56/correct48 -> sale51, unchanged incoming price, explicit edits recapture only their record, positive integer input rejects zero, missing observation errors are explicit, and mixed Q7/planning batches reject.
- [ ] T056 [P] [US4] Add price/provenance/status tests in `apps/web/tests/plans/plan-board.test.tsx` for live versus saved/basis/sale, explicit visible saved-price policy, lightweight estimates, provisional versus requires-resolution versus saved, negative bank as shortfall, earliest-GW navigation and retained decisions during repairs.

### Implementation And Verification

- [ ] T057 [US4] Complete ownership-basis and financial dependency evaluation in `packages/fpl_engine/src/fpl_engine/planning/evaluate.py`: carry permanent acquisition bases, preserve corrected underlying FH ownership, retain provisional bank dependencies independently of currently held players, and derive all negative nodes/reachable descendants without an FH-temporary-bank edge into restoration.
- [ ] T058 [US4] Harden T011's existing correct/confirm/upstream-acquisition handling in `packages/fpl_engine/src/fpl_engine/planning/mutations.py` with T054/T055's combined FH/WC/rebuy dependencies; same-player corrections preserve ownership keys, saved markets/incoming prices/identities stay fixed, confirmation changes no money, ordinary edits must not worsen any evaluable GW shortfall, and rebased starting-basis correction preserves original capture/value and frozen boundary bank. Fix only defects exposed by these cases; core correction support was required for US1, not deferred here.
- [ ] T059 [US4] Harden T018's checked decimal-to-tenths adapters and capture/correction persistence in `apps/api/src/api/services/plans.py` with `apps/api/src/api/repositories/plan_repository.py` using T055's price-refresh cases and T014/T020's rollback cases: only explicit records read latest stored prices, dependent sales use saved markets and sale outputs update atomically. Fix only additional precision/capture/transaction defects; do not introduce another price adapter or persistence path.
- [ ] T060 [US4] Expose inspection/provisional/shortfall/earliest-chain data in `apps/api/src/api/schemas/plans.py` and `apps/api/src/api/services/get_plan_view.py`; derive on every coherent GET, show blocked totals unavailable, and never clamp deficits or persist resolution/status permission markers.
- [ ] T061 [US4] Add contextual price inspection and repair/status presentation to `apps/web/src/components/plans/plan-board.tsx`: state the capture/refresh/correction policy explicitly, separate latest market from saved assumptions and purchase source/confirmation, show earliest reason/amount/chain, retain lightweight estimates, and permit correction/repair without speculative future-price inputs.
- [ ] T062 [US4] Add guarded SQL reopen/correction tests in `apps/api/tests/repositories/test_plan_repository.py`: verify frozen quotes after live refresh/lineup save, atomic dependent sale materialization, preserved decisions and replay-only resolution after reopen, moved-earliest repair, FH branch isolation and independence from quarantined financial fields.
- [ ] T063 [US4] Extend horizon/rebased-basis service cases in `apps/api/tests/plans/test_plan_services.py` for carried planned-acquisition correction, preserved original capture/boundary bank, retained transfer quote edit, no dangling prefix source, unresolved-prefix rejection and Q7 reopen independent of My Team.
- [ ] T064 [US4] Extend `apps/web/tests/e2e/planner-foundations.spec.ts` for saved/live price inspection, refresh stability, explicit quote edit, correction/shortfall/reload/repair, completed-GW edits and rebased purchase corrections (journeys3/7), using deterministic stateful market/error fixtures.
- [ ] T065 [US4] Run all pricing/replay/service/component cases, guarded T062 SQL cases and T064's browser cases; record hand-calculated SC-005 and relevant SC-007/009 evidence in `specs/002-planner-foundations/quickstart.md` without claiming browser mocks prove DB persistence.

**Checkpoint**: Price policy and official sale arithmetic are visible and stable; saved correction, provisional estimates and actual insolvency remain distinct, with derived issues surviving reopening and clearing after legal repair.

## Phase 7: User Story 5 - Persist Edits As The User Works (Priority: P2)

**Goal**: Finish robust queue/reconciliation/departure UX on the common guarded path, with no lost accepted edits or false saved/financial-valid claims.

**Independent Test**: Delay captain C in GW9, choose vice D and switch to GW10; dispatch vice-only at the acknowledged next revision, retain C, return/reload and see both after successful acknowledgement. Inject accepted canonical-write failure, retain the visible not-saved candidate across GW selection and retry the same ID/quotes.

### Tests

- [ ] T066 [P] [US5] Expand deferred/stateful coordinator tests in `apps/web/tests/plans/plan-save-coordinator.test.ts`: captain C then vice D, rejected predecessor, removed target reselection, sequence/generation/revision guards, plan switching, committed response with newer current plan, accepted-not-saved pause, stale explicit reconciliation, 404 while original remains in flight and missing-plan stop.
- [ ] T067 [P] [US5] Add component navigation/departure/failure cases to `apps/web/tests/plans/plan-board.test.tsx`: separate pending intent from durably accepted candidate; retain earlier accepted-unsaved/Q7 context after a new domain rejection; distinguish saving/saved/not saved from financial flags; assert no Save Gameweek control (FR-037-FR-042; SC-006/007).
- [ ] T068 [P] [US5] Extend API retry contract cases in `apps/api/tests/plans/test_plans_router.py` for compatible pending candidate reconstruction only, stale metadata without old candidate, committed ID before expected revision, newer current plan without old-candidate overlay, `outcome_unknown`, fresh `revision_conflict`, and same-ID retry after lookup404.

### Implementation And Verification

- [ ] T069 [US5] Complete serialization/rebasing/obsolete-response protection in `apps/web/src/lib/plan-save-coordinator.ts`: resolve field/decision intent only at dispatch, freeze sent envelopes, preserve latest accepted/acknowledged state, require reselection for disappeared identities and never rebuild queued full-lineup payloads.
- [ ] T070 [US5] Complete failure/lookup/retry state transitions in `apps/web/src/lib/plan-save-coordinator.ts` and `apps/web/src/lib/api.ts`: reconcile the same ID on uncertainty, retain accepted quote inputs through compatible retry, pause dependent writes, treat404 as inconclusive, require explicit new-ID stale reconciliation with visible new quotes and never silently merge cross-tab conflicts.
- [ ] T071 [US5] Implement pending/accepted-unsaved/rejected/stale/missing-plan controls and departure protection in `apps/web/src/components/plans/plan-board.tsx`; preserve coordinator state across GW selection, guard in-app and native departure that would lose work, expose retry/reconciliation and do not promise asynchronous unload persistence or treat queued unvalidated intent as accepted calculations.
- [ ] T072 [US5] Strengthen actual SQL fault/concurrency coverage in `apps/api/tests/repositories/test_plan_repository.py` for the final client-facing retry scenarios, including a duplicate reaching the final lock after commit, no double revision/write/reprice, stale pending rule fingerprint excluding live prices, and accepted correction rollback/retry without losing Q7 context.
- [ ] T073 [US5] Extend `apps/web/tests/e2e/planner-foundations.spec.ts` with delayed captain/vice navigation, canonical-write failure after receipt, lost-success reconciliation after later revision, stale conflicts, rejection preserving retry state, native/in-app departure guard and reload only after acknowledged commit (journeys2/5).
- [ ] T074 [US5] Run T066-T068 focused suites, T072 guarded SQL cases and T073 browser cases; inspect actual request intents/revisions and status transitions rather than relying on static save mocks, and record SC-006/007 evidence in `specs/002-planner-foundations/quickstart.md`.
- [ ] T075 [US5] Verify every Planner writer/caller in `apps/web/src/components/plans/plan-board.tsx`, `apps/web/src/components/plans/plans-list.tsx`, `apps/web/src/lib/api.ts` and `apps/api/src/api/routers/plans.py` uses the single guarded path for name/horizon/starting/GW edits. Rerun T017/T026's revision-aware plan-list rename success/stale/technical-failure/retry cases and assert zero PATCH fallback; old PUT/PATCH remain non-writing 410 Gone, no Save Gameweek remains and failed/pending persistence cannot be represented as saved. Fix only regressions within this story.

**Checkpoint**: Latest successfully persisted accepted state survives navigation/reopening; unresolved persistence is visible/retryable and cannot erase corrected provenance or financial issues.

## Phase 8: User Story 6 - Rearrange XI And Bench Like My Team (Priority: P3)

**Goal**: Use direct selection/target interaction and one authoritative legality/captaincy operation on both surfaces without changing My Team persistence or finances.

**Independent Test**: With the same squad on both screens, select a starter or bench player and compare legal targets/results. Swap, cancel/replace selection and reorder outfield substitutes; exclude GK/outfield reorder, inherit captaincy identically, autosave the Planner GW and preserve other GWs' lineup choices.

### Tests

- [ ] T076 [P] [US6] Extend `packages/fpl_engine/tests/test_rules.py` and `packages/fpl_engine/tests/test_planning.py` for shared legal target enumeration/swap, formation/position/club/bench/C/VC validation, outfield bench priority, GK exclusion, My Team captaincy inheritance and per-GW role isolation (FR-028, FR-043-FR-047; SC-008/009).
- [ ] T077 [P] [US6] Add direct illegal-swap/lineup request rejection and target/result parity cases in `apps/api/tests/plans/test_plans_router.py`, using the existing My Team service/router tests under `apps/api/tests/team/` to protect the additive target response and unchanged My Team save behavior.
- [ ] T078 [P] [US6] Add matching selection/cancel/replace/target/confirmation cases in `apps/web/tests/plans/plan-board.test.tsx` and `apps/web/tests/team/my-team-board.test.tsx`; assert bench visual order matches priority, GK exclusion, two-selection swaps, announcements and no former dropdown swap controls.

### Implementation And Verification

- [ ] T079 [US6] Implement shared pure rearrangement/target enumeration in `packages/fpl_engine/src/fpl_engine/rules/squad.py` and use it for Planner swap intents in `packages/fpl_engine/src/fpl_engine/planning/mutations.py`; retain existing authoritative squad validation and never introduce a separate React formation definition.
- [ ] T080 [US6] Wire shared legal targets/swap results through `apps/api/src/api/services/get_plan_view.py` and the existing My Team application service under `apps/api/src/api/services/`, with additive response/schema changes only where required; enforce direct requests through the same engine rules and preserve My Team's current persistence and market-price approximation.
- [ ] T081 [US6] Extract only reusable selection/announcement presentation into `apps/web/src/lib/squad-rearrangement.ts` and integrate `apps/web/src/components/plans/plan-board.tsx` with `apps/web/src/components/team/my-team-board.tsx`; reuse existing pitch/card/bench primitives, consume engine-provided targets, remove Planner dropdown/formation logic, keep independent page state and preserve existing My Team save behavior.
- [ ] T082 [US6] Extend `apps/web/tests/e2e/planner-foundations.spec.ts` with same-squad My Team/Planner legal-target/result parity, starter/bench selection, cancellation/replacement, outfield priority, GK exclusion, C/VC inheritance, visible confirmation and independent GW roles (journey6).
- [ ] T083 [US6] Run shared rule, Planner/My Team API and both component suites plus T082 browser cases; record SC-008/009 parity evidence and any unavoidable unverified states in `specs/002-planner-foundations/quickstart.md`.

**Checkpoint**: Direct rearrangement is consistent, accessible and server-authoritative on both screens, without sharing page state or broadening financial scope.

## Phase 9: Polish And Cross-Cutting Verification

**Purpose**: Verify the complete agreed feature, operator safety and final scope. No optional product improvements are included.

- [ ] T084 Audit FR-001-FR-049 and SC-001-SC-009 against actual owning-layer tests and all seven browser journeys; fill any missing in-scope acceptance cases in `packages/fpl_engine/tests/test_planning.py`, `apps/api/tests/plans/test_plan_services.py` or `apps/web/tests/e2e/planner-foundations.spec.ts` and record the evidence map in `specs/002-planner-foundations/quickstart.md`.
- [ ] T085 Run the full guarded Planner repository/migration suite via `Makefile`'s `test-integration` target on the dedicated `_test` database, including isolated round trips and downgrade refusal after new-only writes; report explicit skips/failures, never substitute development data or weaken `ensure_test_database_url`.
- [ ] T086 Run mise-pinned `make lint`, `make typecheck`, `make test` and `pnpm --filter web build`, plus the durable `apps/web/tests/e2e/planner-foundations.spec.ts` suite; fix only feature regressions, rerun affected checks and record actual outputs/limitations in `specs/002-planner-foundations/quickstart.md`.
- [ ] T087 Follow `.github/skills/ui-browser-verification/SKILL.md` on actual desktop1440x900/mobile390x844 rendering: starting/chip/price/resolution/persistence controls, long names, loading/empty/blocked/error/pending states, keyboard/focus/announcements, tap targets and no clipping/overlap; inspect console/network and request counts/responsiveness, capture screenshots and record results in `specs/002-planner-foundations/quickstart.md`. Use isolated/stateful fixtures for synthetic failures, not destructive development mutations.
- [ ] T088 Update operator/developer instructions in `README.md` and `specs/002-planner-foundations/quickstart.md` with actual readiness/check/apply commands, backup and explicit-approval requirements, coordinated web/API writer switch, pending-plan diagnostics and rollback limits; document that after new-only writes backup/export plus conversion/restore is required, not a claimed lossless downgrade.
- [ ] T089 Perform independent read-only review using `.github/skills/code-review/SKILL.md` against `specs/002-planner-foundations/spec.md`, the accepted architecture and final implementation diff; resolve in-scope findings with focused rechecks, then repeat affected independent verification before declaring completion.
- [ ] T090 Inspect the complete final diff for unintended source/dependency/metadata changes and report files changed, material decisions/trade-offs, SC-001-SC-009 evidence, executed gates/browser results, known limitations and every skipped/unverified requirement in `specs/002-planner-foundations/quickstart.md`; do not mark a task done solely on the implementer's narrative or commit/create a branch without a user request.

## Dependencies And Execution Order

### Phase Graph

```text
Setup T001-T003
  -> Shared domain T004-T011
  -> Canonical persistence/transport T012-T024
  -> Minimal client T025-T028
  -> US1 T029-T037 (P1 starting state)
  -> US2 T038-T044 (P1 chips)
  -> US3 T045-T053 (P1 transfer flow)
  -> US4 T054-T065 (P1 prices/resolution)
  -> US5 T066-T075 (P2 persistence UX)
  -> US6 T076-T083 (P3 rearrangement)
  -> Completion T084-T090
```

This is the safe default implementation order, not a claim that unrelated work is inherently sequential. The domain functions needed by multiple stories are foundational; subsequent story phases use and extend them rather than replacing them. All story phases require T028. The default sequence avoids concurrent edits to the shared board, service, evaluator and test files.

### Concrete Prerequisites

| Tasks | Prerequisites / reason |
|-------|------------------------|
| T002-T003 | T001; disjoint fixture files may proceed together. |
| T004-T011 | Setup complete; value tests -> values -> primitive tests/implementation -> replay/core-intent tests -> replay -> candidate/legacy-repair comparison tests -> core handlers/validation. T011 owns the horizon/transfer/chip/correction prerequisites needed by earlier gates; no later story is a prerequisite for those handlers. |
| T012-T015 | T005 value shapes agreed; SQL tests -> additive models/schema -> repository tests/implementation. Complete T011 before aggregate integration. |
| T016-T020 | Engine/repository ready; schemas -> service/route/rename tests -> full core-handler orchestration -> router -> actual SQL concurrency proof. T018 integrates T011 horizon/transfer/repair/correction before client wiring. Inject post-commit enrichment/response failure at the service/router boundary; rerun those cases after T024's read-adapter change as part of T028. |
| T021-T023 | Engine and additive schema/repository ready; initialization tests -> service/CLI -> isolated migration round-trip/downgrade guard proof. No live operator apply is implicit in these tasks. |
| T024-T028 | Engine, repository and mutation/initialization contracts ready; chip-reason/read adapter -> strict client -> queue/plan-list rename tests -> coordinator -> board/list integration with reasons and foundation checks. T028 requires working T011/T018 handlers and T024 chip reasons, not future T034/T041/T048/T049 implementation. |
| US1 | Foundation; adds boundary controls/declaration integration and repeated-horizon regression proof using existing T011/T018 handlers. T037 requires chip-reason rendering already provided by T024/T028, not US2, and correction/retained-transfer support already provided by T011/T018, not US3/US4. |
| US2 | Foundation and US1 declaration integration; adds full chip-matrix/move/period-reset hardening to existing T011/T024/T028 behavior, without needing US3/US4 UI or reimplementing core rules/rendering. |
| US3 | Foundation and US2 chip hardening; adds accounting/impact-repair presentation and adversarial transfer/legacy-repair proof to existing T011/T018 integration. Accounting tests use frozen synthetic prices, independent of US4 inspection UI. |
| US4 | Foundation and US3 transfer integration; starting inputs come from US1, chip branches from US2. |
| US5 | Foundation's coordinator/receipt contract plus US1-US4 edits/statuses for full cross-operation error preservation. |
| US6 | Foundation and US5 saving UX; domain target work can start earlier after T011, but full parity verification needs integrated Planner/My Team responses and client controls. |
| T084-T090 | All stories complete; final review follows implementation/gates and documentation, and final reporting follows resolution/rechecks. |

Within each story, its first test tasks precede implementation, then browser coverage and focused execution. A test may initially fail from missing behavior, but its fixture or import must not be mistaken for the intended failure. Each implementation task includes rerunning the smallest relevant test/type check before further work. Run SQL migration suites serially or on separate isolated fixtures; never parallelize destructive setup against one database.

### Parallel Opportunities

- Setup: T002 and T003 after T001.
- US1: T029, T030 and T031 after T028; separate engine/API/component files.
- US2: T038, T039 and T040 after US1's gate; separate rules/router/component files.
- US3: T045, T046 and T047 after US2's gate; separate engine/API/component files.
- US4: T054, T055 and T056 after US3's gate; separate engine/API/component files.
- US5: T066, T067 and T068 after US4's gate; separate coordinator/component/router files.
- US6: T076, T077 and T078 after US5's gate; separate engine/API/component files.
- Do not run multiple story implementations against the same board/service/replay files concurrently. Do not infer additional `[P]` opportunities merely because two tasks use different layers: their contract prerequisites still apply.

## Parallel Examples By User Story

Each row is one permissible concurrent test-writing wave after its phase prerequisites; join and review the tests before implementation. These examples schedule work, not subagents or concurrent database mutation.

| Story | Parallel example |
|-------|------------------|
| US1 | T029 starting-state engine cases + T030 capture/rebase API cases + T031 starting-panel component cases. |
| US2 | T038 chip rule cases + T039 direct-route/clearing cases + T040 chip-state components. |
| US3 | T045 accounting/replay cases + T046 accounting/read service cases + T047 inline-transfer components. |
| US4 | T054 basis/dependency engine cases + T055 capture/correction service cases + T056 inspection/status components. |
| US5 | T066 deferred coordinator cases + T067 navigation/failure components + T068 receipt API contracts. |
| US6 | T076 rearrangement engine cases + T077 direct-request API parity cases + T078 Planner/My Team components. |

## Requirements And Acceptance Coverage

Ranges below include both endpoints. Shared prerequisites are traced as well as story-specific work so no acceptance item is assigned only to a UI test.

| Requirements / decisions | Owning tasks and verification |
|--------------------------|-------------------------------|
| FR-001-FR-008; SC-001 | T004-T005, T013, T021-T024, T029-T037; independent capture, legacy usability, chip contradictions and boundary/horizon edits. |
| FR-009-FR-018; SC-003/004; R-01-R-04 | T006-T011, T024/T028/T037, T038-T044; core reasons/rendering before the US1 gate, then full chip-matrix/period/move hardening, GW1/FH19-20 and BB/TC ordinary effects. |
| FR-019-FR-025; SC-002; R-05-R-08 | T006-T009, T024, T045-T053; hand-calculated FT/hits, unlimited cases, first-GW comparison and display. |
| FR-026-FR-027, FR-033; R-10-R-12 | T008-T011, T018, T034, T045-T053, T054/T057-T059; core horizon/transfer support precedes T028, then ownership/permanence, Examples A/B and explicit repair hardening, with no output-to-command conversion. |
| FR-028-FR-029, FR-043-FR-047; SC-008/009 | T004-T011, T045/T048/T051, T076-T083; legality across transfers/direct requests, local roles and My Team rearrangement parity. |
| FR-030-FR-032, FR-034-FR-036; SC-005; R-09 | T005-T011, T013/T024, T031/T035, T054-T065; integer sales, assumed/confirmed/source separation, live/saved inspection, visible policy and refresh stability. |
| FR-037-FR-042; SC-006/007 | T014-T020, T025-T028, T066-T075; receipt acceptance/atomic write/lookup, field-intent queue, board and plan-list guarded rename migration, failure retention, departure protection and no manual save. |
| FR-008/FR-027/FR-040 legacy structural repair | T010-T011, T021, T048/T051/T053; accept repair of one independent diagnostic while another unchanged one remains, reject new/worse unrelated invalidity and unverified blocked descendants, and preserve unavailable accounting without fabricated bank/shortfalls. |
| FR-048-FR-049 and qualified FR-006/FR-027/FR-032/FR-034/FR-040 | T010-T011, T017-T020, T054-T065, T067/T072-T074; saved-market corrections, deficits/FH chains, non-worsening repair, no persisted validity markers and reopen evidence. |
| Q5 completed GWs; independent/rebased plans | T030/T034-T037, T051, T058/T063-T065; no history lock, explicit transfer edits use current quotes only for that record, rebased bases remain editable without changing frozen bank/original captures. |
| Migration, writer retirement and rollback | T012-T024, T028, T039, T075, T085/T088; canonical nullable chip isolation, once-only conversion, coherent reads, original legacy preservation and safe downgrade refusal. |
| All SC-001-SC-009; constitutional gates | T084-T090 plus each story gate; actual SQL/browser evidence, strict typing, build, independent review, final scope inspection and limitations report. |

## Implementation Strategy

### MVP First

1. Finish Setup and Foundation, including actual isolated SQL proof and the minimal shared autosave path.
2. Deliver US1 as an internal starting-state increment; validate its independent scenario and durable reload/rebase cases before proceeding.
3. Do not present US1 alone as the completed foundations feature. The public readiness boundary includes all four P1 stories: trusted starting state, chips, accounting and prices/resolution. P2 autosave reliability and P3 rearrangement are also required for the approved feature's final acceptance.

### Incremental Delivery

1. Implement each phase as small tested changes at the owning layer; reuse foundation contracts throughout.
2. Finish P1 stories in the default dependency order, then harden cross-operation persistence in US5, then complete My Team parity in US6.
3. Use each story's independent scenario as its acceptance gate. Defer no required safety, receipt-durability or backend legality guarantee to browser-only verification.
4. Rehearse rollout on isolated fixtures; only explicitly authorized operators may initialize persistent plans after backup. Switch API/web writers together with no writable legacy fallback.
5. Execute the final gates and independent review, inspect the full diff and report actual evidence. Leave blocked/unverified tasks unchecked; neither this generated list nor an implementer's assertion is proof of completion.

## Notes

- All 90 tasks are initially unchecked. `[US1]` through `[US6]` map to specification stories, not implementation completion or release flags.
- `[P]` identifies test/fixture authoring opportunities, not permission for unattended concurrency or subagent delegation.
- No application source, migration, runtime test, database operation or browser session is executed by generating this document.
- No specification/architecture decision, checklist result, commit or branch change is implied by task generation.