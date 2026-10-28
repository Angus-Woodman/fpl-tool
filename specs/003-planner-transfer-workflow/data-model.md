# Phase 003 Data Model

Design only. **No persisted schema change**: no table, column, index, constraint or Alembic revision is added. Everything below is either an existing persisted structure, read unchanged, or an in-memory value that is computed per request and never stored.

## 1. Persisted structures used (unchanged)

| Structure | Used for | Notes |
|---|---|---|
| `plans` | source and new plan rows | `revision`, `foundation_state`, `name` (100 chars, not unique), legacy float `initial_bank` and `initial_free_transfers` (non-null) |
| `plan_starting_players` | boundary squad, per-plan unique `slot_id`, `ownership_id`, `player_id` | copied with remapped identifiers |
| `plan_gameweeks` | `planned_chip`, `slot_lineup` JSONB | copied; lineups reference slot identifiers |
| `plan_transfer_decisions` | transfers with saved prices | unique per gameweek on `decision_id`, outgoing and incoming player, incoming ownership; `selling_price_tenths` materialisation copied verbatim |
| `plan_mutations` | receipts | read only for the pending-edit check; never copied |
| `players`, `teams`, `projection_runs`, `projections`, `fixtures` | pool, metadata, projections, fixtures | read only |

Plan-local identifier uniqueness is enforced by constraints and assumed by `Plan.__post_init__`; identifiers are not constrained across plans, which is why a copy could technically reuse them but must not (see section 4).

## 2. Engine values (new, in memory, frozen dataclasses)

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

### `ClonedPlan`
`plan` (new `Plan`, revision 0), `id_map` (old UUID to new UUID, test-visible), `sales` (new decision id to saved selling price tenths).

## 3. Validity truncation

Let *c* be the first conflict gameweek (selected gameweek included).

| Conflict kind | Replay effect | Values displayed |
|---|---|---|
| none | all gameweeks evaluated | every horizon gameweek with projections |
| structural at *c* | `players` is `None` from *c*; later gameweeks `dependency_blocked` | gameweeks `< c` |
| financial at *c* | squads exist; bank negative from *c*; dependent chain flagged | gameweeks `<= c`; nothing after |

`valid_through_gameweek` is computed once per candidate and applied to accounting, plan impact and consequences. Best-XI gain is a static-squad measure independent of later decisions and is always shown (FR-025, FR-016).

## 4. Identity remapping (`clone_plan`)

| Identifier | Where it appears | Treatment |
|---|---|---|
| `slot_id` | `Boundary.players[*]`, `Boundary.lineup[*]`, every `GameweekDecision.lineup[*]` | one new UUID per boundary slot, applied to all |
| `ownership_id` | `Boundary.players[*]`, `TransferDecision.outgoing_ownership_id`, `TransferDecision.incoming_ownership_id`, `Boundary.bank_assumptions` | one new UUID per distinct old value; values without a referent in the plan (possible in `bank_assumptions` after a rebase) also get fresh UUIDs |
| `decision_id` | `TransferDecision.decision_id`, saved sales map | one new UUID per decision |
| `PurchaseProvenance.source` | boundary players | copied verbatim (opaque label; may mention removed decisions) |
| everything else | prices (tenths), confirmations, bank, free transfers, chips, used chips, FH19 flag, origin, horizon, observation source and time, origin tags | copied verbatim |
| `revision` | `Plan.revision` | 0 |
| `name` | `Plan.name` | allocated (section 5) |

Invariants (tested): the set of old UUIDs and the set of new UUIDs are disjoint; every reference in the copy resolves within the copy; `evaluate_plan(copy)` equals `evaluate_plan(source)` after mapping identifiers back; plan-level constructors (`Plan.__post_init__`) pass without special cases.

## 5. Naming algorithm

Inputs: source name, existing plan names (from a prefix query taken under the advisory lock).

1. `s = name.strip()`; `base = s` with one trailing ` (option N)` removed when `N` is a whole number >= 2 without leading zeros.
2. Members of the family: names equal to `base` (option 1) or `base + " (option N)"` with the same `N` rule. Exact, case-sensitive comparison.
3. `n = max(N over members, 1) + 1`.
4. Candidate = `fit(base, n)`: if `len(base) + len(" (option n)") > 100`, shorten `base` (then rstrip whitespace) so the whole name is at most 100 characters; the suffix is never shortened.
5. While the candidate equals any existing name, `n += 1` and recompute.
6. Lock key: `"plan-name-family:" + base`.

Examples: `{"My Plan"}` gives `My Plan (option 2)`; `{"My Plan","My Plan (option 2)","My Plan (option 3)"}` gives `(option 4)`; after deleting `(option 3)` gives `(option 3)`; after deleting only `(option 2)` gives `(option 4)`; source `My Plan (option 3)` with no `My Plan` present gives `My Plan (option 4)` when option 3 is the highest. A renamed original (no longer matching the base) is not a member.

Known edge (accepted): for names whose base is shortened, later duplicates compute their family from the shortened base, so the original long-named plan is not counted; uniqueness is still guaranteed by step 5.

## 6. Client state (Planner-mode Explorer)

States: `loading plan` → `choose outgoing` (no `out`) or `loading candidates` → `ready` ⇄ `previewing (loading/ready/error/unavailable)` → `confirming` (coordinator saving) → `saved` (navigate) | `rejected` | `not saved` | `conflict`.

Transitions of note:
- `rejected` with code `prices_changed` → automatic fresh preview, back to `previewing`; never an automatic resubmit.
- `conflict` → `abandon()` on the coordinator, reload plan, back to `ready` with a visible notice; user must preview again.
- Any change of outgoing player or horizon cancels in-flight requests and ignores late responses.
- Leaving while `confirming` or `not saved` triggers the departure guard.

Duplicate control states are the table in the spec; transitions: `enabled` → `duplicating` → `navigated` | `error (known)` | `unknown outcome` (control re-enabled with explicit message and a link to the Plans list).

## 7. Validation rules carried from the spec

- Money is integer tenths end to end in Planner mode; the browser formats £m only.
- Horizon gameweeks are `N..N+h-1` limited to covered projections; never zero-filled for gameweeks the run does not cover.
- A missing player in the run for a whole in-horizon squad yields the existing `missing_projections` unavailable state.
- Guard fields are both-or-neither, positive tenths, and never persisted.
