# Phase 003 Current-State Assessment, Risks and Implementation Slices

Date: 2026-10-28, revised after the Phase 003 / Phase 004 split (Duplicate Plan findings removed; recoverable from Git history, commit `a3c5144`). Supports [spec.md](spec.md). This is source inspection only: no code, test, database or migration was run or changed while preparing it, so nothing here is runtime-verified. File references are repository-relative and were read on branch `feature/planner-transfer-workflow` (clean working tree, merged Phase 002 at `d2b9e17`).

## 1. Current-state assessment

### 1.1 How the My Team Transfer Explorer works today

| Concern | What the code does | Evidence |
|---|---|---|
| Squad source | Reads the singleton saved squad; no plan parameter exists anywhere in the Explorer API. | `GetTransferExplorerService.execute` in `apps/api/src/api/services/get_transfer_explorer.py` (`current_squad_repository.get_current()`); routes `/my-team/transfers/{id}`, `/preview`, `/apply` in `apps/api/src/api/routers/my_team.py` |
| Bank and money | `float` bank from the saved squad; every price is `current_price` on both sides; response carries `selling_price_is_approximate=True`. | same service; `OutgoingPlayerSummary.selling_price` |
| Candidate pool | `PlayerReadRepository.list_by_position`, then `incoming_pool_exclusion` (same position, not owned, `can_select`/`can_transact`; unknown selectability becomes a refresh-required failure). Playing status is advisory. | `apps/api/src/api/services/candidate_pool_failures.py`; `packages/fpl_engine/src/fpl_engine/transfers/candidate_pool.py` |
| Ranking | `rank_replacement_candidates`: per-gameweek `evaluate_single_transfer` (best-XI before and after), summed over horizons 1, 3, 5, sorted by primary-horizon gain then player id; illegal candidates are kept and flagged. | `packages/fpl_engine/src/fpl_engine/transfers/replacement_ranking.py`, `single_transfer.py` |
| Projection source | `component_v3`, latest run via `ProjectionRunRepository.get_latest` (ordered by `generated_at`, then id). The horizon starts at the first gameweek with projections in that run (`evaluated_gameweek_numbers`); preview and apply use `min(gameweek)` in the run. No selected-gameweek concept. | `get_transfer_explorer.py`, `get_transfer_preview.py`, `apply_transfer.py`, `projection_run_repository.py` |
| Preview | Read-only; compares best-XI before and after for the first projected gameweek; no free transfers, no hits. | `get_transfer_preview.py` |
| Apply | Re-validates, then rewrites the saved squad, replacing the outgoing player in the same slot; leaves `free_transfers` untouched. | `apply_transfer.py` |
| Frontend | `/transfers?out=<player>`; always fetches `primary_horizon=5` and re-sorts 1/3/5 client-side; no search, filter, fixtures or plan context; entry only from My Team and the recommended-squad view (`transferHref`). | `apps/web/src/components/transfers/transfer-explorer.tsx`, `replacement-table.tsx`, `apps/web/src/components/team/my-team-board.tsx` |

Note: the project memory records an approved "official run before the gameweek deadline" rule. The code does not implement it; it uses the latest run. The spec follows the code and says so (FR-024).

### 1.2 How the Planner represents its canonical boundary and evaluated state

- **Canonical model**: `fpl_engine.planning.models` holds typed immutable `Plan`, `Boundary` (15 `Ownership` entries with stable slot and ownership UUIDs, `PurchaseProvenance`, bank in integer tenths, starting free transfers, used chips, FH19 flag, origin, bank assumptions), per-gameweek `GameweekDecision` (slot-based lineup, planned chip, `TransferDecision` list with saved market assumption, incoming price, observation source and time).
- **Evaluation**: `fpl_engine.planning.evaluate.evaluate_plan` replays boundary plus decisions in order and returns per-gameweek squad, bank, free transfers (including Wildcard/Free Hit consumption and Free Hit reversion), transfers made, hit, sales (official selling price), provisional dependencies, shortfall chains and diagnostics. It is pure and needs only player position and team metadata.
- **Mutation**: `fpl_engine.planning.mutations.apply_intents` applies intents to a candidate plan and validates it (`validate_candidate`: no new diagnostics, no new or worsened per-gameweek shortfall, Q7 exception for purchase corrections). It is a pure function and a natural basis for a read-only "what if" check.
- **Persistence**: `apps/api/src/api/repositories/plan_repository.py` (`load_canonical`, `save_canonical`, receipts), tables `plans`, `plan_starting_players`, `plan_gameweeks` (slot lineup, `planned_chip`), `plan_transfer_decisions`, `plan_mutations` in `apps/api/src/api/models/entities.py`. Alembic head is `c6f91a2d83b0` (the Planner Foundations research notes an earlier head).
- **Single writer**: `POST /plans/{id}/mutations` with `mutation_id`, `expected_revision`, `intents`; `add_transfer` (gameweek, outgoing player and ownership, incoming player) and `edit_transfer` capture latest stored prices server-side (`PlanMutationService._capture` in `apps/api/src/api/services/plans.py`). `PATCH /plans/{id}` and `PUT /plans/{id}/gameweeks/{n}` return 410.
- **Read model**: `GetPlanViewService._canonical_view` evaluates the plan and returns per-gameweek players (with slot, ownership, source decision), decisions (with live-price display fields), accounting, chip availability, legal rearrangements, financial status, decision errors. Projected points come from `MyTeamProjectionRepository.list_latest_player_fixture_projections` (component_v3, latest `generated_at`). The response carries no model, run or generation-time field.

