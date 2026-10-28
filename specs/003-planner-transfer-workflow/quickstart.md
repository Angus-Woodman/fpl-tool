# Phase 003 Quickstart: Validation Guide

Run and validation guide for the planned design. It describes what to run and what must be observed once implemented; nothing here has been executed yet (planning stage). Contracts: [contracts/](contracts/). Model: [data-model.md](data-model.md).

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
  packages/fpl_engine/tests/test_planning_impact.py packages/fpl_engine/tests/test_planning_clone.py
PYTHONPATH=packages/fpl_engine/src uv run --package api pytest -q apps/api/tests/plans apps/api/tests/transfers
pnpm --filter web test:run -- tests/transfers tests/plans
```

Guarded integration subset:

```sh
mise exec -- env RUN_DB_TESTS=1 TEST_DATABASE_URL=postgresql+psycopg://fpl:fpl@localhost:5432/fpl_test \
  PYTHONPATH=packages/fpl_engine/src uv run --package api pytest -q \
  apps/api/tests/repositories/test_plan_duplicate_integration.py apps/api/tests/plans
```

## Validation scenarios

### Domain (fpl_engine)

| ID | Scenario | Pass when | Spec |
|---|---|---|---|
| D1 | For every pool candidate of each reference plan, compare the non-raising verdict with `apply_intents` | `confirmable` iff `apply_intents` does not raise; unavailable and blocked reasons match the raised diagnostics | SC-003, FR-016 |
| D2 | Ordinary, Wildcard, Free Hit, Bench Boost, Triple Captain gameweeks; first plan gameweek; starting FT 0; estimated purchase basis; unaffordable; same-gameweek replacement of a planned acquisition | bank, FT, hits, selling price and provisional flags equal hand calculations | SC-002 |
| D3 | Later planned decision sells the outgoing player or buys the candidate | state `blocked_by_later_decision`, correct gameweek and decision; values after the validity limit absent; no later decision altered | SC-015, FR-016 |
| D4 | Player starting GW7, benched GW8, captain GW9 | per-gameweek impact uses those roles (including Bench Boost and Triple Captain effects) | Q-6, FR-023 |
| D5 | Horizon extends past the plan end; final gameweek is ordinary; final gameweek is Free Hit | continuation uses the permanent (restored) squad and final-gameweek roles; labelled and totalled separately; illegal roles reported unavailable | Q-6, FR-023 |
| D6 | Clone | no shared identifier; `evaluate_plan(copy)` equals the source after id mapping; revision 0 | SC-010, FR-058 |
| D7 | Inputs unchanged | the input `Plan` and baseline evaluation compare equal before and after assessing all candidates | FR-028 |
| D8 | Regression | existing ranking, single-transfer, rules and planning tests pass unmodified | SC-013 |

### API and persistence

| ID | Scenario | Pass when | Spec |
|---|---|---|---|
| A1 | List and preview for a plan whose squad and bank differ from My Team | squad, bank, exclusions and money come from the plan; no My Team field used; `selling_price_is_approximate` absent | FR-003, SC-004 |
| A2 | Horizons from GW7 with full, partial and no projection coverage; completed gameweek; missing run; missing squad projections; selectability unknown | exact evaluated gameweeks `N..`, partial flagged, specific 422 codes, nothing zero-filled | SC-005, FR-021, FR-027 |
| A3 | Read paths on the guarded database | row counts, plan `revision` and `updated_at`, receipts and My Team rows identical before and after; no flush recorded | FR-028, SC-004 |
| A4 | Mutation guard: unchanged prices, changed outgoing price, changed incoming price, retry with same id | commit; `prices_changed` 422 with no receipt; identical retry resumes | Q-7, FR-033 |
| A5 | Selectability: non-selectable, unknown, unchanged incoming on edit, saved decision replay | rejected with specific codes; edit without incoming change accepted; replay unaffected | Q-3, FR-012 |
| A6 | Explorer-originated confirm followed by GET plan | later gameweeks recalculated; My Team squad, bank and free transfers byte-identical | FR-036, FR-037, SC-004 |
| A7 | Duplicate: ordinary plan; plan with Wildcard and Free Hit; estimated prices; shortfall; blocked decisions (guarded fixtures) | new plan evaluates identically modulo ids; stored selling prices identical; source revision, `updated_at`, receipts unchanged | SC-010, SC-012 |
| A8 | Duplicate refusals | legacy plan, stale revision, resumable pending receipt, deleted source all refused with the contract codes; stale pending receipt does not block; nothing created | FR-051 to FR-054 |
| A9 | Duplicate atomicity: inject failure after the plan row and after the starting players | no `plans`, `plan_starting_players`, `plan_gameweeks` or decision rows remain | FR-055, SC-011 |
| A10 | Concurrent duplication: two sessions on the same source; and on source and copy of one family | distinct names, consecutive numbers, no partial plans | FR-055, SC-011 |
| A11 | Independence: mutate the copy, then the source | neither shows the other's change; no shared identifiers | FR-058, SC-012 |
| A12 | Naming | spec examples, deleted-number reuse, 100-character fit, renamed original, case sensitivity | FR-049, FR-050 |

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
| W5 | Commit state machine (deferred promises) | saving then saved navigates only after acknowledged revision; double click sends once; `prices_changed` refreshes preview without resubmitting; not saved offers retry and check status; conflict calls `abandon()` and requires re-preview |
| W6 | Coordinator | `abandon()` semantics; existing coordinator tests unchanged |
| W7 | Plan page | header row, Duplicate gating for saved, saving, not saved, conflict, missing, not ready; single-flight; success navigates; error and unknown-outcome messages with Plans link; highlight and `gw` handling on arrival only |
| W8 | Shared departure guard | behaviour identical to before for the Planner; same warning in the Explorer |

### Browser (Playwright; isolated preview; 1440x900 and 390x844)

| ID | Journey | Observed |
|---|---|---|
| B1 | Plan, GW7 player, Explore, candidate list, Preview, Confirm, back on the Planner | same gameweek selected, incoming player highlighted and in view, notice shown, later gameweeks changed, My Team unchanged |
| B2 | Reload inside the Explorer; open the address in a new tab; browser Back and Forward | same mode, plan, gameweek and player; no fall-through to My Team |
| B3 | Blocked candidate (later planned sale of the outgoing player) | visible, previewable, conflicting gameweek named, Confirm disabled, no repair offered, no later decision changed |
| B4 | Prices change between preview and confirm (guarded harness updates a stored price) | confirmation rejected, fresh preview shown, nothing saved |
| B5 | Save failure and conflict injected through the existing guarded fault harness | not saved with retry; conflict requires a fresh preview |
| B6 | Duplicate Plan: top-right control aligned with Back to plans; disabled while saving; success lands on the new plan with its name; edit the copy, original unchanged | as described; console free of errors and unexpected requests |
| B7 | Existing My Team Explorer journey | unchanged |

Report exactly what was observed, which states were not exercised, the preview port and cleanup result.

## Completion report (per AGENTS.md)

Files changed; important decisions and trade-offs; tests and checks run (with counts); browser verification performed; performance numbers (median and worst, dataset description); known limitations; anything not verified; and whether the final diff was reviewed for unintended changes.
