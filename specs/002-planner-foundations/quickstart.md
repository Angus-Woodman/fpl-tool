# Planner Foundations Validation Guide

This guide retains the full feature's validation scenarios below. T001-T037 (shared foundations and US1 Starting State) and T038-T044 (US2 Plan Chips Across Both Periods) are implemented and verified as recorded here. US3 and later stories are not certified by these increments. See [plan.md](plan.md), [data-model.md](data-model.md) and [contracts/planner-api.md](contracts/planner-api.md); [spec.md](spec.md) remains the acceptance authority.

## Prerequisites And Safety

Use repository-root commands with the mise-pinned toolchain, project-local `.venv`/pnpm workspace dependencies and the existing environment setup in `README.md`. Current versions: Node 22.7.0, Python 3.12.15, uv 0.5.24, pnpm 9.9.0. Existing installed dependencies are sufficient; no new service is planned.

For DB-touching tests, `TEST_DATABASE_URL` must point to the dedicated database whose name ends `_test` (normally `fpl_test`). The existing `ensure_test_database_url` safeguard must run before destructive setup. Never substitute `DATABASE_URL`/development data, weaken the safeguard, or run an Alembic downgrade on the development database. If the test DB is unavailable, use the repository's explicit skip/fail path and report it. Migration round-trip fixtures require an isolated test database/schema and must not collide with concurrently running integration tests.

## Focused Automated Checks

### Increment 1 Preflight (2026-10-14)

Implementation scope is T001-T037 only (shared foundations and US1). Both
requirements-quality checklists passed before implementation (16/16 and 35/35).
`mise current` confirmed Node 22.7.0, Python 3.12.15, uv 0.5.24 and pnpm 9.9.0.
Run Alembic head inspection from `apps/api`; using `-c apps/api/alembic.ini`
from the repository root does not resolve the relative script directory:

```sh
cd apps/api && mise exec -- uv run --package api alembic heads
```

From the repository root, after the corresponding slice/tests exist:

```sh
mise exec -- uv run --package fpl-engine pytest -q packages/fpl_engine/tests/test_rules.py packages/fpl_engine/tests/test_planning.py
mise exec -- env PYTHONPATH=packages/fpl_engine/src uv run --package api pytest -q apps/api/tests/plans
mise exec -- pnpm --filter web test:run tests/plans/plan-board.test.tsx tests/team/my-team-board.test.tsx
```

`test_planning.py` contains the focused replay tests. Ordinary API runs skip DB-gated cases; do not mistake fake-boundary or skipped results for SQL proof.

With Docker running and the dedicated test URL confirmed:

```sh
mise exec -- make db-test-up
mise exec -- make test-integration
```

`make test-integration` uses `RUN_DB_TESTS=1` and `TEST_DATABASE_URL` through repository tooling. New Planner repository/atomicity/migration cases must join that guarded suite. Upgrade/backfill/downgrade/re-upgrade fixtures must create controlled legacy rows, compare them after rollback and remove only their isolated test resources. Do not replace `make test-integration` with a destructive ad-hoc script on the normal API connection.

## Initialization And Rollout Verification

The implemented `api.scripts.initialize_planner_foundations` entrypoint provides `--check` (read-only readiness/diagnostic report) and `--apply` (once-only per-plan transactional initialization). Tests call its service against guarded isolated fixtures; do not run the operator apply procedure on development data merely to test it.

Operational sequence after implementation: take a normal database backup, apply additive schema, run `--check`, explicitly run `--apply`, review its report, then switch the web/API writers together. Pending plans remain explicitly unavailable for editing with retryable diagnostics; there is no legacy write fallback. GET must not initialize them. Before any new application edits, isolated downgrade tests prove old rows untouched without per-plan rollback payloads. After new-only writes, rollback requires explicit backup/export plus conversion/restore; a downgrade must refuse a falsely lossless in-place conversion.

Read-only readiness command, after an operator applies the additive schema:

```sh
cd apps/api && PYTHONPATH=src:../../packages/fpl_engine/src mise exec -- uv run --package api python -m api.scripts.initialize_planner_foundations --check
```

