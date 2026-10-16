# Planner Foundations Validation Guide

This guide retains the full feature's validation scenarios below. T001-T037 (shared foundations and US1 Starting State), T038-T044 (US2 Plan Chips Across Both Periods) and T045-T053 (US3 Transfers, Hits And Squad Flow) and T054-T065 (US4 Official Selling Prices And Financial Resolution) and T066-T075 (US5 Persistence And Navigation Safety) and T076-T083 (US6 Rearrange XI And Bench Like My Team) and T084-T090 (Phase 9 polish and cross-cutting verification) are implemented and verified as recorded here. See [plan.md](plan.md), [data-model.md](data-model.md) and [contracts/planner-api.md](contracts/planner-api.md); [spec.md](spec.md) remains the acceptance authority.

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

Follow `.github/skills/ui-browser-verification/SKILL.md`. Do not start servers or mutate development state merely to validate this planning document. Existing frontend port 3000 (`.next`) and backend port 8000 processes are user-owned: never kill, restart or replace them for verification. Normal `make frontend-dev` remains unchanged. Production verification must use the isolated targets below, never an unqualified production build against `.next`. Do not change CORS policy; reuse the existing test-origin handling and guarded API harness.

```sh
mise exec -- make frontend-verify-build
```

Start a tracked temporary preview in a separate owned terminal, only on an
unused port (3100 below; choose another if occupied):

```sh
mise exec -- make frontend-verify-preview FRONTEND_VERIFY_PORT=3100
```

Both targets use `.next-copilot`, not normal dev output. Register `try/finally`
or equivalent cleanup before building. On success, failure or interruption,
stop and await only the exact owned preview/process group (never a broad
port-based kill), then run `mise exec -- make frontend-verify-clean`. Confirm
the preview port is released and `.next-copilot` is absent before finishing.
This also applies to build-only gates. Keep the alternate generated-types
include in `apps/web/tsconfig.json` so builds do not rewrite that file; remove
the generated directory, not the include. Never clean normal `.next` output.

Default user URLs: frontend `http://localhost:3000`, API `http://127.0.0.1:8000`. Point Playwright at the temporary preview using `PLANNER_BASE_URL`. Do not use the normal development API for synthetic destructive setup. Durable Planner tests should use deterministic stateful intercepted API fixtures for error/timing/price edge cases, paired with actual API/PostgreSQL tests above for true persistence/atomicity proof. A mocked browser response alone does not prove backend saving.

Run the implemented first-increment journey file:

```sh
mise exec -- env PLANNER_BASE_URL=http://127.0.0.1:3100 pnpm --filter web e2e tests/e2e/planner-foundations.spec.ts
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
mise exec -- make frontend-verify-build
```

Run these gates inside the cleanup-managed scope above; after any preview has
exited, always run `mise exec -- make frontend-verify-clean`, including when
a gate fails. Do not leave isolated generated types behind.

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
- Production build: passed, including static generation (historical evidence;
	future runs use `mise exec -- make frontend-verify-build` and final cleanup).
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
	`mise exec -- make test` and the production build: passed (historical evidence;
  future builds use `mise exec -- make frontend-verify-build` and final cleanup).
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

## Increment 3: US3 Evidence (2026-10-15)

Scope: T045-T053 only. T054/US4 and later tasks remain unchecked. The
requirements-quality checklists passed before implementation (16/16 and 35/35)
and were not edited.

### Acceptance Evidence

- SC-002: 35 new engine cases cover the independently counted GW8-12 chain,
	FT0-5, the cap, ordinary/WC/FH/BB/TC accounting at move counts 0/1/4,
	first/last and adjacent FH/WC, permanent buy-back ownership episodes,
	same-GW round-trip rejection, unordered net sets and local lineup roles.
	Starting FT2 with moves 1/0/4/0/0 produces available FT2/2/3/1/2,
	next FT2/3/1/2/3, hits 0/0/4/0/0 and closing banks 12/12/20/20/20 tenths.
	Existing GW1/GW2 and first-GW FT0 cases passed in the complete replay slice.
- No competing accounting: ten canonical API read cases compare all seven
	accounting fields directly with the single engine replay, despite stale
	legacy starting finances and different live prices. Two additional view
	cases independently assert FT0 first-week labels/count/hit/bank and FH
	restoration without inferred downstream moves. No engine/API production
	arithmetic or ownership implementation was added.
- FR-008/027/040 repair subset: guarded SQL starts with two saved legacy
	ownership errors, removes one atomically, reloads the accepted inputs and
	retains the other diagnostic. Dependent bank/shortfall/hit remain unavailable.
	An unverified downstream transfer and an unrelated new invalid captain reject
	without changing those accepted inputs; removing the second error restores
	evaluable accounting. Existing independent lineup and financial-repair
	regression cases also passed. This is not certification of US4 price UX.
