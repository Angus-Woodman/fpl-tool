# Phase 003 Quickstart: Validation Guide

Run and validation guide for the planned design (revised after the Phase 003 / Phase 004 split: Duplicate Plan validation was removed from this phase). It describes what to run and what must be observed once implemented; nothing here has been executed yet (planning stage). Contracts: [contracts/](contracts/). Model: [data-model.md](data-model.md).

## Prerequisites and safety

- Toolchain from `mise.toml` only (`mise exec -- ...`); project-local `.venv` and `node_modules`; PostgreSQL from Docker Compose (`make db-up`).
- **Database safety (AGENTS.md, constitution VII).** Integration tests run only against the dedicated database: `make db-test-up` creates `fpl_test`; tests use `TEST_DATABASE_URL`, `ensure_test_database_url` and isolated per-test schemas. Never point them at the development database, never truncate or reset development data, never bypass the `_test` guard. If the test database is unavailable, tests fail or skip through the existing mechanism.
- Existing ports 3000 and 8000 are user-owned; never kill or replace them. Production-build verification uses `NEXT_DIST_DIR=.next-copilot` through `make frontend-verify-build` and `make frontend-verify-preview FRONTEND_VERIFY_PORT=3100`, with mandatory cleanup (`make frontend-verify-clean`), per `.github/skills/ui-browser-verification`.
- No Alembic revision is part of this feature; `alembic upgrade head` must remain at `c6f91a2d83b0`.

## Quality gates (run in this order while iterating, all before completion)

1. Smallest relevant tests first (engine, then API, then web): see the focused commands below.
2. `mise exec -- make lint`
3. `mise exec -- make typecheck`
4. `mise exec -- make test` (engine, API and web unit suites; existing My Team Explorer, ranking and Planner suites must pass **unmodified**)
5. `mise exec -- make test-integration` (guarded PostgreSQL suite)
6. Web production build via the isolated targets above, then the Playwright journeys against that preview.
7. Independent review per `.github/skills/code-review/SKILL.md`; final `git diff` review for unintended scope (no dependency, migration, toolchain or unrelated Planner changes).

Focused commands (illustrative; paths from the plan):

```sh
uv run --package fpl-engine pytest -q packages/fpl_engine/tests/test_planning_hypothetical.py \
  packages/fpl_engine/tests/test_planning_impact.py
PYTHONPATH=packages/fpl_engine/src uv run --package api pytest -q apps/api/tests/plans apps/api/tests/transfers
pnpm --filter web test:run -- tests/transfers tests/plans
```

Guarded integration subset:

```sh
mise exec -- env RUN_DB_TESTS=1 TEST_DATABASE_URL=postgresql+psycopg://fpl:fpl@localhost:5432/fpl_test \
  PYTHONPATH=packages/fpl_engine/src uv run --package api pytest -q \
  apps/api/tests/repositories/test_plan_transfer_explorer_integration.py apps/api/tests/plans
```

## Validation scenarios

### Domain (fpl_engine)

Reference plans for the engine tests are built by `packages/fpl_engine/tests/planning_reference_plans.py` from pure engine objects. API tests build their own equivalents in `apps/api/tests/plans/explorer_builders.py`. Neither layer imports the other's test fixtures.

| ID | Scenario | Pass when | Spec |
|---|---|---|---|
| D1 | For every pool candidate of each reference plan, compare the non-raising verdict with `apply_intents` | `confirmable` iff `apply_intents` does not raise; unavailable and blocked reasons match the raised diagnostics | SC-003, FR-016 |
| D2 | Ordinary, Wildcard, Free Hit, Bench Boost, Triple Captain gameweeks; first plan gameweek; starting FT 0; estimated purchase basis; unaffordable; same-gameweek replacement of a planned acquisition | bank, FT, hits, selling price and provisional flags equal hand calculations | SC-002 |
| D3 | Later planned decision sells the outgoing player or buys the candidate | state `blocked_by_later_decision`, correct gameweek and decision; values after the validity limit absent; no later decision altered | SC-012, FR-016 |
| D4 | Player starting GW7, benched GW8, captain GW9 | per-gameweek impact uses those roles (including Bench Boost and Triple Captain effects) | Q-6, FR-023 |
| D5 | Horizon extends past the plan end; final gameweek is ordinary; final gameweek is Free Hit | continuation uses the permanent (restored) squad and final-gameweek roles; labelled and totalled separately; illegal roles reported unavailable | Q-6, FR-023 |
| D6 | Inputs unchanged | the input `Plan` and baseline evaluation compare equal before and after assessing all candidates | FR-028 |
| D7 | Regression | existing ranking, single-transfer, rules and planning tests pass unmodified | SC-010 |