Explicit operator approval/backup is required before using `--apply` against persistent data. Integration fixtures must still use `TEST_DATABASE_URL`/the existing safeguard before initialization or schema setup. Initialization readiness does not certify legacy legality: independent diagnostics remain visible and repairable.

## Expected Domain Scenarios

Use deterministic synthetic player metadata and independent hand-calculated expectations, not the same evaluator as the oracle. Unless a scenario specifies otherwise, select a legal 15-player multi-club squad and legal XI/bench/C/VC.

| Scenario | Expected evidence |
|----------|-------------------|
| Starting FT 0..5, default and GW1 | New post-GW1 plan defaults to 1 even when My Team differs. Zero means no transfers remain. GW1 is unlimited/N/A, no pre-used chips; GW2 has exactly 1. |
| First-GW ordinary transfer | Against independent boundary: one meaningful replacement with starting FT0 yields count1/hit4, then next FT1. WC/FH yields no hit; BB/TC do not waive the hit. |
| Ordinary chain | Start GW8 FT2; make 1,0,4 transfers in GWs8,9,10: available 2,2,3; GW10 hit4; GW11 FT1. Total hits are correct. |
| WC/FH rollover | Parameterize available N=0..5 and arbitrary transfer counts: next FT=`min(5,max(N-1,0)+1)`, no hit. WC/FH must never use old `N+1` rule. |
| BB/TC ordinary | N3 and moves0/1/4 -> next FT4/3/1, hits0/0/4. GW1 still feeds exactly FT1. No 2025/26 top-up. |
| Chip periods/declarations | Four chip types, once per period, one per GW. Used before and planned elsewhere have distinct reasons. Contradictions reject in both directions with conflicting GW. First-period unused chips lapse. |
| Boundary restrictions | WC/FH GW1 reject, BB/TC GW1 accept. FH19 plus FH20 rejects in either order; previous-GW19 declaration rejects FH20. Other same-type chips19/20 accept. GW20 has no used second-period declarations. |
| Sales | Purchase50 with market48/50/51/52/53/54 -> sale48/50/50/51/51/52. Check integer output and bank, not rounded float coincidence. |
| Save then refresh | Create decision, change stored latest market, GET/reload/lineup save: old assumptions/acquisition/sale/bank unchanged. Explicit edit captures latest only for that decision. |
| Provenance correction | Purchase50, saved market54, sale52; correct purchase48 while live market56 -> sale51. Incoming acquisition and saved market54 unchanged; bank decreases1. Confirmation-only changes no money and clears only relevant provisional dependency. |
| Accepted shortfall | Correct basis, preserve decisions/assumptions, derive earliest negative bank/amount/chain on replay and reopen. Later positive bank alone does not erase an earlier negative node. No persisted resolution markers. |
| Earliest failure moves | Before GW9=-1/GW10=-3; repair to GW9=0/GW10=-2. Accept because every shortfall improves; derive GW10 as earliest. Compare per-GW deficits, not issue IDs. Unrelated legal edits retain unchanged old deficits; new/worse shortfall rejects outside Q7. |
| Upstream acquisition edit | New acquisition basis changes dependent later sale using that sale's saved market, never its incoming price. If the explicit edit creates insolvency, reject atomically under Q2 rather than Q7. |
| WC permanence/FH reversion | Start/last FH; FH before/after WC; retained WC player keeps basis; acquired WC player gains permanent basis. FH restores permanent squad/bank/provenance, including corrected/assumed basis and genuine latest-market display. |
| FH deficit branch | Correction affects temporary FH sales and later permanent sales using each saved assumption. Temporary deficit stays a plan issue; it does not contaminate restored permanent bank. Permanent-origin issues remain dependent through FH. |
| Sell and buy back | Across different GWs: new acquisition basis/ownership identity and correct count. Same-GW round trips are not a transaction-history feature. |
| Explicit progression / Example A | GW8 ordinary A->B and no GW9 decision yields B in GW9. Enable FH8: restore A in GW9, zero GW9 transfers; no inferred A->B. Disable FH: B permanent again, quotes unchanged. Materialized old GW9 membership must not affect replay. |
| Missing outgoing / Example B | GW8 A->B, GW10 B->C. Propose A->D in GW8: GW10 reports `outgoing_not_owned`, never becomes D->C automatically. Q2 rejects this new blocked candidate alone. Explicit atomic batch removes or user-replaces GW10 decision; validate all and save once. Test removal/edit of earlier acquisition and outgoing ownership mismatch too. |
| Horizon changes | Start-later rebase carries permanent bank/ownership/FT and chip declarations, handles FH19->new start20. Extension after last FH uses permanent state. No unresolved prefix issue erased. Earlier start preserves retained decisions, validates new-period declarations and fabricates no historical data. |
| Rebased plan edits | After start-later rebase, change starting FT/chip declarations and correct a new starting player's basis, including a carried planned acquisition. Original captured source/value and boundary bank remain intact; dependent sales use saved market assumptions under Q7. Add/edit a retained-GW transfer using current prices under Q2; reopen with the new boundary and edits preserved, independent of My Team. |
| Completed GW edits | Apply lineup and transfer edits to a completed GW with the same legality/persistence rules. Only the explicitly edited transfer captures current prices; unaffected decisions stay frozen. No historical lock or reconstructed historical price is introduced. |
| Per-GW lineup isolation | XI/bench/C/VC edits stay local; propagated replacement inherits only outgoing slot/role. Same legal targets and captaincy outcome on My Team/Planner. GK never reorders into outfield bench priority. Direct invalid requests reject. |