- Transfer-related SC-009: direct guarded service calls reject illegal formation,
	club, squad and unowned-captain states after propagated ownership changes.
	Wrong ownership episodes reject; completed-GW explicit edits capture current
	prices for edited records while a third unedited record remains identical
	despite its changed live price. Canonical reload verifies accepted decisions.
- Example A: actual API/browser FH/WC activation and removal on first/last
	weeks preserve every explicit decision and captured quote. FH restores the
	independent permanent squad; clearing it restores the planned acquisition.
	The following empty week still has zero decisions/transfers, never a phantom
	transfer inferred from displayed membership.
- Example B: actual API/browser changes an earlier acquisition with a later
	sale bound to its episode. The upstream-only proposal returns 422 with the
	intended outgoing player/GW and leaves GET exactly equal to the accepted
	plan. User-selected removal or explicit outgoing replacement is submitted
	with that original proposal in one two-intent batch at the accepted revision.
	The source acquisition decision ID is reused, not a same-GW round trip.
	A GW11 captain choice remains local while earlier/later slots inherit only
	their own replacement roles; reload and SQL reopen retain the final inputs.

### Executed Checks

- Complete planner engine slice: 93 passed, including 35 new US3 cases.
- Complete guarded Planner service/view/router/repository/migration gate:
	145 passed, including all three actual PostgreSQL/API browser journeys.
	Only the dedicated `fpl_test` URL and UUID-isolated guarded schemas were used.
- Final full web suite: 119 passed, including 36 Planner component/coordinator/
	list cases. Rejected proposals preserve the accepted display; diagnostics
	expose explicit remove/replace choices and blocked totals say Unavailable.
	Rejected impact context expires on a newer accepted server revision.
- `mise exec -- make lint`, `mise exec -- make typecheck` and
	`mise exec -- make test`: passed. Final frontend lint/typecheck/full tests
	were rerun after the coordinator review fix. Ordinary API runs intentionally
	skip DB/browser opt-ins; the guarded gate above supplies actual SQL proof.
- `mise exec -- make frontend-verify-build`: passed on the final bundle.
	All eight fixture browser journeys passed separately. Their starting-FT
	response fixture was corrected to update replay accounting as well as its
	legacy display field; no production fallback arithmetic was introduced.

The guarded command from the preceding increments was run with
`PLANNER_BASE_URL=http://127.0.0.1:3101`; ports 3000/8000 and an existing 3100
listener were left untouched. The owned preview used `.next-copilot` and was
stopped and awaited in `finally` before `frontend-verify-clean`, including after
an initial fixture-test failure. Port 3101 was confirmed released and isolated
output/generated types absent. No persistent migration or initialization ran.

Actual API/browser screenshots were inspected at 1440x900 and 390x844.
Removal repair was exercised on desktop and replacement repair on mobile;
diagnostics, controls and accounting wrap without content overlap, and reload
has no document-width overflow. No uncaught page errors occurred. Existing
mobile navigation scrolling, the command-local mac14 Playwright workaround,
Vite CJS warning and two WebSocket dependency deprecation warnings remain.

### Decisions And Limits

Production changes are confined to board presentation and rejected-impact
context in its existing plan-scoped coordinator. Replacement choices carry
saved ownership IDs from the accepted read/boundary; legality stays on the
server. No candidate ownership, bank or FT is synthesized in React. Existing
engine/API handlers passed the new adversarial cases unchanged, so T048/T049
required coverage rather than speculative implementation changes.

Final diff reviewed against the accepted US3 scope: only the board/coordinator,
their focused tests, the existing guarded browser harness and these task/evidence
records changed. No dependencies, migrations, infrastructure, xPts model,
contract, specification or plan changes. Only T045-T053 markers were added,
with task wording unchanged; no extension hooks were registered.

No known US3 defect blocks US4. Selling-price inspection, provenance/shortfall
resolution UX, comprehensive failure/departure handling and My Team/Planner
lineup parity remain future-story work, not certification from this increment.

## US3 Review Remediation (2026-10-15)

Both independent US3 findings are remediated without starting T054/US4 or
changing task markers. This evidence supersedes the earlier Example B browser
replacement case, which selected an already-known ownership rather than the
newly proposed acquisition.

- Canonical Example B now submits the upstream acquisition edit followed by a
	downstream edit with `outgoing_player_id` and `outgoing_source_decision_id`,
	not a guessed/generated browser ownership ID. Capture resolves that earlier
	same-batch source to its actual new incoming ownership. Both decision IDs
	and the unchanged downstream incoming ownership remain stable. The normal
	engine remains authoritative for final ownership and legality.
- Guarded regressions reject unknown, forward, mismatched-player, conflicting
	ownership/source and same-GW references without changing canonical inputs.
	Explicit edits capture latest prices; an unedited third decision remains
	identical despite a changed live price. Upstream-only rejection leaves the
	accepted plan unchanged, and repaired inputs survive canonical reload.
