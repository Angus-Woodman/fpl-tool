# Implementation Plan: Planner Foundations

**Branch**: `feature/planner-foundations` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)

**Input**: Approved product intent in `specs/002-planner-foundations/spec.md`; FR-001 to FR-049, SC-001 to SC-009, R-01 to R-12 and resolved Q-1 to Q-7. The spec's existing Draft label is unchanged. Spec Kit's feature selector is `002-planner-foundations`; it does not rename the actual Git branch.

**Planning status**: Phase 1 design revised after architecture review. No implementation or task breakdown is included. The product owner approved first-saved-GW legacy boundary initialization, permanent-state rebasing when moving start later, and this revision's explicit-decision progression/simplifications; see [research.md](research.md). The specification is unchanged. Newly blocked downstream decisions remain subject to Q2, not an invented invalid-edit exception.

## Summary

Make Planner state trustworthy before exploration, historical analysis or optimisation. A pure typed `fpl_engine.planning` evaluator consumes one independent starting boundary plus explicit per-GW net-transfer/chip decisions and local slot-based lineup choices. Its output is each full squad, ownership/bases/provenance, bank, FT/hits, chip reasons and validity. Saved membership snapshots never act as replay input or manufacture transfers after upstream edits. API services supply price captures and persistence; React submits domain/field intent.

Financial invalidity is derived, not persisted as permission markers. A Q7 purchase correction remains accepted even if deficits appear; replay saved market assumptions, preserve decisions and derive the earliest shortfall/chain. Ordinary repairs compare per-GW shortfalls rather than issue identity, allowing the earliest failure to move later. One public idempotent mutation call replaces prepare/commit and retires legacy PUT/PATCH writers. A plan-scoped field-intent queue prevents stale payload overwrite. A minimal private pending receipt preserves accepted quote inputs across canonical-write failure; no historical aggregate is retained.

## Technical Context

**Language/Version**: mise-pinned Python 3.12.15, Node 22.7.0, uv 0.5.24 and pnpm 9.9.0; strict Python typing and TypeScript strict mode.

**Primary Dependencies**: Existing FastAPI/Pydantic 2, SQLAlchemy 2/Alembic, Next.js 15.0.0/React 18.3.1, Tailwind, pytest, Vitest and Playwright. No new runtime library, service, event bus or background worker proposed.

**Storage**: Existing PostgreSQL; additive Alembic boundary/explicit-decision/slot-lineup/receipt storage and controlled once-only initialization. Integer-tenths money. No optional accounting/status caches, new membership materializations, validity-marker table or per-plan rollback payload. Local dependencies only.

**Testing**: Focused engine tests; API service/router tests; guarded PostgreSQL repository/transaction/migration tests; component race/error tests; durable Planner Playwright journeys and rendered desktop/mobile inspection. Independent review per repository skill before implementation completion.

**Target Platform**: Existing browser-based Planner, host-run Next.js/FastAPI, Docker Compose PostgreSQL only; CI's isolated PostgreSQL service remains supported. No containers for application development.

**Project Type**: Existing monorepo web application with reusable Python domain package. No new top-level application or package.

**Performance Goals**: Deterministic full replay over at most 38 GWs x 15 players, bounded database reads/writes and no external calls during replay. Avoid per-player/GW queries. Autosave queues must converge without stale overwrite. No new latency/throughput SLO is invented; inspect request counts/visible responsiveness during browser verification.

**Constraints**: No silent repricing or error swallowing; no blocking purchase-confirmation gate; no historical truth fabricated; single-plan mutation ordering; no automatic cross-tab merging; completed GWs stay editable. Dedicated test database and safeguards are mandatory. All substantial UI work requires browser verification.

**Scale/Scope**: Current single-manager planning workspace; maximum season 1..38, four chips per period, 15-player squads. Full transaction history, same-GW round trips, historical evaluation/versioning, xPts changes, predicted/speculative prices, Explorer navigation/ranking and broad redesign are excluded.

## Constitution Check

Pre-research gate: passed against `.specify/memory/constitution.md` and `AGENTS.md`. Post-design gate: passed as a design, with implementation proof still required below. No constitutional exception is requested.