### API and persistence

| ID | Scenario | Pass when | Spec |
|---|---|---|---|
| A1 | List and preview for a plan whose squad and bank differ from My Team | squad, bank, exclusions and money come from the plan; no My Team field used; `selling_price_is_approximate` absent | FR-003, SC-004 |
| A2 | Horizons from GW7 with full, partial and no projection coverage; completed gameweek; missing run; missing squad projections; selectability unknown | exact evaluated gameweeks `N..`, partial flagged, specific 422 codes, nothing zero-filled | SC-005, FR-021, FR-027 |
| A3 | Read paths on the guarded database | row counts, plan `revision` and `updated_at`, receipts and My Team rows identical before and after; no flush recorded | FR-028, SC-004 |
| A4 | Mutation guard: unchanged prices, changed outgoing price, changed incoming price, retry with same id | commit; `prices_changed` 422 with no receipt; identical retry resumes | Q-7, FR-033 |
| A5 | Selectability: non-selectable, unknown, unchanged incoming on edit, saved decision replay | rejected with specific codes; edit without incoming change accepted; replay unaffected | Q-3, FR-012 |
| A6 | Explorer-originated confirm followed by GET plan | later gameweeks recalculated; My Team squad, bank and free transfers byte-identical | FR-036, FR-037, SC-004 |
| A7 | Analysis on an in-memory `PlanningContext` with read-only fakes (no database); inspect the service's constructor dependencies | full list and preview results produced with no database; no plan repository, session or mutation service reachable from the analysis service; identical results to the router path | FR-047, SC-013 |
| A8 | Preview and list responses | each carries `planning_context` (plan, gameweek, revision); the commit descriptor's `expected_revision` equals it; a confirmation against an older revision is a conflict | FR-048, FR-034 |

### Performance gate (G-PERF; opt-in, guarded)

- Build a synthetic full-season dataset in an isolated schema of `fpl_test`: about 600 players across 20 clubs with realistic selectability flags, one `component_v3` run covering all remaining gameweeks, and a plan of 8 gameweeks that includes a Free Hit and later planned transfers.
- Time the list endpoint (midfielder pool, the largest) and the preview endpoint end to end through the ASGI app, at least 10 runs each, discarding the first (warm-up). Record median and worst.
- **Pass**: median list <= 3 s and preview <= 2 s. **Action threshold**: if either exceeds 70% of budget, apply the levers in [plan.md](plan.md) one at a time, each with its equality test, and re-measure.
- Also record a 38-gameweek plan (reported, not gating).
- Optional, with approval: the same read-only timing against the development database through the running API; no writes.

### Web (Vitest)

| ID | Scenario | Pass when |
|---|---|---|
| W1 | Entry wrapper | `plan` present renders Planner mode; absent renders the existing Explorer with its existing tests unchanged |
| W2 | Planner-mode states | loading, no outgoing player, empty pool, each unavailable code, invalid link, plan missing, plan not ready |
| W3 | Candidate table | search, filters, sorts, stable tie-break, active-filter chips, empty state; ranking order equals server order by default; no domain recalculation |
| W4 | Preview | saved-plan and assumed-continuation blocks separate and labelled; totals never summed; blocked candidate shows values only through the valid range and the conflicting gameweek and decision; Confirm disabled with the reason |
| W5 | Commit state machine (deferred promises), driven once through the `commit` prop with a fake adapter and once with the real coordinator; preview marked stale when the acknowledged revision changes; success only from the submission's own acknowledgement | saving then saved navigates only after acknowledged revision; double click sends once; `prices_changed` refreshes preview without resubmitting; not saved offers retry and check status; conflict calls `abandon()` and requires re-preview; a rejection (including `prices_changed`) keeps its message visible above the fresh preview, clears the record, never resubmits, and Confirm needs a new click that creates a new submission |
| W6 | Coordinator pinned submission ([contract](contracts/pinned-submission.md)) | see the dedicated matrix below; existing coordinator tests unchanged |
| W7 | Shared departure guard | behaviour identical to before for the Planner; same warning in the Explorer |
| W8 | Accepted-but-not-saved ([contract](contracts/pinned-submission.md)) | the warning is visible next to "Stop tracking this transfer" before the action; afterwards the not-added notice shows; no text says the transfer was saved, cancelled, deleted or removed (negated forms only); no navigation, no highlight; the reloaded plan lacks the transfer; a pending record cannot be read as committed; fresh preview required |
| W9 | Terminal record found on mount (`rejected`, `committed`, `plan_missing`) | message shown once and the record cleared with `abandon()`; no submission, no navigation; a following preview and confirmation work |