- The real frontend/API/PostgreSQL journey now chooses the proposed D
	acquisition on mobile, sends its source decision ID without an ownership ID,
	and verifies the newly generated episode is used for D-to-C. Decision IDs,
	the C acquisition identity, unchanged quotes and empty downstream decisions
	are checked through API read, browser reload and SQL reopen. A live price of
	8.0 does not change the untouched 5.0 acquisition; edited D records capture
	5.2. No phantom transfer is introduced.
- Accepted-plan diagnostics are merged/deduplicated for display with rejected
	proposal diagnostics, labelled Saved plan versus Rejected edit. Missing
	rejection diagnostics never hide accepted issues. The coordinator's raw
	rejection context and acknowledged canonical plan remain separate and
	unchanged; a later accepted revision clears rejection-only context as before.
	Component cases cover missing, identical and additional rejection diagnostics,
	the rejection message and subsequent acceptance. A diagnostic-less rejection
	is not silently resubmitted with an accepted-plan repair.

Verification passed: all 93 planner replay cases; six focused guarded source
reference cases; all 150 guarded Planner API/repository/migration cases,
including three actual API browser journeys; all 123 web tests (40 Planner);
all eight fixture browser journeys; root `make lint`, `make typecheck`,
`make test`; and the isolated production build. Ordinary API test skips are
not SQL evidence; the guarded run uses only `fpl_test` and existing safeguards.

Desktop/mobile screenshots were inspected; no new overlap or page errors were
observed. The owned preview on port 3101 and `.next-copilot` were cleaned after
both an initial test-fixture setup failure and the successful rerun. Existing
ports 3000/8000/3100 were untouched. The fixture failure was fixed by refreshing
live prices after both seed mutations, preserving the original saved quotes.
Existing dependency deprecation warnings and mobile navigation scrolling remain.

Final diff reviewed for US3-only scope: request schema, capture resolution,
TypeScript request type, board repair/diagnostic presentation, their focused
tests and existing browser harness, plus request-contract/evidence docs. No
domain arithmetic, coordinator, dependency, migration, task wording/markers or
US4 price-resolution UX changes. No known remaining issue from either finding.

## Increment 4: US4 Evidence (2026-10-15)

Scope: T054-T065 only. T066/US5 and later tasks remain unchecked. Both
requirements-quality checklists passed before work (16/16 and 35/35) and were
not edited. No extension hooks are registered.

### Acceptance Evidence (hand-calculated, tenths)

- SC-005 sale steps: purchase 50 with saved market 40/48/50/51/52/53/54 sells
  40/48/50/50/51/51/52, and each bank equals `10 + sale - 50` through full
  replay, not only the pure function. A Wildcard acquisition at 52 becomes the
  permanent basis: later sale at 56 gives 54; a buy-back at 53 gives 51 with a
  new ownership identity and basis 50 (banks 10/14/15, no hits).
- Free Hit: a temporary sale (saved 52 over basis 50) pays 51 and closes at 8;
  the following week restores bank 10 and a new sale at 54 pays 52 (bank 12).
  The saved Free Hit decision is unchanged.
- Upstream acquisition edit: raising a first acquisition from 50 to 54 moves
  the dependent later sale from 53 to 55 using that sale's own saved market 56
  and leaves its incoming price unchanged; the earlier bank falls from 10 to 8
  and a 63 incoming price is rejected at GW8 as a new shortfall (Q2).
- Q7 correction, P50/M54/live56 to 48: sale 52 becomes 51, the incoming 62 and
  quote 54 are unchanged, and bank moves 0 to -1 (shortfall 1 at GW8). With a
  Free Hit GW8 the deficit stays temporary (restored bank 10, empty chain); with
  a plain GW8 plus a later GW9 sale the negative node is not erased by a later
  positive bank (-1, 1, 1; chain {8}). Repair by editing the incoming price to 61
  clears every flag. Moving the earliest failure later (-1,-3 to 0,-2) remains
  accepted from existing coverage.
- Confirmation changes no money: sale and bank are identical, only that
  ownership leaves the provisional set. Mixed correction/planning batches reject.
- Explicit edit versus refresh: saved M54/P50 with live later 56/58/59; after
  correction to 48 the explicit edit to another incoming player recaptures only
  that decision (outgoing market 56, incoming 50, sale 52, bank 12) while a
  second unedited decision keeps market 50/incoming 50/sale 50. A completed
  gameweek edit is not historically locked.

### Production Changes And Defects Found

Existing engine arithmetic already satisfied every case above, so T057/T058
needed only additive read data: each engine sale now records the basis amount,
kind and confirmation that produced it, and the read model exposes per-decision
basis, saved quotes, sale, latest live prices, the earliest shortfall amount and
reason, and a per-gameweek provisional flag, all from the single replay. The
response schema carries the new fields. No pricing arithmetic changed.