### 1.3 API contracts and reusable pieces

| Need | Reusable today | Gap |
|---|---|---|
| Candidate pool rules | `incoming_pool_exclusion`, `candidate_pool_exclusion` | None; call the same logic |
| Ranking | `rank_replacement_candidates` | Takes a flat squad, float prices, one `bank`; legality is My Team's single-transfer evaluator. Needs plan-aware legality and integer-tenths money, or a plan-aware wrapper that keeps ranking order and tie-break semantics |
| Plan-aware transfer legality and consequences | `evaluate_plan`, `apply_intents` | `apply_intents` raises on the first rejection; it does not return a per-candidate verdict with bank, transfers made, hit and downstream effects. A non-raising domain evaluation for a hypothetical transfer is missing |
| Persisting a planned transfer | `add_transfer` / `edit_transfer` in the mutation operation | None for writing. The inline picker already uses it, including edit-instead-of-add when the outgoing player was acquired in the same gameweek |
| Projections for a chosen gameweek | `list_player_fixture_projections_for_run(player_ids, run_id)` | Callers pass the whole run; the horizon must be sliced from the selected gameweek |
| Selectability on write | Enforced in My Team apply | Not checked in `add_transfer`; the inline picker filters playing status `a` only in the browser (see 3.2) |

### 1.4 Planner UI, navigation and autosave

- `PlanBoard` (`apps/web/src/components/plans/plan-board.tsx`) keeps the selected gameweek in local `useState`; reloading or returning always lands on the first gameweek. Nothing is in the URL.
- The inline transfer picker calls `fetchPlayers({position, status: "a", sort: "price_desc", page_size: 50})`: no search, projections, fixtures or selectability data, and a hard cap of 50 players per position. Playing status `a` conflicts with the My Team decision that status is advisory only.
- Autosave: `PlanSaveCoordinator` (`apps/web/src/lib/plan-save-coordinator.ts`) is plan-scoped and held in a module-level `Map` (`getPlanSaveCoordinator`), so it survives client-side navigation but not a reload or new tab. Statuses `saved`, `saving`, `not_saved`, `conflict`, `error`, `missing`; `hasUnsavedWork()`; `retry`, `reconcile`, `revalidate`.
- Departure protection (`beforeunload`, link-click confirm, `installHistoryDepartureGuard`) is installed only inside `PlanBoard`. The Explorer has none.
- No component displays the projection run for the Planner (`ProjectionRunBadge` is used only by the Explorer and My Team recommendation).

### 1.5 Plan loading and locking

- Load: `load_canonical` raises `PlanNotReadyError` for `foundation_state != "ready"`; the router maps it to 409 `plan_not_ready` on mutations; GET returns a read-only view with an initialisation reason. Initialisation is an explicit CLI (`apps/api/src/api/scripts/initialize_planner_foundations.py`), never done by a GET.
- Locking: `lock_plan` takes `SELECT ... FOR UPDATE` on the plan row; `get_for_view` takes a shared lock.

## 2. Already satisfied (Phase 003 must not rebuild)