## Persistence, Migration And Concurrency Proof

API service/router tests cover one typed mutation path, retired-writer responses and a single engine source for replay/accounting. Add real PostgreSQL tests for:

- Slot/decision/receipt uniqueness and plan ownership, exactly 15 boundary/lineup slots, and coherent revision/child reads. Inject failure during canonical input/selling-price/receipt writes and prove complete canonical rollback.
- One POST automatically evaluates and saves; no public prepare/commit routes. Fail before durable receipt: pending/unaccepted proposal. Fail after valid pending receipt: accepted-not-saved candidate/quotes survive. Retry same ID after live refresh resumes captured inputs; no extra committed revision.
- Commit succeeds before response/enrichment loss: same ID returns `already_committed`, not a repeat write. Simulate an uncertain database COMMIT outcome and require `outcome_unknown`/same-ID reconciliation, not an assumed rollback. Advance aggregate revision and retry again: return original committed revision plus current plan, not the old candidate.
- Pending receipt becomes stale after revision/rule-context change: `stale_reprepare_required`; no historical base/candidate reconstruction or silent re-quote. A new ID with an old expected revision returns `revision_conflict` without acceptance/capture/write. Same ID/different digest rejects. Exercise concurrent duplicate receipt creation, a duplicate reaching the final lock after the first request commits (returns `already_committed`), and 404 lookup while an original request is still running.
- Old PUT/PATCH return 410 and cannot change either canonical or quarantined data. Stale expected revision and competing mutations cannot overwrite newer state; no automatic cross-tab merge is claimed.
- Corrected inputs survive reopen and reproduce financial flags from replay alone; no resolution/cached-status rows. Reject a batch mixing Q7 corrections with unrelated planning mutations, so a new unaffordable transfer cannot borrow the correction exception. Confirm GET is read-only and market refresh leaves saved assumptions/bank unchanged.
- Legacy plan with ordinary first GW, leading FH, period crossing, incorrect old WC/FH cache, and an old illegal chip/squad. Preserve original rows/decisions and expose estimates/repair issues. No current-My-Team substitution or external FPL call.
- Once-only snapshot-to-decision conversion and rerun/refresh idempotence; missing prices leave original rows/pending status intact. Verify isolated upgrade/backfill/downgrade/re-upgrade preserves original rows/values without rollback copies, never deletes new plans, and refuses unsafe reversal after new-only edits.
- Clear a backfilled canonical `planned_chip` while the quarantined legacy `chip` remains populated: GET/reopen must retain the cleared choice, never consult/fall back to the legacy value. Compare quarantined membership/chip/accounting values before and after initialization.