Review found and fixed one defect in this increment's own display helper: a
stored live price of 0, a negative, a non-tenth, NaN or infinity either crashed
or produced a schema-invalid read. It now reuses the strict `checked_tenths`
and omits an unusable live value (five regression cases). A completed-run
failure also showed two US2 assertions compared whole decisions across a live
price change; they now compare saved fields strictly and exclude only the two
explicitly live fields. A blanket formatter run touched an unrelated migration
and that file was reverted; no migration, dependency or toolchain change exists.

### UI And Browser Evidence

The board states the price policy, separates basis/saved market/selling/
acquisition prices from "Latest market (not used)", shows estimates as a
lightweight label, keeps saved/provisional/requires-resolution distinct, lists
the earliest shortfall amount, reason, full dependent chain and a navigation
button, shows a negative bank as a shortfall, and presents a planned
acquisition's source readably instead of a raw decision identifier. All figures
are server-provided tenths; React performs no financial arithmetic.

The real frontend/API/PostgreSQL journey (desktop 1440x900 and mobile 390x844)
checked saved quotes against moved live prices, correction to a 0.1 shortfall in
GW8 with chain GW8-GW11, reload and earliest-GW navigation, an explicit edit of
that completed-gameweek transfer clearing the flag (bank 12, sale 52, edited
quote 56/50), a rebase to GW9 carrying the planned acquisition at 50 with bank
12, correction to 48, and a retained transfer (sale 49, buy 60, bank 1), then
reload and SQL reopen. Screenshots were inspected: no overlap or document
overflow and no page errors. API responses were forwarded, not mocked.

### Checks Run

- Engine: 329 tests pass (16 new US4 cases); mutation checks with a deliberately
  rounded sale step and a removed response field both failed the new cases.
- Guarded Planner API/SQL/migration suite: 173 pass against `fpl_test`,
  including four actual browser journeys; ordinary API runs skip DB/browser cases.
- Web: 131 tests pass (48 Planner), eight fixture browser journeys pass.
- `make lint`, `make typecheck` and `make test` pass; ruff reports two import/
  line-length findings only in `apps/api/alembic`, identical on a clean stash and
  outside the repository lint scope.
- The isolated build ran on owned preview port 3101 (3100 was already in use);
  the preview was stopped and awaited, port 3101 released and `.next-copilot`
  removed, including after an earlier failing run. Ports 3000/8000/3100 untouched.

### Limits

Comprehensive save-failure/departure UX (US5), lineup-rearrangement parity (US6)
and completion tasks are not certified. The edit-then-refresh display shows the
latest price only as information; no speculative future price is accepted.

## Increment 5: US5 Evidence (2026-10-15)

Scope: T066-T075 only. T076/US6 and later tasks remain unchecked. Both
requirements-quality checklists passed before work (35/35 and 16/16) and were
not edited. No extension hooks are registered. Server and engine source were
not changed: the receipt/idempotency contract already satisfied US5, so T068
and T072 pin existing behaviour.

### Behaviour Evidence (SC-006 / SC-007)

- Single writer path: a static guard fails if any Planner component or client
  helper writes outside the coordinator; plan-list rename issues zero
  PATCH/PUT and a vanished plan shows a missing-plan state. Legacy PUT/PATCH
  remain 410 and there is no Save Gameweek control.
- Receipt lookup 404 `mutation_not_found` is inconclusive: the same mutation
  ID is retried or reconciled ("Retry Same Edit" / "Check Save Status"). Only
  409/410 conflicts use a new ID after explicit revalidation. 404
  `plan_not_found` stops writes ("Plan missing").
- A queued intent whose target vanished is recorded as skipped and later
  intents still drain (no stranded queue); a rejected (422) edit keeps its
  message and shows saved state, not "Not saved".
- Departure guard: `beforeunload` plus in-app http(s) link confirmation while
  work is unsaved; `mailto:`, new-tab, modifier-click, download and same-URL
  links are not intercepted.
- Real frontend to API to PostgreSQL journey: injected 503 then reload shows
  the last committed state, the retried same-ID edit commits once, and SQL
  reopen asserts exactly one committed revision.

### Verification Run

- Root `make lint typecheck test`: ruff clean, ESLint clean, mypy 34 and 78
  source files clean, web 158 tests in 12 files passed.
- Planner client suites: 75 passed (coordinator 16, board 36, list 4, static
  guard 3, plus pre-existing cases in those files).
- Guarded (isolated `fpl_test` schemas, owned preview on 3101): 187 passed
  across plans services/router/accounting, plan repository (24) and
  migrations (5); fixture browser journeys 8 passed; the real-API persistence
  journey passed. Cleanup confirmed: preview exited, port 3101 free,
  `.next-copilot` absent.