- Authoritative financial and transfer accounting, chips, free transfers, Free Hit and Wildcard carry-forward, selling-price rules, provisional and shortfall status (`fpl_engine.planning`, `fpl_engine.rules`).
- Single guarded mutation operation, revisions, retry identity, receipts, conflict and reconciliation semantics, and the plan-scoped autosave coordinator with its failure states.
- The `add_transfer`/`edit_transfer` intents, including edit-in-place for same-gameweek acquisitions, and the explicit repair-batch flow for clashing later decisions (`TransferRepairPanel`).
- Replacement ranking, candidate pool and legality-reason rendering, the projection-run badge, My Team Explorer, preview and apply.
- Select-and-target lineup rearrangement, chip availability display, financial resolution panel, rename, horizon edit.
- Legacy-plan read-only handling and the "plan requires initialisation" state.

## 3. Functional gaps Phase 003 closes

1. No plan context anywhere in the Explorer API or UI (mode, plan, gameweek, plan squad, plan money).
2. Horizons anchored to "first projected gameweek", not a chosen gameweek.
3. No plan-aware, non-raising evaluation of a hypothetical transfer (legality, bank, transfers made, hit, Free Hit/Wildcard, downstream effects).
4. Money in the Explorer is float and approximated; the Planner is exact tenths with real selling prices.
5. Planner gameweek selection is not retained across navigation; no URL state; no highlighting or scrolling to a changed player.
6. No entry point from the Planner to the Explorer; no return path or confirmation.
7. Explorer has no departure guard or autosave awareness; a Planner-mode commit must use the plan's coordinator or an equivalent that preserves revision and retry rules.
8. Explorer has no search, filters, fixtures or alternative sorts; the Planner picker is capped at 50 players and ignores selectability.
9. The Planner does not show which model and run produced its xPts.
10. Explorer services read the My Team repository directly and mix context lookup with analysis; there is no seam between resolving a planning context and analysing it. Phase 004 (scenario tree) will change how contexts are resolved and where confirmations are written, so Phase 003 introduces a small separation (see plan.md).

## 4. Risks, conflicts and ambiguities

| # | Item | Why it matters | Handling in spec |
|---|---|---|---|
| R1 | **Gain basis differs between ranking and the Planner.** Ranking uses best-XI gain; a Planner transfer puts the incoming player in the outgoing player's slot (002 Q-3), so the plan's real xPts change can differ. | Two numbers for "the effect of this transfer" could confuse or mislead. | FR-023, FR-025; Q-1 and Q-6 resolved (two distinct measures; plan impact follows saved per-gameweek lineups, assumed continuation after plan end) |
| R2 | **Later planned decisions clash.** Editing an earlier transfer or adding one can orphan a later decision (002 Example B); the mutation layer rejects the candidate. | The Explorer could offer a candidate the Planner will refuse. | FR-016, Q-2 resolved (visible and previewable, commit disabled, no repair in the Explorer) |
| R3 | **Selectability is not enforced on the Planner write path.** Only the browser's `status: "a"` filter (playing status, not selectability) guards the inline picker. | Violates "authority in the domain"; Explorer and picker disagree. | FR-012, Q-3 resolved (enforce on new or edited transfers only) |
| R4 | **Planner and Explorer may use different runs.** Planner picks the newest `generated_at` among rows for the plan's players; the Explorer picks the newest run row. Normally the same; edge cases can differ. The Planner shows no run. | Explorer gain and Planner xPts could be from different runs without anyone knowing. | FR-024 pins and discloses the Explorer run; flagged for planning to verify, not asserted as a defect |
| R5 | **Coordinator lifetime.** The save coordinator is a module singleton; a hard reload inside the Explorer loses in-flight state. | Confirmation across a reload could look unsaved or be replayed incorrectly. | FR-032 to FR-035, FR-041; the same mutation ID and receipt lookup already cover reconciliation |
| R6 | **Horizon past the plan end and Free Hit.** A horizon beyond the plan's last gameweek, or a Free Hit gameweek, make "gain" ambiguous. | Overstated or understated gains. | FR-020, FR-025, FR-026 |
| R7 | **Completed gameweeks are editable but have no projections.** | Explorer cannot rank them. | Explicit unavailable state (US1-8); no fabrication |
| R8 | **Scope creep.** Search, filter and sort could grow into a redesign, or the Phase 004 scenario tree could leak into this phase. | Violates constitution VIII. | FR-046, Out of Scope |
| R9 | **Price drift between preview and confirm.** `add_transfer` captures the latest stored prices at commit, and the Planner contract forbids browser-authored quotes, so saved prices could differ from those previewed. | Surprising bank change versus what the user approved. | FR-033, Q-7 resolved (reject and re-preview; previewed prices are a guard only) |
| R10 | **Per-candidate plan evaluation cost.** Plan-aware legality, plan impact and clash detection for a pool of several hundred players each need a replay of the plan. | Slow candidate list. | SC-011, Q-8 resolved (3 s list, 2 s preview; measured, not a licence for premature optimisation). Plan impact needs the candidate plan replayed and scored per gameweek (today `score_gameweek` is applied in `GetPlanViewService`); how to do this per candidate is a planning concern |
| R11 | **Phase 004 rework.** The scenario tree changes how a planning context is resolved, addressed and written. If the Explorer reaches into plan storage and the writer, Phase 004 must untangle it. | Avoidable rework. | FR-047, FR-048, SC-013; three small seams in plan.md |
| R12 | **Over-engineering the seams.** Generic scenario or repository abstractions would guess at Phase 004's design. | Speculative complexity (constitution II, VIII). | Seams limited to one resolver function, one context dataclass, a read-only analysis service and a `commit` prop; no option or branch types |