Component tests use stateful realistic fixtures and deferred promises, not static save responses. Queue captain C then vice D before the first response: dispatch the vice-only envelope at the acknowledged new revision and retain C. Assert no complete lineup payload is queued; test a removed target requiring reselection. Cover navigation, rapid edits, late responses, unaccepted failure vs accepted-not-saved, identical retry after ambiguous success, explicit stale reconciliation, retained Q7 context, rejection preserving earlier unsaved work, departure protection and no Save Gameweek control.

## Browser Setup And Journeys

Follow `.github/skills/ui-browser-verification/SKILL.md`. Do not start servers or mutate development state merely to validate this planning document. For implementation browser verification, run existing services in separate terminals; choose unused ports and document any CORS/test-origin adjustment rather than replacing another process. API runs from `apps/api` so its relative environment file resolves correctly.

```sh
mise exec -- make db-up
mise exec -- make backend-dev
```

In another terminal:

```sh
mise exec -- make frontend-dev
```

Default URLs: frontend `http://localhost:3000`, API `http://127.0.0.1:8000`. Existing Playwright expects frontend `http://127.0.0.1:3000`; use its configured API origin. Do not use the normal development API for synthetic destructive setup. Durable Planner tests should use deterministic stateful intercepted API fixtures for error/timing/price edge cases, paired with actual API/PostgreSQL tests above for true persistence/atomicity proof. A mocked browser response alone does not prove backend saving.

Run the implemented first-increment journey file:

```sh
mise exec -- pnpm --filter web e2e tests/e2e/planner-foundations.spec.ts
```

Protect important journeys with durable Playwright tests:

1. Create a plan/start at GW12, set FT3 and used WC; confirm period-boundary chip reasons, lightweight nonblocking price estimates and first-GW transfer accounting. Reload after acknowledgement.
2. Change captain C, delay response, choose vice D and switch GW immediately. Verify requests contain field intents/rebased revisions, C is not reset, per-GW choices remain independent and reload retains final acknowledged state. No save action.
3. Inspect a saved transfer's basis/live/saved prices and the explicit saved-price policy, simulate refresh, verify bank stability; explicitly edit and observe a new quote. Correct provenance to expose a shortfall, verify earliest issue/amount/chain and saved status, reload, repair and verify cleared flags. Include a completed-GW edit to rule out an unintended historical lock or repricing policy.
4. Exercise leading/last FH/WC and Examples A/B. A chip toggle never turns inherited output into a new transfer; a missing outgoing decision names its intended player and is repaired only by explicit remove/replacement in an atomic batch.
5. Inject canonical-write failure after private receipt acceptance: accepted edit stays visible/not saved across GW selection, identical retry preserves quotes. Test lost successful response/current-revision lookup, stale pending conflict and domain rejection separately. Prior accepted edits/Q7 context survive; departure is guarded and no Save Gameweek control exists.
6. Use direct rearrangement from starter and bench, cancel/replace selection, reorder outfield priorities, reject GK/outfield reorder, inherit C/VC and verify My Team parity with the same squad.
7. Open a legacy assumed plan and start-later rebase; verify no fabricated history, dangling deleted acquisition source, old-period chip declaration or lost bank/provenance assumption. Edit the rebased starting FT/chips and purchase basis, then make a retained-GW transfer and reopen; the new boundary remains authoritative and the plan remains editable. Reopen the repaired `(-1,-3)->(0,-2)` case and verify derived GW10 earliest failure without persisted flags.

Inspect actual rendered desktop and narrow mobile viewports (e.g. 1440x900 and 390x844): starting panel, chip states, price inspection, saved/provisional/resolution separation, selection/target/confirmation, long player names, loading/empty/invalid/error/pending states. Capture screenshots; inspect no clipping/overlap, focus/keyboard/announcements and usable tap targets. Record browser/console failures and any local Playwright platform workaround without committing unrelated tracked configuration changes. No 3D/canvas assets are involved.