- Defects found by failing tests first and fixed: receipt-404 treated as a
  conflict; missing plan not distinct; vanished target stranded the queue;
  rejection message wiped on next dispatch; rejected edit shown as "Not
  saved"; no reconcile control or departure guard; `mailto:` wrongly prompted.

### Known Limits

- The guard covers `beforeunload` and link clicks, not programmatic
  navigation. (Browser Back/Forward was added later by the FR-038 remediation
  in "T089 FR-038 History Navigation Remediation" below.)
- No cross-tab merge; no unload-time persistence is promised.

## Increment 6: US6 Evidence (2026-10-15)

Scope: T076-T083 only. T084 and later tasks remain unchecked. Both
requirements-quality checklists passed before work (35/35 and 16/16) and were
not edited. No extension hooks are registered.

### Behaviour Evidence (SC-008 / SC-009)

- One rule authority: `fpl_engine.rules.squad` now owns `rearrange_lineup` and
  `legal_rearrangements`. The Planner's swap intent and its `legal_rearrangements`
  field delegate to them (the former duplicate in `planning/mutations.py` is
  gone), and My Team's GET and PUT responses carry the same targets through
  the additive `legal_rearrangements` field. Tightening the shared
  `STARTING_POSITION_LIMITS` changes the targets on both screens.
- Same squad, same targets, same result: with the squad of the guarded plan
  (4-4-2, captain P2, vice P3, bench GK/DEF/MID/FWD) the real browser offered
  identical targets for all 15 players on My Team and on Planner GW9
  (`planned == mine`). The bench goalkeeper's only target was the starting
  keeper and vice versa; no starter was ever offered against another starter.
- Swaps: P2 (captain) with P14 gave P14 the armband and P2 bench order 3 on
  both screens; P13 with P15 swapped only bench order. Both screens announced
  "Swapped P2 with P14." and "Swapped bench order of P13 and P15." and the
  resulting lineups were identical through each API (`My Team == Planner GW9`).
- Per-gameweek isolation: after the Planner swaps in GW9, GW8 and GW10 lineups
  were unchanged through the API and SQL (canonical revision 2); the Planner
  edits also did not alter the saved My Team squad until My Team made its own
  identical swaps. Pages keep independent state.
- Autosave: the Planner issues one `swap_lineup_players` intent for the shown
  gameweek on the second selection, never a lineup snapshot, and shows
  "Saved" without any other action. My Team keeps its whole-lineup PUT with
  the saved bank and free transfers unchanged.
- Direct requests (SC-009): through HTTP, an illegal formation swap (5 with the
  bench goalkeeper), goalkeeper-against-outfield reorders, starter-with-starter,
  the same player twice and an unknown player all return 422 with the engine's
  code and message and write no SQL rows; the formation message equals the one
  My Team's save rejects the same lineup with.
- Bench order defect found and fixed: My Team's `Bench` grouped substitutes by
  position, so the visual order did not match substitute priority. Both screens
  now render the bench strictly in priority order (tests and browser).
- Stale selection defect found by review and fixed (test first): a Planner
  selection whose player left the gameweek dimmed every card with no Clear
  control; the selection is now derived from the players actually shown.
- Presentation: shared `SquadPitch`/`Bench`/`SquadPlayerCard` plus
  `lib/squad-rearrangement.ts` and `rearrangement-controls.tsx`; the Planner's
  dropdown swap and My Team's client-side formation/target rules were
  removed. My Team still owns the optimiser's own formation table (a
  hypothetical-lineup display, not a legality rule).

### Verification Run

- Root `make lint typecheck test`: ruff and ESLint clean, mypy 34 and 80 source
  files clean, engine 412 passed, API 308 passed and 167 skipped without the
  guarded database, web 181 passed in 13 files.
- New/changed automated cases: engine 26 (15 shared rules, 11 Planner), API 5
  My Team service/router plus 7 guarded HTTP, web 7 helper + 14 Planner
  rearrangement + 4 My Team cases (and updated existing My Team fixtures).
- Guarded (isolated `fpl_test`, owned preview on 3101): the entire API suite,
  475 collected, passed including six real frontend to API to PostgreSQL
  journeys (horizon, chips, transfers, pricing, persistence, rearrangement);
  8 fixture Planner journeys passed; 7 My Team stub and smoke specs passed.
  Cleanup confirmed: preview exited, port 3101 free, `.next-copilot` absent.
  User-owned listeners on 3000, 3100 and 8000 were not used.
- Mutation checks (each failed the suite, files restored): no keeper
  exclusion, no captaincy inheritance, no legality validation (engine); every
  player a target, reversed swap order, unsorted bench, announcement despite
  rejection, selection allowed while saving (web); every player a target also
  failed the real browser journey.
- Rendered desktop (1440) and mobile (390) screenshots of both screens showed
  selected (green) and valid-target (blue) states, dimmed non-targets, the bench
  in priority order and no horizontal overflow (asserted in the journey).