## 5. Phase 004 compatibility (summary)

Phase 004 (Branching Scenario Planner, [vision](../004-branching-scenario-planner/vision.md)) replaces the linear plan with a scenario tree of options, immutable saved options and editable drafts. Phase 003 keeps the existing linear Planner and prepares only these seams: a context resolver separate from analysis, an analysis service with read-only dependencies, and a commit descriptor handed to the Planner's own writer. The engine already works on a linear `Plan` value, so a selected path can later be flattened into it. The table of components and contracts that Phase 004 will need to adapt is in [plan.md](plan.md).

## 6. Suggested implementation slices (high level, independently testable)

| Slice | Content | Owning layer and tests |
|---|---|---|
| S1 | Engine analysis: non-raising verdict extracted from `validate_candidate`, `hypothetical.py` (candidate assessment on in-memory plan copies, first downstream conflict), `impact.py` (plan impact, hit deltas, labelled continuation of the plan's final state), selectability rule extraction. | `fpl_engine`: domain tests including verdict-equals-`apply_intents`; ordinary, Wildcard, Free Hit, Bench Boost, Triple Captain, first gameweek, FT 0, estimated basis, shortfall, same-gameweek replacement, downstream clash |
| S2 | Mutation guard and selectability: optional compare-only price guard, `prices_changed`, `player_not_selectable` and `selectability_unknown` on new or edited transfers. | `apps/api` service and router tests; inline-picker regression |
| S3 | Context resolver, analysis service and API: `plan_context.py`, `plan_transfer_analysis.py`, router and schemas; run pinning, partial and unavailable coverage, selectability pool, tenths money, blocked-candidate truncation, `planning_context` ref; performance gate. | `apps/api`: no-database analysis tests, router tests, My Team regression; guarded no-write integration test |
| S4 | Explorer UI (Planner mode): URL context, banner, outgoing selection, preview, `commit` prop, coordinator `abandon()`, shared departure guard, Planner explore links, gameweek and highlight on arrival. | `apps/web`: component tests with deferred promises; Playwright journeys at 1440 and 390 |
| S5 | Search, filter, sort and fixtures for candidates (client re-presentation of server results). | `apps/web` component tests; Playwright smoke |
| S6 | Hardening: full quality gates, independent review per the code-review skill, browser verification, final diff review. | Cross-cutting |

Order: S1 precedes S3; S2 is independent of S1 and precedes S4's confirmation step; S3 precedes S4; S5 follows S4.

## 7. Evidence index

`apps/api/src/api/services/get_transfer_explorer.py`, `get_transfer_preview.py`, `apply_transfer.py`, `candidate_pool_failures.py`, `plans.py`, `get_plan_view.py`; `apps/api/src/api/routers/my_team.py`, `plans.py`; `apps/api/src/api/repositories/plan_repository.py`, `projection_run_repository.py`, `my_team_projection_repository.py`; `apps/api/src/api/models/entities.py`; `apps/api/src/api/schemas/plans.py`; `packages/fpl_engine/src/fpl_engine/planning/{models,evaluate,mutations}.py`, `transfers/{replacement_ranking,single_transfer,candidate_pool}.py`; `apps/web/src/components/plans/{plan-board,plans-list}.tsx`, `transfers/*`, `team/my-team-board.tsx`; `apps/web/src/lib/{plan-save-coordinator,api,history-departure-guard}.ts`; `apps/web/src/app/plans/[id]/page.tsx`, `transfers/page.tsx`; `specs/001-my-team-ux/spec.md`; `specs/002-planner-foundations/{spec,data-model,research}.md`, `contracts/planner-api.md`.