| Principle | Before research | After design / required evidence |
|-----------|-----------------|----------------------------------|
| I. Domain authority/boundaries | Preserve engine/API/web separation. | One explicit-decision replay authority; API captures/persists/enriches; UI never authoritative. Alembic for schema. |
| II. Human ownership | Approved spec controls decisions. | Migration/horizon answers retained; requested review fixes recorded, including retiring redundant writers. No new product features. |
| III. Reviewable slices | Avoid monolithic page/service rewrite. | Coherent delivery boundaries below; each has a focused proof before integration. |
| IV. Owning-layer tests | Identify actual controlling paths first. | Authority/acceptance matrix and layered verification below. |
| V. Independent verification | Do not claim source inspection proves runtime. | Automated expected-value tests, real browser checks and code-review skill required during implementation. |
| VI. Browser checks | Substantial UI changes acknowledged. | Durable Planner journeys, desktop/mobile and failure/pending inspection per UI skill. |
| VII. Database safety | No planning-time DB mutation. | `TEST_DATABASE_URL`, `_test` and `ensure_test_database_url`; isolated upgrade/downgrade fixtures only. |
| VIII. Scope | Foundations only. | Explicit exclusions; no pricing/ranking redesign outside Planner. |
| IX. Acceptance before edits | FR/SC/R/Q registers identified. | This plan maps requirements and tests; no source implementation in this command. |
| X. Final gates/diff | Planning and implementation evidence distinct. | Implementation requires lint/type/tests/build, final diff review and limitations report; planning validates artifacts/scope only. |

## Project Structure

### Documentation

```text
specs/002-planner-foundations/
  spec.md                     approved intent, unchanged
  checklists/requirements.md  existing specification checklist
  plan.md                     architecture, acceptance and delivery boundaries
  research.md                 evidence, decisions and alternatives
  data-model.md               authoritative decisions, replay, invalidity and migration
  contracts/planner-api.md    read/mutation/error/client sequencing contracts
  quickstart.md               future validation commands and scenarios
```

`tasks.md` is intentionally not generated; task generation belongs to a later command.

### Source Ownership (Existing And Proposed)

```text
packages/fpl_engine/
  src/fpl_engine/rules/{chips,transfers,squad}.py  extend existing authority
  src/fpl_engine/planning/                       proposed aggregate/value/evaluation slice
  tests/test_rules.py                            extend existing reference cases
  tests/test_planning.py                         proposed focused replay/ownership cases
apps/api/
  src/api/models/entities.py                     boundary/decision/slot-lineup/receipt models
  src/api/repositories/plan_repository.py         aggregate load and atomic persistence
  src/api/services/{plans,plan_accounting,get_plan_view}.py
  src/api/schemas/plans.py                       input/output contracts
  src/api/routers/plans.py                       one mutation/result lookup; retire PUT/PATCH
  src/api/scripts/                              proposed once-only initialization/check entrypoint
  alembic/versions/                              additive revision(s), reversible fixtures
  tests/plans/                                  reuse current service/router/accounting tests
  tests/repositories/ and tests/db/              actual SQL/atomicity/migration coverage
apps/web/
  src/components/plans/plan-board.tsx            evaluated state + direct rearrangement UI
  src/components/team/my-team-board.tsx          extract narrow shared interaction pieces
  src/components/team/{squad-player-card,squad-pitch,bench}.tsx
  src/lib/api.ts                                strict contract/error mapping
  src/lib/                                      proposed plan-scoped save coordinator/shared helpers
  tests/plans/ and tests/team/                   stateful/deferred-promise component tests
  tests/e2e/planner-foundations.spec.ts           proposed durable important journeys
```

**Structure Decision**: Keep current modules and helpers where suitable. Add only the pure planning domain slice, required persistence inputs, a plan save coordinator and focused tests. Domain portions of `plan_accounting.py` become engine functions; do not leave competing arithmetic. Reuse existing component primitives and test builders. Exact filenames within the new domain slice can follow implementation size, without changing these ownership boundaries.

## Architecture And Authority