### Known Limits And Unverified

- `validate_squad` was deliberately not changed, so a full-lineup PUT or a
  persisted lineup can still hold the bench goalkeeper outside bench slot 1;
  only the rearrangement operation refuses to move it against outfield
  substitutes. Tightening that would affect persisted data and was not in scope.
- My Team still persists the lineup composed in the browser (inherited
  captaincy included) validated by the engine, so result parity there is shown
  by tests and the browser journey rather than by a server-computed swap.
- The Planner shows the swapped lineup after the server acknowledges it (no
  optimistic lineup), and the "Swapped ..." announcement is withheld whenever
  the save status is unsaved, conflicting, missing or rejected.
- Keyboard-only traversal and screen-reader output were reviewed by markup
  (buttons with `aria-pressed`, a polite live region) but not with a screen
  reader.

## Phase 9: Cross-Cutting Verification Evidence (2026-10-16)

Scope: T084-T090 only. Both requirements-quality checklists passed before work (35/35 and 16/16)
and were not edited. No extension hooks are registered. Nothing was committed by the agent.

### T084 Acceptance Evidence Map (FR-001-FR-049, SC-001-SC-009)

Built by reading the tests (not by trusting earlier narratives); `ENG` = `packages/fpl_engine/tests`,
`API` = `apps/api/tests`, `PB` = `apps/web/tests/plans/plan-board.test.tsx`, `E2E` =
`apps/web/tests/e2e/planner-foundations.spec.ts`. J1-J7 are the quickstart journeys above.

| Requirements | Owning-layer evidence | Browser |
|---|---|---|
| FR-001-FR-008 starting state | ENG `test_starting_state_*`, `test_period_boundary_*`, `test_contradictory_starting_chip_*`; API `test_new_plan_captures_an_independent_ready_boundary_*`, `test_legacy_initialization_is_once_only_*`, migration round-trip; PB starting-state, FT0 and basis-correction cases | J1 (stub), J7 |
| FR-009-FR-018, SC-003/004 chips | ENG `TestPlannerChipPeriods::*`, `test_chip_reasons_*`; API `test_chip_http_bypass_*` (15 HTTP zero-write cases incl. FR-007 declarations), `test_chip_http_clear_move_*`; PB chip-state cases incl. all four chips together | J4 (real API) |
| FR-019-FR-025, SC-002 allowance/hits | ENG `test_us3_allowance_hits_and_cap_matrix`, `test_us3_hand_calculated_chain_*`, plus new FR-021/022/023 cases | J4 |
| FR-026-FR-029 flow-forward/legality | ENG `test_wildcard_*`, `test_example_a_*`, `test_example_b_*`; API `test_us3_direct_api_rejects_illegal_state_after_propagation`, new SC-009 HTTP zero-write cases | J4, J6 |
| FR-030-FR-036, FR-048/049, SC-005 prices/resolution | ENG `test_official_sale_steps`, `test_us4_*`; API `test_us4_*` (view, SQL freeze, reopen) | J3 |
| FR-037-FR-042, SC-006/007 persistence | coordinator and PB cases, API/SQL fault-boundary cases | J2, J5 |
| FR-043-FR-047, SC-008/009 rearrangement | ENG `TestRearrangement`, `test_us6_*`; API `test_us6_http_*`; PB direct-rearrangement | J6 (real API) |

Acceptance cases added in this phase after the audit found them weak or missing:

- FR-021: following gameweek after Wildcard/Free Hit across banked 0-5 and 0/3 moves (32 engine cases).
- FR-022/FR-023: Bench Boost/Triple Captain in GW1 stay hit-free with GW2 exactly 1; only WC/FH/GW1 are unlimited.
- FR-049 relocation: the (-1,-3) to (0,-2) case asserted before and after in the engine and again after a
  guarded SQL reopen (earliest failure GW9 then GW10, derived from replay only).
- FR-007 and SC-009 over HTTP: used-chip declaration contradicting a planned chip, and illegal formation,
  club-limit, squad-shape and unknown-captain requests all reject 422 with zero SQL writes.
- FR-016/SC-004: all four chips with different states and reasons in one gameweek.
- FR-041/FR-038: an accepted provenance correction stays visible, "Not saved", guarded on departure and
  retries with the same mutation ID (component level).

Mutation checks: FR-021 (removing the banked-transfer rule failed 16 cases) and FR-022 (changing the GW1
carry value failed 2 cases).

Still Partial after the audit (limits, not hidden): J1 first-gameweek transfer accounting and the FT3 plan
run only against a stub in the browser (accounting itself is asserted in the engine and over HTTP/SQL); J5
real-browser coverage uses captain edits, not transfer quote retention (covered at API/SQL and, for a
provenance correction, component level); J7 legacy start-later rebase has stub browser coverage plus
API/service tests but no real-API browser journey; FR-008 legacy plans after `--apply` have no browser
journey; FR-036 inspection is tested per transfer, not for every shown bank figure.

