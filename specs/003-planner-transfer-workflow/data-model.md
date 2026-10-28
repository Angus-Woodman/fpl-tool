# Phase 003 Data Model

Design only (revised after the Phase 003 / Phase 004 split; plan duplication structures were removed and survive only in Git history, commit `a3c5144`). **No persisted schema change**: no table, column, index, constraint or Alembic revision is added. Everything below is either an existing persisted structure, read unchanged, or an in-memory value that is computed per request and never stored.

## 1. Persisted structures used (unchanged)

| Structure | Used for | Notes |
|---|---|---|
| `plans` | `revision`, `foundation_state`, horizon, boundary fields | read by the context resolver; never written by the Explorer read paths |
| `plan_starting_players` | boundary squad (slot, ownership, player, purchase price, provenance) | read |
| `plan_gameweeks` | `planned_chip`, `slot_lineup` JSONB | read |
| `plan_transfer_decisions` | transfers with saved prices | read; written only by the existing mutation path when a transfer is confirmed |
| `plan_mutations` | receipts | written only by the existing mutation path |
| `players`, `teams`, `projection_runs`, `projections`, `fixtures` | pool, metadata, projections, fixtures | read only |

The Explorer read paths write nothing. Confirmation uses the existing mutation endpoint and tables exactly as the Planner's inline picker does today.

## 2. Engine values (new, in memory, frozen dataclasses)

### `ContextRef` and `PlanningContext`
`ContextRef`: `plan_id`, `gameweek`, `revision`. It is echoed in every Explorer response as `planning_context` and identifies what a preview was computed for.

`PlanningContext` (frozen, in memory, produced by `resolve_planning_context` and consumed by analysis): `ref` (`ContextRef`), `plan` (the engine's linear `Plan` for this context), `metadata` (player rule data for the plan's players), `baseline` (`PlanEvaluation`), and the selected gameweek's evaluated squad and accounting taken from the baseline. It holds no repository, session or connection. Phase 004 is expected to produce the same value by flattening a selected option path; no option, branch or scenario types exist in Phase 003.

### `PinnedSubmission` (client-side, held by the plan's save coordinator)
`submissionId`, `mutationId`, `expectedRevision` (the preview's revision), `status` (`sending` | `committed` | `rejected` | `conflict` | `unknown` | `pending_unsaved` | `plan_missing`), `committedRevision` (committed only), `diagnostics` (rejected only), `message`. `abandon()` returns `AbandonResult` (`abandoned` with `previous` and `serverReceiptRetained`, `nothing_to_abandon`, `refused`, `refresh_failed`); `serverReceiptRetained` is true only for `pending_unsaved`, whose durable server receipt is never cancelled, deleted or committed by the client. A `rejected` record keeps its message and diagnostics until `abandon()` acknowledges it. At most one exists per plan. It is not persisted and not part of any server contract; its mutation is an ordinary Planner mutation with `expected_revision` equal to `expectedRevision`.

### `CandidateQuote`
`player_id`, `outgoing_market_tenths`, `incoming_price_tenths`. Built from latest stored prices (`exact_tenths`), identical to what `PlanMutationService._capture` will capture at commit.

### `TransferOperation`
`kind` (`add_transfer` | `edit_transfer`), `gameweek`, `outgoing_player_id`, `outgoing_ownership_id`, `replaces_decision_id` (edit only).

Rule (single source, server side): locate the outgoing player's ownership in the baseline evaluation of the selected gameweek. If a transfer decision *in that gameweek* has `incoming_ownership_id` equal to it, the operation is `edit_transfer` of that decision (the outgoing side stays that decision's original outgoing player). Otherwise it is `add_transfer` selling that ownership. The same rule is what the Planner's inline picker applies in the browser today.

### `Conflict`
`kind` (`structural` | `financial`), `gameweek`, `code` (existing diagnostic codes such as `outgoing_not_owned`, `incoming_already_owned`, `dependency_blocked`, squad-rule codes, or `financial_shortfall`), `decision_id` (nullable), `message`, `shortfall_tenths` (financial only).

