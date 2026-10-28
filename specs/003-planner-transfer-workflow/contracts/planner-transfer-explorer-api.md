# Planner Transfer Explorer API Contract

Two read-only endpoints. Neither writes data, creates receipts, or reads or writes My Team. Money fields named `*_tenths` are integers (50 = £5.0m); points are floats; gameweeks are 1-38. Existing My Team endpoints (`/my-team/transfers/...`) are unchanged.

## GET /plans/{plan_id}/gameweeks/{gameweek}/transfers/{player_out_id}

Ranks and assesses replacements for one player in one plan gameweek.

Query:

| Name | Type | Default | Notes |
|---|---|---|---|
| `primary_horizon` | 1, 3 or 5 | 5 | ordering key; others 422 `invalid_horizon` |
| `projection_run_id` | int | latest `component_v3` run | pins the run for the session; unknown or non-`component_v3` run is 422 `run_not_found` / `run_model_mismatch` |

### 200 response

```text
plan: { plan_id, name, revision, start_gameweek, end_gameweek, gameweek, chip, evaluator_version }
projection: {
  model_version, run_id, generated_at, newer_run_available,
  primary_horizon,
  horizons: [ { horizon: 1|3|5, requested_gameweeks: [..], evaluated_gameweeks: [..],
                saved_plan_gameweeks: [..], assumed_gameweeks: [..], partial: bool } ],
  limited_to_selected_gameweek: bool, limited_reason: "free_hit_gameweek" | null
}
accounting_before: { starting_bank_tenths, closing_bank_tenths, free_transfers_available,
                     transfers_made, points_hit, unlimited_transfers, provisional: bool }
outgoing: {
  player_id, web_name, position, team_short_name, ownership_id,
  operation: "add_transfer" | "edit_transfer", replaces_decision_id | null,
  purchase_price_tenths, purchase_basis: { basis_kind, confirmation },
  market_price_tenths, selling_price_tenths | null, selling_provisional: bool,
  projected_points_by_horizon: { "1","3","5": float }
}
candidates: [ {
  player_id, web_name, team_short_name, position, status,            # status = playing status (advisory)
  price_tenths,
  state: "available" | "unavailable" | "blocked_by_later_decision",
  reasons: [code],                                                    # when unavailable
  conflict: { kind, gameweek, decision_id | null, code, message, shortfall_tenths | null } | null,
  valid_through_gameweek: int | null,
  resulting_bank_tenths | null, points_hit_after | null,
  best_xi_gain_by_horizon: { "1","3","5": float },                    # ranking measure
  direct_xpts_difference: float | null,
  plan_impact_by_horizon: { "1","3","5": { saved_plan: float | null, assumed_continuation: float | null,
                                           net_saved_plan: float | null, valid_through_gameweek: int | null } },
  fixtures: [ { gameweek, opponent_short_name | null, is_home | null, difficulty | null } ]
} ]
```

Ordering: descending `best_xi_gain_by_horizon[primary_horizon]`, ties by ascending `player_id` (the existing ranking rule). Blocked and unavailable candidates keep their ranked position (FR-016).

Semantics:

- The squad is the Planner's displayed squad for `gameweek` (its other planned transfers applied; Free Hit temporary squad for a Free Hit gameweek).
- `candidates` is the pool defined by My Team rules: same position, not in that squad, selectable per imported flags. Players sold by another transfer in the same gameweek appear as `unavailable` with reason `sold_this_gameweek`.
- `best_xi_gain_*` is a static-squad measure (squad at `gameweek` held constant); `plan_impact_*` replays the plan (saved roles, chips, later decisions) and is the plan's real effect. They are separate fields and never combined.
- `plan_impact_*.assumed_continuation` covers horizon gameweeks after `plan.end_gameweek` using the plan's final permanent squad and final-gameweek roles; `null` when none or `continuation_lineup_illegal`.
- Values for gameweeks beyond `valid_through_gameweek` are `null`, never estimated.
- Projections are never zero-filled for gameweeks outside the run's coverage; `partial: true` marks shortened horizons.