## Completion Gates

```sh
mise exec -- make lint
mise exec -- make typecheck
mise exec -- make test
mise exec -- pnpm --filter web build
```

Also run the guarded SQL/migration and Playwright checks above. Use `.github/skills/code-review/SKILL.md` for independent read-only implementation review, resolve relevant findings, and inspect the final full diff for unintended source/dependency/metadata changes. Report files changed, decisions/trade-offs, SC-001 to SC-009 evidence, actual checks/browser results and anything skipped/unverified. Do not treat an agent's statement, a component-only test, or this plan as runtime verification.

## Increment 1 Evidence (2026-10-14)

Scope: shared prerequisites and US1 only. No US2 task was started. The older
scenario/journey lists are acceptance references for the whole feature, not a
claim that later story UX is finished.

### Executed Checks

- `mise exec -- make lint`: passed, including Ruff and Next.js ESLint.
- `mise exec -- make typecheck`: passed (34 engine and 78 API source files,
	plus strict TypeScript). The final browser fixture also passed TypeScript.
- `mise exec -- make test`: passed; the full engine and ordinary API suites,
	and 105 web tests. Ordinary API DB cases explicitly skip without opt-in.
- `mise exec -- pnpm --filter web build`: passed, including static generation.
- Focused guarded SQL/API gate: 106 cases passed, including actual receipt
	races, rollback/uncertain-commit faults, retired-writer zero-write proof,
	initializer cases and four isolated migration round trips/refusals.
- Focused client gate: 22 board/coordinator/list cases passed.
- Safe initializer `--help`: passed; neither operator mode was run against
	development data.

The focused SQL command from the repository root was:

```sh
mise exec -- env RUN_DB_TESTS=1 \
	TEST_DATABASE_URL=postgresql+psycopg://fpl:fpl@localhost:5432/fpl_test \
	PYTHONPATH=packages/fpl_engine/src uv run --package api pytest -q \
	apps/api/tests/plans apps/api/tests/repositories/test_plan_repository.py \
	apps/api/tests/db/test_planner_foundations_migrations.py
```

The existing guard verified `fpl_test`; new Planner fixtures create/drop only
their UUID-named isolated schemas. No development schema, data, migration or
backfill was changed. Original Alembic head: `3e8b5d1a9c47`; additive revision:
`c6f91a2d83b0`. There are no dependency, lockfile or toolchain changes.

### Browser Evidence

The durable `planner-foundations.spec.ts` suite passed all eight cases against
both the development server and the production build at port 3100. It covers
journey 1 and the US1 portion of journey 7 at desktop 1440x900/mobile 390x844,
plus GW1/20/25, FT0, loading and read-only legacy readiness.

Observed: automatic FT/declaration/correction/confirmation persistence and
reload; 15 nonblocking estimates; used-before/planned-elsewhere/named conflict
reasons; period reset; FH19 restriction; rebased acquisition provenance and
frozen boundary bank; retained acquisition edited by decision ID, not a new
round trip; zero PUT/PATCH and no Save Gameweek control. Desktop/mobile
screenshots under ignored `apps/web/test-results/` were inspected; the tested
layouts have no document overflow. The primary navigation retains its existing
horizontal mobile scrolling. Production screenshots have no dev overlay.

Browser API responses are deterministic stateful fixtures, not proof of SQL
persistence or FPL arithmetic. The matching creation/rebase/reopen/quote and
transaction cases run through the actual application/repository on PostgreSQL.
The created-plan browser cases reported no uncaught page errors.

This host reports mac13, for which the installed Playwright version has no
headless-shell download. A command-local fallback worked; no tracked browser
configuration was changed:

```sh
mise exec -- env PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=mac14 \
	pnpm --filter web exec playwright install chromium --only-shell
mise exec -- env PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=mac14 \
	PLANNER_BASE_URL=http://127.0.0.1:3100 pnpm --filter web e2e \
	tests/e2e/planner-foundations.spec.ts --workers=1 --reporter=line
```