### T085 Guarded Database Suite

`mise exec -- make test-integration` (applies Alembic head `c6f91a2d83b0` to `fpl_test`, then the
whole API suite with `RUN_DB_TESTS=1` and only `TEST_DATABASE_URL`): 488 tests, 6 skipped (the real
browser journeys, which need `RUN_PLANNER_BROWSER_TESTS=1`), no failures; includes the isolated
upgrade/backfill/downgrade/re-upgrade and downgrade-refusal-after-new-writes cases. The
development database was not touched and the `_test` safeguard was not bypassed. After the review
remediations the whole suite was rerun with browser tests enabled: 489 passed, 0 skipped.

### T086 Gates And Browser Suite

- Root `make lint typecheck test` after final changes: ruff and ESLint clean; mypy clean on 34 and 80
  files; engine 445 passed; API 314 passed and 175 skipped without the guarded DB; web 193 passed
  in 13 files.
- Guarded API suite with real frontend to API to PostgreSQL journeys (horizon, chips, transfers,
  pricing, persistence, rearrangement): 489 passed. Fixture Planner journeys plus the Phase 9 rendered
  states spec: 9 passed. My Team stub and smoke specs: 7 passed.
- Production build ran through `make frontend-verify-build` on an owned preview at 127.0.0.1:3101 (3100
  was held by an old user-owned listener and left alone; 3000 and 8000 were never used). Cleanup was
  registered before building; after every run the owned preview had exited, port 3101 was free and
  `.next-copilot` was absent.

### T087 Rendered UI (desktop 1440x900, mobile 390x844)

The durable Phase 9 spec drives a stateful stubbed API (never development data) and records
screenshots per state at both viewports. Observed and asserted:

- Loading, plan with a long plan name and 44-character player names, chip states (planned here,
  planned elsewhere, used before), selected card, accepted-but-not-saved with Retry Same Edit, API
  error and missing plan: no horizontal overflow, long names wrap, nothing overlaps.
- Keyboard: Select receives focus, Enter selects and deselects (`aria-pressed`), Clear selection appears.
- Tap targets: every enabled control is at least 24x24 CSS px (WCAG 2.2 minimum); the standalone "Back
  to plans" link was 20px high and was padded. The compact buttons do not reach the 44px
  recommendation.
- Console and network: no page errors or unexpected console errors; at most two `GET /plans/{id}`
  per load.
- Previously captured desktop/mobile evidence for the starting panel, price inspection and financial
  resolution states (increments 1-4) was not re-screenshotted in this phase.
- Observed, not changed: the global app navigation is clipped at 390px (last items cut off). It is
  pre-existing shell code outside this feature.
- Not verified: screen-reader output, Safari/Firefox (Chromium only).

### T088 Operator Documentation

`README.md` now has a "Planner foundations rollout" section: backup, additive migration, coordinated
web/API writer switch (old PUT/PATCH return 410), read-only `--check`, explicit-approval `--apply`,
pending-plan diagnostics and rollback limits (no lossless downgrade after new-only writes). The
`--check` command was run against the isolated `_test` database only (returned `[]`, exit 0); `--apply`
was never run on persistent data.

### T089 Independent Review And Remediation

A read-only review (code-review skill, separate agents for engine/API and web, then a second review of
the remediation diff) found no High defect in replay, accounting or idempotency. Defects fixed, each
with a failing test first:

- Rename editor closed the moment it opened (High): now closes only when its own submitted name is
  acknowledged.
- Horizon From/To inputs saved on every keystroke, so typing a two-digit gameweek could trim and drop
  plan content: now commit on blur/Enter with 1-38 validation, and reset after a server rejection.
- `revalidate()` replayed already-resolved absolute values over a concurrent writer's change: it now
  re-resolves the original edit against the fresh plan.
- A transfer plus a horizon trim in one batch crashed with `StopIteration` (500): now a 422 rule
  violation.
- Unbounded request integers could be accepted, then fail forever as retryable: ids are bounded to
  int4, prices to 1000.0m, batches to 100 intents.
- A database outage during the post-failure lookup surfaced as a bare 500: now `outcome_unknown` 503;
  the response-building catch-all is logged.
- Swap controls: `aria-disabled` instead of `disabled` while saving (focus is kept), described valid
  targets, a live no-target notice, `aria-expanded` on Transfer toggles.
- README order, backup directory, rehearsal URL and `mise exec` prefixes corrected.