| Concern / acceptance | Authoritative layer | API/web responsibility and owning proof |
|----------------------|---------------------|----------------------------------------|
| Starting FT/chips/boundary; FR-001 to FR-008, SC-001 | Engine starting-state/declaration validation | API captures My Team once; boundary is independent. UI estimates; service/migration tests. |
| Chip periods/availability/reasons; FR-009 to FR-018, SC-003/004 | Extend `rules.chips`; engine evaluator combines pre-used and planned | No frontend-only chip validation. Router bypass and chip move/remove tests. |
| FT, unlimited, hits, first-GW diff; FR-019 to FR-025, SC-002 | Existing transfer primitives plus corrected WC/FH transition and boundary replay | Service passes inputs; client displays available/made/hit/next/bank/total hit. Hand-calculated engine tests. |
| Membership/ownership/propagation and FH/WC; FR-026/027, FR-033 | Replay explicit decisions over permanent/temporary branches | Persist user decisions, not membership output. Missing outgoing bindings block candidates; Examples A/B and atomic repair tests. |
| Selling prices/provenance/frozen inputs; FR-030 to FR-036, SC-005 | Pure integer sale calculation, ownership episodes and dependency replay | Infrastructure reads latest market only for explicit capture. UI distinguishes live/saved/basis/sale. API refresh/reopen tests. |
| Correction/repair exception; FR-048/049 and qualified FR-006/027/032/034/040 | Engine replayed shortfalls/dependencies and operation-specific comparison | Persist corrected inputs, derive negative bank/chain on read. Test moved-earliest failure and reopening without markers. |
| Squad, formation, bench, C/VC, legal targets; FR-028/029, FR-043 to FR-047, SC-008/009 | Existing squad rules plus shared pure rearrangement operation/target enumeration | Narrow shared UI interaction helper; server targets for both My Team/Planner; direct API rejection/parity tests. |
| Autosave/rejection/technical failures; FR-037 to FR-042, SC-006/007 | Engine validates; API owns canonical transaction/revision/receipt | One mutation request, field-intent queue, committed/stale result lookup and no unguarded writers. Component/SQL concurrency tests. |

Use immutable engine values and one deterministic replay contract: canonical aggregate + intent + necessary captured observations -> candidate/evaluation or structured violations. Reuse `RuleViolationError` and typed schema adapters; do not let engine import FastAPI, fetch FPL or open a database. Domain replay is independent of projections, current time and market refresh once inputs are captured.

### Core State Changes

Persist the boundary (15 stable slots/occupants, ownership/bases/provenance, bank/FT/chip declarations), explicit net transfers with frozen quotes, per-GW chip/slot-lineup decisions, horizon/name and revision. User-authored decisions are the replay input. Full membership, later ownership and financial state are output, not another writable representation. Existing whole-squad screens remain; no real transfer ledger or same-GW sequence is added.

Each acquisition has an ownership identity. Each outgoing decision names its intended player/episode, not an arbitrary current slot occupant. Apply the complete GW net set to entering ownership, then that GW's independent slot roles. No decisions means no transfers, including after a changed upstream state. First-GW changes compare against the independent boundary and count/hit normally; GW1 remains unlimited. Stable slots preserve each GW's XI/bench/C/VC when occupants change, without propagating lineup edits.

Ordinary/WC acquisitions are permanent; retained WC players keep basis. FH evaluates a temporary branch then restores permanent squad/bank/ownership. Toggling WC/FH preserves saved transfer decisions/quotes but changes allowance/permanence and triggers full replay. **Example A:** GW8 ordinary A -> B, GW9 no transfer; enable FH8 and GW9 restores A, with no inferred A -> B. **Example B:** later GW10 B -> C becomes `outgoing_not_owned` if GW8 changes to A -> D. Do not invent D -> C. Q2 rejects that upstream candidate alone; an explicit atomic repair batch may remove the GW10 decision or replace it with the user's chosen owned outgoing player. Details and all transition cases are in [data-model.md](data-model.md).

Changing/removing transfers, editing an outgoing binding and moving horizons use this same replay, never snapshot-diff reconciliation. Unchanged records keep price assumptions. Explicitly changed records capture latest known market prices; dependent same-player sales use their own saved assumptions and replayed basis. Legacy migration alone converts old snapshots once into explicit assumed decisions.