### Acceptance And Limits

- SC-001: domain boundary matrix, guarded independent creation/default FT1,
	component modes and browser creation/reload pass. Contradictory declarations
	name the planned GW and preserve the accepted decision.
- Relevant SC-005: integer sale steps and SQL P50/M54/live56/correct48 -> sale51
	pass, preserving saved market/incoming price, original capture and bank.
	Carried acquisition corrections remain N/A for historical confirmation.
- Relevant SC-006: delayed captain/vice navigation and latest-revision dispatch
	pass in component/coordinator tests. Basic same-ID retry, uncertainty and
	pause behavior have owning-layer tests. Comprehensive departure/failure UX
	and the later-story browser failure journeys are not certified here.
- SQL fault proofs are distributed across repository, service and router test
	modules at their owning boundaries rather than duplicated in one file.
- Final source/test/documentation diff reviewed for approved scope and
	architectural boundaries. Review found a SQL-null receipt-constraint gap;
	the regression failed before the explicit non-null revision fix, then the
	106-case SQL/API gate, lint and types passed again. Only T001-T037 are checked;
	all task wording and T038-T090 completion markers remain unchanged.
- Quarantined legacy accounting helpers remain for initializer/legacy tests;
	canonical GET/mutations use engine replay and old HTTP writers are 410.
- This is not approval to deploy a partial feature. Before persistent rollout,
	take a backup, apply the additive schema, explicitly check/apply initialization
	and coordinate the matching API/web writer release. No such rollout was run.
	After new-only writes, downgrade refuses; export/conversion or restore is
	required. Full story matrices, price-resolution UX and departure protection
	remain later approved increments.

## Independent Review Remediation (2026-10-14)

- Earlier horizon defaults clear chip history when crossing periods or moving
	to GW1/GW20, and clear an inapplicable FH19 declaration without inventing a
	planned chip. Same-period assumptions and explicit replacements remain
	supported. Seven new engine cases reproduced the defects and passed after
	repair.
- Downgrade also refuses unresolved `validated_pending` receipts before any
	schema drops. The regression commits the pending receipt on a revision-zero
	legacy-origin plan, then verifies refusal and retention of its retry payload.
	All five migration cases pass.
- Pending-plan GET reuses the initializer's read-only check and exposes its
	failure with repair/retry guidance through the existing initialization read
	model. No diagnostic column or GET initialization writes were added. Three
	real HTTP cases cover missing gameweeks, invalid prices/bank, data repair and
	explicit initialization/reopen.
- A guarded API test launches an ephemeral FastAPI server using the isolated
	test schema and runs the durable real-API Playwright case against the actual
	frontend. Desktop/mobile horizon edits send no replacement declarations;
	GW25 -> GW19 -> GW25 -> GW19 and reload preserve the correct cleared history.
	API responses are forwarded, not mocked. The mobile screenshot was inspected.

With a freshly built frontend running at port 3100, the complete guarded gate is:

```sh
mise exec -- env RUN_DB_TESTS=1 RUN_PLANNER_BROWSER_TESTS=1 \
	TEST_DATABASE_URL=postgresql+psycopg://fpl:fpl@localhost:5432/fpl_test \
	PYTHONPATH=packages/fpl_engine/src PLANNER_BASE_URL=http://127.0.0.1:3100 \
	PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=mac14 uv run --package api pytest -q \
	apps/api/tests/plans apps/api/tests/repositories/test_plan_repository.py \
	apps/api/tests/db/test_planner_foundations_migrations.py
```

Result: 111 passed, including the real browser/API journey. Without the browser
opt-in, that case explicitly skips; the standalone browser case also skips
without its guarded API URL/plan ID. `make lint`, `make typecheck`, `make test`
(including 105 web tests) and the production build passed. Uvicorn's existing
WebSocket imports emit two dependency deprecation warnings in the browser
harness. The stale preview was rebuilt before final browser verification.
Final source/test diff reviewed: no T038/US2, task/spec/plan, dependency or
toolchain changes. No persistent database migration/initialization was run.