### `CandidateAssessment`
- `player_id`
- `state`: `available` | `unavailable` | `blocked_by_later_decision`
- `reasons`: tuple of codes when `unavailable` (squad rules, club limit, `financial_shortfall`, `sold_this_gameweek`, `player_not_selectable`)
- `conflict`: first conflict at a later gameweek, when `blocked_by_later_decision`
- `valid_through_gameweek`: last gameweek whose values may be displayed (see section 3)
- `selling_price_tenths` (add operations), `resulting_bank_tenths` (closing bank of the selected gameweek after the transfer), `points_hit_after`, `evaluation` (the candidate's `PlanEvaluation`, kept only for the response builder)

State precedence: a conflict at the selected gameweek yields `unavailable`; otherwise a conflict at a later gameweek yields `blocked_by_later_decision`; otherwise `available`. `confirmable` is true only for `available`.

### `GameweekImpact`
`gameweek`, `basis` (`saved_plan` | `assumed_continuation`), `available` (bool), `reason` (when unavailable: `no_projection`, `beyond_valid_range`, `continuation_lineup_illegal`), `points_before`, `points_after`, `delta` (all excluding hit), `hit_before`, `hit_after`.

### `PlanImpact`
`by_gameweek: tuple[GameweekImpact, ...]`; `totals[horizon]` for horizon 1, 3, 5 with `saved_plan`, `assumed_continuation` (each `None` when no available gameweek of that basis), `valid_through_gameweek`; `hit_change` and `net_saved_plan = saved_plan - hit_change` per horizon. Saved and assumed totals are never summed.

## 3. Validity truncation

Let *c* be the first conflict gameweek (selected gameweek included).

| Conflict kind | Replay effect | Values displayed |
|---|---|---|
| none | all gameweeks evaluated | every horizon gameweek with projections |
| structural at *c* | `players` is `None` from *c*; later gameweeks `dependency_blocked` | gameweeks `< c` |
| financial at *c* | squads exist; bank negative from *c*; dependent chain flagged | gameweeks `<= c`; nothing after |

`valid_through_gameweek` is computed once per candidate and applied to accounting, plan impact and consequences. Best-XI gain is a static-squad measure independent of later decisions and is always shown (FR-025, FR-016).

## 4. Client state (Planner-mode Explorer)

States: `loading plan` → `choose outgoing` (no `out`) or `loading candidates` → `ready` ⇄ `previewing (loading/ready/error/unavailable)` → `confirming` (coordinator saving) → `saved` (navigate) | `rejected` | `not saved` | `conflict`.

Transitions of note:
- `rejected` (including `prices_changed`) → the Explorer keeps the message and code from `abandon()`'s `previous` record, the record is cleared (no server contact), a fresh preview is loaded (`previewing`) with the message visible above it; never an automatic resubmit; Confirm needs a new explicit action and creates a new submission.
- `pending_unsaved` → retry, check status, or "Stop tracking this transfer" (with the warning shown first); after `abandon()` the Explorer shows the not-added notice, the plan reloads without the transfer, and a fresh preview is required.
- Confirm is only reachable when the coordinator holds no pinned submission, is idle, and the preview's revision equals the acknowledged revision; any acknowledged revision change while the Explorer is open marks the preview stale (Confirm disabled, "Plan changed, preview again").
- `confirming` is entered only through `submitPinned`; success is entered only when the coordinator's `pinned` record carries this submission's identity with status `committed`.
- `conflict` (known no-write outcome) → `abandon()` refreshes the plan, clears only the pinned submission, back to `ready` with a visible notice; user must preview again. `unknown` and `pending_unsaved` follow the abandon table in [contracts/pinned-submission.md](contracts/pinned-submission.md): unknown is reconciled or retried with the same identity before it can be abandoned.
- Any change of outgoing player or horizon cancels in-flight requests and ignores late responses.
- Leaving while `confirming` or `not saved` triggers the departure guard.

## 5. Validation rules carried from the spec

- Money is integer tenths end to end in Planner mode; the browser formats £m only.
- Horizon gameweeks are `N..N+h-1` limited to covered projections; never zero-filled for gameweeks the run does not cover.
- Missing data is decided from the fixture schedule: a player lacking a row for an unfinished scheduled fixture of their club, or whose club's schedule is unknown (gameweek without imported fixtures, or a postponed fixture without a gameweek), yields the `missing_projections` unavailable state when they are a squad player (selected squad, later planned acquisition, continuation squad); a pool candidate is withheld (`unprojected_candidate_ids`), never ranked on zeros. A confirmed blank (no unfinished fixture, known complete schedule) is the only case where absence means zero points.
- A financial-conflict gameweek keeps its negative-bank figures but is `valid: false` with `reason: financial_shortfall`.
- Guard fields are both-or-neither, positive tenths, and never persisted.