### Coordinator pinned submission matrix (Vitest, deferred promises; `apps/web/tests/plans/plan-save-coordinator-pinned.test.ts`)

| ID | Scenario | Pass when | Spec |
|---|---|---|---|
| C1 | `submitPinned` at the acknowledged revision | the envelope's `expected_revision` equals the pinned value; one POST; status `sending` | FR-049 |
| C2 | Acknowledged revision advanced after the preview (own earlier edit, `synchronize`, or a committed Planner edit) | refused `stale_preview`; no POST; nothing queued | FR-049, US2-18 |
| C3 | Coordinator busy (active envelope or queued edits) | refused `busy`; no POST; the queue and active envelope are unchanged | FR-049, FR-052 |
| C4 | Second pinned submission while one exists | refused `pinned_exists` | FR-049 |
| C5 | Intents no longer resolve against the acknowledged plan | refused `stale_preview`; no POST; no retargeting | FR-049 |
| C6 | Unrelated revision change or other mutation acknowledgement while pinned is `sending` | pinned does not become `committed`; only a response with the pinned mutation identity does | FR-050, US2-19 |
| C7 | `committed` and `already_committed` for the pinned identity | `committed` with the committed revision; acknowledged plan advances | FR-050 |
| C8 | 422 (including `prices_changed`) | `rejected` with diagnostics; no replay; queued Planner edits resume against the unchanged plan | FR-033, FR-052 |
| C9 | 409 `revision_conflict` / `stale_reprepare_required`, 410 | `conflict`; no second POST; `retry()` refused; `revalidate()` abandons (never replays) | FR-049, FR-051, FR-052 |
| C10 | Network failure, timeout, 503 `outcome_unknown` / `not_accepted`, 409 `mutation_id_reused`, malformed response | `unknown`; `abandon()` refused `reconcile_first`; `retry()` resends the same identity; `reconcile()` resolves to `committed`, `pending_unsaved` or stays `unknown` on 404 | FR-051 |
| C11 | 503 `accepted_not_saved` | `pending_unsaved`; same-identity `retry()` or `abandon()` allowed; no second identity | FR-051 |
| C12 | `abandon()` while `sending` | refused `outcome_pending`; nothing discarded | FR-051 |
| C13 | `abandon()` on `conflict` or `pending_unsaved` with the plan refresh succeeding | plan refreshed, only the pinned submission cleared, status recomputed | FR-051, US2-20 |
| C14 | `abandon()` when the plan refresh fails or the plan is missing | nothing discarded and message shown; missing plan becomes `plan_missing` | FR-051 |
| C15 | Planner edits queued behind or before a pinned conflict, then `abandon()` | no queued edit discarded; they resume against the refreshed plan with the existing rebasing; none replayed with stale values | FR-051, FR-052 |
| C16 | Planner edit enqueued while pinned is `sending` | queued behind it; dispatched after the pinned outcome against the then-acknowledged revision | FR-052 |
| C17 | Re-obtaining the coordinator after navigation (`getPlanSaveCoordinator`) | pinned state retained; `hasUnsavedWork()` true for `sending`, `unknown`, `pending_unsaved`, `conflict`, false for `committed`, `rejected` and after `abandon()` | FR-041, FR-051, US2-21 |
| C18 | Existing coordinator suites (`plan-save-coordinator.test.ts`) | all pass unmodified | FR-052, SC-014 |
| C19 | `abandon()` on `pending_unsaved` | result `abandoned` with `serverReceiptRetained: true`; only a plan load is sent (no mutation, no receipt request); the refreshed plan lacks the transfer; `pinned` is `null`, never `committed`; a later `submitPinned` uses a new mutation identity | FR-051, US2-22 |
| C20 | `abandon()` on `rejected` (including `prices_changed`) | result `abandoned` with `serverReceiptRetained: false` and the cleared record in `previous` (message and diagnostics); no server contact; Planner `error` status cleared; `hasUnsavedWork()` false | FR-034, US2-23 |
| C21 | After a rejection: unacknowledged record, then acknowledged | with the record present `submitPinned` is refused `pinned_exists` and nothing is sent; after `abandon()` a fresh `submitPinned` at the current revision sends a new identity; nothing is ever resubmitted automatically; Planner `enqueue` is unaffected by the record; the record survives `getPlanSaveCoordinator` | FR-034, FR-049, FR-052, US2-23, US2-24 |