Findings reviewed and deliberately not changed (open limits): legacy writers/services and unused engine
helpers remain behind the 410 routes (removal is a separate cleanup); `provisional_dependencies` marks a
plan provisional whenever any held player has an assumed price (needs a product decision against
FR-032/FR-036); `set_starting_chips` defaults `free_hit_gameweek_19` to false when omitted; GET and
receipt lookup take shared row locks; repeated full replays per GET; initialization turns any
`ValueError` into `legacy_pending`; the departure guard does not cover an uncommitted typed field
(Back/Forward was closed by the FR-038 remediation below), and `PlansList` rename has no guard; `PlansList` rename completion matches any
newer revision; uncontrolled starting-state fields keep a rejected value on screen; the transfer picker
can show a stale pool after a late response; `reconcile()` is not guarded against a concurrent retry;
non-JSON 5xx responses lose their status in the mutation reader; some accessible names use raw player
IDs and several controls are 24-28px.

### T089 FR-038 History Navigation Remediation

Closed the final merge-readiness finding: the departure guard covered
`beforeunload` and http(s) link clicks but not browser Back/Forward.

Approach (`apps/web/src/lib/history-departure-guard.ts`, installed from the
existing guard effect in `plan-board.tsx`; no coordinator change, no global
state, no new dependency):

- Back/Forward cannot be cancelled, so while `PlanSaveCoordinator.hasUnsavedWork()`
  is true one same-URL history entry carrying a sentinel state is pushed above
  the Planner entry (armed via the coordinator's `subscribe`). Nothing is
  pushed, and no prompt is shown, while nothing is unsaved.
- Back lands on the entry underneath: `popstate` asks the same `window.confirm`
  warning. Stay restores the guard entry with `history.go(1)` (URL, React state
  and the coordinator are untouched); leave continues with one `history.back()`.
  A one-second leaving flag stops a repeat prompt and makes `beforeunload` skip
  during the confirmed departure, then re-arms if the page is still mounted with
  unsaved work. If work was saved in the meantime the guard entry is simply
  stepped over without prompting.
- A stale sentinel left by a reload is replaced on install. Link-click and
  `beforeunload` guards are unchanged apart from the `leaving` skip.

Evidence (failing tests first):

- Component: six cases in `plan-board.test.tsx` ("browser history departure
  guard (FR-038)"): history untouched and no prompt while nothing is unsaved,
  exactly one guard entry however many edits follow, Back prompts and cancel
  restores the entry and keeps the unsaved work, confirm leaves without a
  second prompt, no prompt once durably saved (Back passes through), and
  `beforeunload` still guarded. Baseline against the unguarded code: 4 failed,
  2 passed; now all pass. The
  Planner client suites pass 106 tests, and the whole web suite 199 in 13 files.
- Real browser (Chromium, owned preview on 3101, stubbed API,
  `FR-038 browser Back and Forward never silently leave unsaved Planner work`):
  Back/Forward with nothing unsaved go to /plans and back with no dialog and
  unchanged `history.length`; with a failed save, Back twice shows the warning
  twice, stays on the Planner with "Not saved" and Retry Same Edit visible and
  `history.length` unchanged, and no second write is sent; accepting leaves
  to /plans exactly once (no loop or extra dialog after 500ms); Forward returns
  to the Planner with the unsaved edit retained and still guarded (Back prompts
  again and cancel keeps it); the in-app "Back to plans" link still prompts and
  cancel stays; after Retry Same Edit saves the same mutation ID, Back leaves
  with no prompt. Baseline against the unguarded code failed at the guard-entry
  assertion; now 1 passed.
- Regression: the whole fixture Planner spec (excluding real-API cases) 10
  passed; the guarded real frontend to API to PostgreSQL browser journeys
  (isolated `fpl_test`) 6 passed; every run ended with the owned preview exited,
  port 3101 free and `.next-copilot` absent. `pnpm --filter web lint` and
  `typecheck` were clean; the 3000, 3100 and 8000 listeners were not touched.

New or still-open limits (not silently removed):

- Arming truncates forward history above the Planner entry, and the same-URL
  guard entry stays in the stack if the user saves and stays (Back still needs
  one press: the guard steps over it without a prompt, but the extra entry is
  visible in the history list).
- Multi-step `history.go(-n)` or long-press history jumps are not guarded as a
  unit; only the single-step entry below the Planner is. Programmatic
  navigation remains unguarded.
- Verified in Chromium only; Safari/Firefox history semantics were not run. The
  after-saved-Back screenshot was not inspected.
- Every other limit listed above (uncommitted typed field, `PlansList` rename,
  and the rest) is unchanged.

### T090 Final Diff

Inspected `git diff` (19 working-tree files, no dependency, lockfile, toolchain, migration or CI changes)
and the whole feature diff against the base: the only metadata files touched by the feature are the
isolated-preview Makefile targets, the `.next-copilot` tsconfig include and the browser-verification
skill, all intended. `git diff --check` is clean. Material decisions: engine is the single rule
authority; saved prices are never repriced by refresh; no lossless downgrade is offered.