### Error responses

All errors use `detail: { code, message, missing_player_ids? }` as in the My Team Explorer.

| Status | `code` | When |
|---|---|---|
| 404 | `plan_not_found` | unknown plan |
| 409 | `plan_not_ready` | plan awaiting Planner initialisation |
| 422 | `gameweek_not_in_plan` | gameweek outside the plan |
| 422 | `evaluation_blocked` | the gameweek's squad cannot be evaluated (plan has a structural diagnostic) |
| 422 | `player_not_in_squad` | outgoing player not in that gameweek's squad |
| 422 | `no_projection_run` / `run_not_found` / `run_model_mismatch` | run unavailable |
| 422 | `gameweek_not_projected` | the selected gameweek is not covered by the run (for example completed) |
| 422 | `missing_projections` | squad players have no projection in the run (`missing_player_ids`) |
| 422 | `selectability_unknown` | refresh required (same message as My Team) |
| 422 | `invalid_money` | stored price not a whole tenth |
| 422 | `invalid_horizon` | bad `primary_horizon` |

## GET /plans/{plan_id}/gameweeks/{gameweek}/transfers/{player_out_id}/preview

Query: `player_in_id` (required), `projection_run_id` (recommended; same rules as above).

### 200 response

```text
plan, projection, accounting_before, outgoing              # as above
candidate: { player_id, web_name, team_short_name, position, status, price_tenths }
state, reasons, conflict, valid_through_gameweek           # as for a candidate
confirmable: bool                                          # true only when state == "available"
commit: {
  intent: { kind: "add_transfer", gameweek_number, outgoing_player_id, outgoing_ownership_id, incoming_player_id }
        | { kind: "edit_transfer", decision_id, incoming_player_id },
  guard: { expected_outgoing_market_tenths, expected_incoming_price_tenths },
  expected_revision: int
}
gameweeks: [ {
  gameweek, basis: "saved_plan" | "assumed_continuation", valid: bool, chip,
  accounting: { before: { closing_bank_tenths, free_transfers_available, transfers_made, points_hit, next_free_transfers },
                after:  { closing_bank_tenths, free_transfers_available, transfers_made, points_hit, next_free_transfers } } | null,
  squad_changed: bool,
  incoming_role: "starting" | "bench" | "captain" | "vice_captain" | null,
  points: { before, after, delta } | null,                  # excludes hit
  reason: "no_projection" | "beyond_valid_range" | "continuation_lineup_illegal" | null
} ]
totals: { horizon: 1|3|5 -> { saved_plan, assumed_continuation, hit_change, net_saved_plan } }
lineup_effect: { captain_changed: bool, vice_captain_changed: bool }
best_xi: { gain_by_horizon: { "1","3","5": float }, direct_xpts_difference: float | null }
```

Semantics:

- Preview of an `unavailable` or `blocked_by_later_decision` candidate returns 200 with `confirmable: false`, the reasons or conflict, and `gameweeks` only through `valid_through_gameweek`; later entries are `valid: false` with `reason: "beyond_valid_range"` and no values. (Same pattern as My Team, where an illegal preview is a normal 200.)
- `commit.intent` is exactly what the browser submits to `POST /plans/{plan_id}/mutations`; `commit.guard` is submitted with it (see [mutation-guard-and-selectability.md](mutation-guard-and-selectability.md)). The browser does not decide add versus edit.
- A candidate that is not in the pool (owned, wrong position, non-selectable) is 422 `player_not_in_candidate_pool` (same code family as My Team preview).
- Same error table as the list endpoint, plus 404 `player_not_found`.

## Non-functional

- No database writes; the read transaction on the plan is ended immediately after the plan is loaded.
- Target: list within 3 s and preview within 2 s on the representative dataset (SC-014).
- Responses are deterministic for a given plan revision, run and price data.