Money uses integer tenths. With purchase `P` and saved market `M`, sale is `M` if `M <= P`, else `P + floor((M - P) / 2)`. Keep latest live `M` separate from saved `M`. Correcting estimated purchase 50 to 48 with saved market 54 recalculates sale 52 to 51 even if live market is now 56; incoming prices remain fixed.

Provisional assumptions, replay-derived financial resolution and persistence are independent. Q7 persists corrected provenance/decisions, not invalidity markers. Derive every negative bank node and its reachable financial descendants on each replay; a positive descendant cannot erase an earlier negative node. FH temporary bank has no edge into restoration. Compare ordinary candidates by `S_candidate(g) <= S_previous(g)` for every retained GW, where S is shortfall and new GWs have baseline zero. Thus GW9/GW10 banks `(-1,-3)` becoming `(0,-2)` are accepted; earliest failure relocates to GW10. Unchanged deficits permit unrelated legal edits. Q7 alone bypasses financial non-worsening, not structural legality. No stored issue identity or warning metadata grants validity.

### Data And Migration

See [data-model.md](data-model.md) for constraints. Save canonical input changes, required selling-price materializations, revision and committed receipt atomically. Derive all other accounting/status. GET uses one coherent canonical revision and never writes/reprices; `get_plan_view.py` consumes replay, not an independent adjacent-squad diff. Old snapshot/float-accounting data is quarantined, never authority after initialization.

Use additive migrations and a controlled once-only application backfill before switching editing on. Keep original legacy rows unchanged; no per-plan rollback copy. Use owner-approved first saved membership/old bank/FT, no pre-used chips, assumed missing purchase/quote information and deterministic conversion of later net snapshot differences against inferred permanent state. Preserve saved lineups/chips and diagnose illegal inputs, rather than fabricating history or clearing decisions. Missing-price failure is explicit/atomic; reruns skip initialized plans. A leading FH boundary remains explicitly inferred. Initialization/readiness commands and test/operator separation are in [quickstart.md](quickstart.md).

Isolated upgrade/backfill/downgrade/re-upgrade must prove unchanged original legacy rows. After new-only edits/plans, require ordinary database backup/export plus explicit conversion/restore; refuse a falsely lossless in-place downgrade. Never restore old snapshots over new decisions or delete new plans. No development-data downgrade tests.

Start-later rebase captures a valid permanent prefix exit, preserving slots/ownership/price sources/FT/bank assumptions and only chip declarations applicable to the new period, plus FH19 at new GW20. Inline provenance must survive deletion of prefix acquisition records. Reject blocked/unresolved prefixes. Earlier starts add empty decisions against a hypothetical existing boundary; extensions use permanent restoration after a final FH. Retained decisions/quotes/lineups remain untouched. Completed GWs stay editable under latest-price explicit edits, not historical reconstruction.

### Autosave And UI Integration

See [contracts/planner-api.md](contracts/planner-api.md). One POST takes mutation ID, expected revision and field/domain intents. No public prepare/commit endpoints. Retire old full-GW PUT and plan PATCH with 410; rename/horizon edits use the same guarded mutation path. No writable compatibility bypass is retained.

The server evaluates/captures inputs and durably stores a minimal valid pending receipt, then automatically attempts the atomic canonical write and committed receipt/revision. These are two private bounded transactions, not one atomic transaction spanning both stages. Retain this small receipt solely so an accepted candidate/quote survives later write failure; before receipt durability, the proposal is unaccepted/pending. Compatible pending retries use the same quotes. Stale pending receipts return `stale_reprepare_required`, not a reconstructed old candidate. Committed IDs return `already_committed` plus original committed revision/current plan even after later revisions. No historical bases or complete candidate snapshots are kept.

Queue captain/vice/swap/chip/transfer/correction intents, not captured complete lineups. Construct each immutable envelope only after the prior outcome settles, against latest acknowledged revision; captain C followed by vice D must preserve C. Pause dependent writes on unknown outcome/accepted technical failure, reconcile the same ID, and guard late responses by sequence/generation/revision. A 404 receipt lookup is not proof an in-flight original stopped. Explicitly resolve stale intent/quote conflicts with a new ID, never silently overwrite or reprice. Preserve accepted-unsaved context across GW navigation and warn before losing it on departure; no async unload guarantee or cross-tab automatic merging.