## Increment 2: US2 Evidence (2026-10-14)

Scope: T038-T044 only. T045/US3 and all later tasks remain unchecked. Both
requirements-quality checklists passed before work (16/16 and 35/35).

### Acceptance Evidence

- SC-003: 28 new engine cases cover exactly WC/FH/BB/TC, once per period,
	first-period lapse/reset, used-before declarations, one chip per GW,
	occupied-target atomic move rejection, explicit remove/move, WC/FH GW1
	refusal and BB/TC acceptance, FH19/20 in both orders and both declaration
	directions. Other same-type chips can occupy both GW19 and GW20.
- SC-004: eight new component cases cover all five server-provided states,
	visible conflicting GW, acknowledged move/clear reason updates, period reset
	and no client-side BB/TC bank/allowance changes. Actual browser/API controls
	also verify used-before versus planned-elsewhere, planned-here, reset,
	rule-specific disabled choices and clear/move after acknowledgement.
- Chip-specific SC-009: 13 direct HTTP bypass cases reject with the engine's
	reason and leave all canonical, receipt and quarantined plan tables unchanged.
	A further HTTP clear/move/reopen case proves canonical null is authoritative
	even with a populated quarantined legacy chip, and saved decisions/quotes
	remain unchanged after the live incoming price changes from 5.0 to 9.0.
	This does not certify later-story lineup/squad/repair matrices.
- T043's actual PostgreSQL-backed browser journey runs at desktop 1440x900 and
	mobile 390x844 through the existing isolated-schema harness. It exercises
	GW17-22 with used FH/WC18, move/clear, both-period WC use, FH/WC toggles,
	both FH19/20 conflict directions, and GW1 WC/FH refusal plus BB/TC acceptance.
	FH activation restores the permanent squad downstream; clearing it restores
	the explicit replacement. Every chip toggle preserves the sole decision's
	ID and captured quotes despite the changed live price; no downstream transfer
	is fabricated. Reload and final SQL reopen retain cleared chips and that
	unchanged decision. API responses are forwarded, not mocked.

### Checks And Browser Observations

- Focused gates: 28 engine cases, 14 SQL-backed HTTP cases and eight component
	cases passed. The entire board suite passed all 23 cases.
- `mise exec -- make lint`, `mise exec -- make typecheck`,
	`mise exec -- make test` and `mise exec -- pnpm --filter web build`: passed.
	Full web regression total: 113 tests; ordinary API runs explicitly skip
	database/browser opt-ins.
- The complete guarded command in the preceding section passed 126 cases,
	including both actual API/browser journeys and isolated migration tests.
	Dedicated `fpl_test` and the existing `_test` safeguard were retained.
- The standalone durable browser command above passed eight fixture cases;
	its two real-API cases explicitly skip without the guarded API URL/plan ID.
	Both passed through the pytest harness, not through static save responses.
- Desktop/mobile chip screenshots were inspected: named reasons remain visible
	with no overlapping chip controls or document overflow in the tested states.
	No uncaught page errors occurred. Existing mobile navigation scrolling remains.
	The command-local mac14 Playwright workaround and two existing WebSocket
	deprecation warnings are unchanged.

### Decisions And Limits

The only production change prioritizes a newly changed chip's authoritative
diagnostic over the diagnostic on the previously accepted chip. Duplicate/FH
conflict messages now name the already accepted GW consistently with the
availability read model. No diagnostic is removed and no second rules path is
added. Existing chip handlers, API mapping and board controls passed the new
matrix unchanged; T041/T042 require fixes only for demonstrated defects.

Final source/test/documentation diff reviewed for scope: no US3 implementation,
new dependencies, migrations, infrastructure, xPts changes or frontend chip
authority. No persistent development-data initialization or rollout was run.
Only T038-T044 completion markers were added; task wording is unchanged.
No known US2 defect blocks US3. Later-story transfer accounting/repair UX,
price-resolution UX, comprehensive save-failure/departure UX and lineup parity
are not certified here.