### Browser (Playwright; isolated preview; 1440x900 and 390x844)

| ID | Journey | Observed |
|---|---|---|
| B1 | Plan, GW7 player, Explore, candidate list, Preview, Confirm, back on the Planner | same gameweek selected, incoming player highlighted and in view, notice shown, later gameweeks changed, My Team unchanged |
| B2 | Reload inside the Explorer; open the address in a new tab; browser Back and Forward | same mode, plan, gameweek and player; no fall-through to My Team |
| B3 | Blocked candidate (later planned sale of the outgoing player) | visible, previewable, conflicting gameweek named, Confirm disabled, no repair offered, no later decision changed |
| B4 | Prices change between preview and confirm (guarded harness updates a stored price) | confirmation rejected, message retained, fresh preview shown with the new prices, nothing saved or resubmitted automatically; an explicit second Confirm then saves it as a new submission |
| B5 | Save failure and conflict injected through the existing guarded fault harness; a competing Planner edit committed between preview and confirm | not saved with same-identity retry (and, for accepted-but-not-saved, "Stop tracking this transfer" with its warning and the not-added notice); conflict or stale preview requires a fresh preview; the transfer is never submitted against the newer revision; navigating away and back shows the unresolved submission |
| B6 | Existing My Team Explorer journey | unchanged |

Report exactly what was observed, which states were not exercised, the preview port and cleanup result.

## Completion report (per AGENTS.md)

Files changed; important decisions and trade-offs; tests and checks run (with counts); browser verification performed; performance numbers (median and worst, dataset description); known limitations; anything not verified; and whether the final diff was reviewed for unintended changes.

## Traceability (requirements to scenarios, contracts, validation and success criteria)

| Requirements | Spec scenarios | Contract | Validation | Success criteria |
|---|---|---|---|---|
| FR-001 to FR-007 mode and context | US1-1, 2, 12, 13; US3-4, 5 | [ui-navigation](contracts/ui-navigation.md); error table in [explorer API](contracts/planner-transfer-explorer-api.md) | A1, W1, W2, B2, B6 | SC-001, SC-007, SC-010 |
| FR-008 to FR-012 squad and pool, selectability | US1-3, 10, 11; US2-10 | explorer API candidates; [mutation guard and selectability](contracts/mutation-guard-and-selectability.md) | D2, A1, A5, W3 | SC-003 |
| FR-013 to FR-019 finance and accounting | US1-4, 5; US2-1, 3, 4, 5 | explorer API `outgoing`, `accounting_before`, preview `gameweeks` | D2, A1 | SC-002 |
| FR-020 to FR-027 projections and ranking | US1-6 to 9, 14 to 16 | explorer API `projection`, `plan_impact_by_horizon` | D4, D5, A2, W4 | SC-005, SC-006, SC-012 |
| FR-028 to FR-031 preview | US2-1 to 6, 14, 15 | explorer API preview | D3, D6, A3, W4, B3 | SC-004, SC-012 |
| FR-032 to FR-038 commit | US2-7 to 13, 16 | mutation guard; preview `commit` | A4, A5, A6, W5, B1, B4, B5 | SC-003, SC-004, SC-008 |
| FR-049 to FR-052 commit integrity (revision pinning, own acknowledgement, abandon, preserved guarantees); FR-034 rejected clearing | US2-18 to 24 | [pinned-submission](contracts/pinned-submission.md); mutation guard (revision pinning) | C1 to C21, W5, W6, W8, W9, B4, B5 | SC-014 |
| FR-039 to FR-042 navigation and states | US3-1 to 7 | ui-navigation | W5, W6, W7, B1, B2, B5 | SC-007, SC-008 |
| FR-043 to FR-046 comparison | US4-1 to 6 | explorer API candidate fields; ui-navigation screen contract | W3 | SC-009 |
| FR-047, FR-048 forward compatibility | US2-17 | `planning_context` in explorer API; `commit` prop in ui-navigation | A7, A8 | SC-013 |
| Performance targets | (SC-011) | explorer API non-functional | G-PERF | SC-011 |
| Regression of existing behaviour | US1-13; US4-6 | explorer API (My Team endpoints unchanged) | D7, B6 | SC-010 |