Extract only useful My Team selection/cancel/target/announcement behaviour and presentation primitives. Remove Planner's separate dropdown/formation logic. Have both surfaces consume legal target pairs from the shared engine rearrangement helper (an additive My Team response field may be needed); preserve My Team's current save behaviour and captaincy inheritance. Do not share page state or introduce a general state-management framework. Verify bench visual order actually matches substitute priority, including GK exclusion. Preserve the established visual language; no broad redesign.

## Delivery Boundaries

These are reviewable architectural slices, not generated tasks. Each implementation slice must gain its owning tests and focused validation before the next integration boundary.

1. Extend existing pure chip/FT/sale/rearrangement rules; add explicit-decision replay/slot/ownership tests, Examples A/B and per-GW financial comparison. No second snapshot-based rule path.
2. Add minimal canonical schema and isolated legacy round-trip fixtures; initialize boundaries/decisions/quotes without modifying original rows. Keep readiness and writer switch explicit.
3. Move service accounting/propagation/read derivation to engine replay; cover horizon/correction and atomic repair batches, with actual repository transaction/coherent-read proof.
4. Add one mutation/result lookup, private receipt durability, expected-revision/idempotency/error contracts; retire old PUT/PATCH and verify they cannot write.
5. Integrate plan-scoped field-intent autosave and starting/financial status UI; share direct rearrangement presentation with My Team and cover delayed captain/vice sequencing without redesign.
6. Complete durable browser journeys, desktop/mobile inspection, broader gates and independent review. Feature readiness is determined by acceptance/evidence, not completion of a slice label.

## Verification And Risks

[quickstart.md](quickstart.md) supplies runnable future checks, expected numerical cases, isolated DB prerequisites and browser workflows. Reuse current test modules/builders; add focused planning/SQL/Playwright files only where no suitable home exists. Existing fake-router and static UI fixtures are not proof of persisted calculations. Use realistic multi-club squads, stateful fake persistence and independent expected values.

Required implementation gates: focused engine/API/web checks while iterating; guarded SQL/migration tests on `_test`; root lint/typecheck/test; production web build; durable Playwright journeys; final real-browser desktop/mobile/error-state verification; read-only independent review following `.github/skills/code-review`; final diff review and report against SC-001 to SC-009 with limitations. No gate is considered executed by this plan.

Unusually risky/expensive surfaces:

- Legacy original membership/prices are irrecoverable; assumed initialization preserves usability, not historical fidelity. Leading FH and missing market data require honest diagnostics.
- Legacy snapshots mix decisions and propagation. Conversion is once-only; new replay uses explicit bindings, never a generic downstream diff. Missing-ownership repair and chip toggles need explicit expected-state tests.
- Existing API uses floats and reprices from live player rows, while read transfer labels use a different baseline. Both paths must switch together.
- Accepted-unsaved UX plus post-commit response failures need durable identity. The remaining private pending receipt is bounded transport state, not a public two-phase workflow or historical candidate store.
- Legacy invalid chips/squads and later changing player metadata can expose old illegality. Preserve/report input and allow explicit repair; do not silently legalize or let read enrichment crash the plan.
- Rollback after new-only edits cannot be lossless in the old schema without export; schema reversibility must not be misreported as universal product-data reversibility.
- Shared rule correction/My Team helper extraction can regress other callers. Reuse targeted existing tests and avoid changing Explorer price/ranking or xPts logic.

## Complexity Tracking

No constitution violations. Retain the pure evaluator, independent boundary, explicit net decisions/slot-lineup inputs, required transaction-price materialization and minimal mutation receipt. Remove public prepare/commit, writable compatibility adapters, full-lineup browser commands, optional accounting/status/membership caches, validity markers and per-plan rollback copies. The receipt's private pending state is justified by accepted quote durability; canonical writes remain atomic. No event ledger, historical versions, new services, general workflow framework or speculative pricing. See [research.md](research.md) for alternatives/evidence.
