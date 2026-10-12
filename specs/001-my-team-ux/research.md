# Phase 0 Research: My Team UX and Transfer Exploration

The specification (including its clarifications) leaves no `NEEDS
CLARIFICATION` items in Technical Context — this is additive UX work on an
existing, well-understood stack. The research below records the concrete
implementation-approach decisions needed to turn the spec's resolved
behaviour into a plan, grounded in the current codebase rather than invented.

This revision incorporates code-review findings: `evaluate_single_transfer`
already computes full comparison data for in-pool illegal candidates (it
does not need to be made optional), the starting-lineup legality check used
by the squad-save path is not currently authoritative, and Transfer Preview
does not currently reject out-of-pool candidates.

## 1. Surfacing unavailable-but-in-pool candidates without losing comparison data

**Decision**: In `rank_replacement_candidates`
(`packages/fpl_engine/src/fpl_engine/transfers/replacement_ranking.py`),
stop `break`-ing out of the per-gameweek loop and stop `continue`-ing past
(dropping) a candidate when `evaluate_single_transfer` reports
`is_legal=False`. Legality (same position, club limit, budget) does not vary
by gameweek per the existing docstring — only `projected_points` does — so
every evaluated gameweek still produces a real `projected_team_gain`,
`resulting_bank`, and `direct_player_xpts_difference` for an in-pool
candidate, legal or not (position composition is preserved by construction
for same-position swaps, which is what keeps `optimal_xi_before/after` from
being `None`). Capture `is_legal` and `errors` once per candidate (they are
constant across gameweeks) and include **every** pool candidate in the
result — `team_gain_by_horizon`, `resulting_bank`, `direct_xpts_difference`,
and `gameweeks_evaluated` stay fully populated for both legal and illegal
candidates. `is_legal: bool` and `unavailable_reasons: list[str]` are new
domain result fields; decision 10 also adds advisory API status.

**Rationale**: The comparison numbers are genuine and already computed by
the existing primitive; discarding them (e.g. by making them `null`) would
throw away real data the spec asks to preserve ("a manager can see every
relevant candidate worth comparing"), and would make the API change
non-additive for no reason.

**Alternatives considered (rejected)**: Making the four existing fields
optional/`None` for illegal candidates — rejected per code review: it isn't
needed (the data exists) and makes "unavailable" look like "no comparison
possible," which isn't true.

## 2. Ordering of candidates, legal and illegal together

**Decision**: No special-casing. Since every pool candidate (legal or not)
now has a real `team_gain_by_horizon`, keep the existing single sort key —
descending team gain at the primary horizon, `player_id` as tie-break —
applied uniformly across the whole pool. Illegal candidates are naturally
interleaved wherever their projected gain places them, not segregated to
the end.

**Rationale**: Segregating illegal candidates to the end (the previous
draft of this research) was only necessary under the (incorrect) assumption
that their gain couldn't be computed. Since it can, ranking the full pool by
the same meaningful metric is both simpler and more useful for comparison.

## 3. Authoritative starting-lineup legality on the squad-save path

**Decision**: Reuse `fpl_engine.rules.validate_squad` (which composes
`validate_squad_composition` + `validate_starting_formation`) from the
squad-save path (`UpsertCurrentSquadService._validate` in
`apps/api/src/api/services/current_squad.py`), replacing that method's
hand-rolled checks. Build one `SquadSlot` per requested player (`player_id`,
`position` from the existing `SquadPlayerLookupItem` lookup already
performed there, `team_id`, `is_starting`, `bench_order`, `is_captain`,
`is_vice_captain`) and call `validate_squad(slots)`, surfacing
`RuleViolationError` as the existing `ValueError`-based 400 response (same
external contract, authoritative implementation).

**Rationale (the gap this closes)**: `UpsertCurrentSquadService._validate`
today re-implements squad-size/position-count/club-limit checks directly in
`apps/api`, duplicating domain rules (Constitution I), and — more
importantly — **never calls `validate_starting_formation` at all**. It only
checks that there are 11 starters and that the full 15-player squad has the
right position counts; it never checks that the 11 *starters themselves*
form a legal formation (1 GK, 3–5 DEF, 2–5 MID, 1–3 FWD). Concretely, the
existing frontend helper `validateStartingLineup`
(`apps/web/src/components/team/my-team-board.tsx`) requires `MID >= 3`,
which would reject a legal 5-2-3 formation that
`STARTING_POSITION_LIMITS` (`MID: (2, 5)`) explicitly allows — proof that a
frontend-only check is not authoritative and must not be the only gate. The
backend has none at all today, and this feature's direct-rearrangement
interaction (FR-004) explicitly requires the result to "remain valid under
the existing squad/formation rules," so this plan closes the gap as part of
implementing that requirement rather than leaving a known hole in place.

**Scope note**: The frontend's own `canSwapStarterWithBench`/
`canReorderBench` predicates (research item 5 below) remain a client-side
UX optimisation only — they pre-filter which targets are offered so the
interaction feels instant — but the save call through `saveMyTeam` is now
always authoritatively re-checked server-side regardless of what the
frontend believed was valid. `tasks.md` should also reconcile
`validateStartingLineup`'s `MID >= 3` with the domain's `MID >= 2` so the
frontend does not block a swap the backend would accept.

**Alternatives considered (rejected)**: Writing a new/duplicate formation
check in `apps/api` — rejected, `validate_starting_formation` already exists
and is exactly this rule (Constitution I: no duplicate rulesets).

## 4. Transfer Preview must reject out-of-pool candidates

**Decision**: Express candidate-pool eligibility once, in
`packages/fpl_engine`, as a small pure helper next to the existing transfer
code (e.g. `fpl_engine/transfers/candidate_pool.py`, exported from
`fpl_engine.transfers`) — something like
`candidate_pool_exclusion(squad, player_out_id, candidate) -> reason | None`
returning `None` for an in-pool candidate and a stable reason code
(`player_already_in_squad`, `different_position`, `player_not_selectable`,
`selectability_unknown`) otherwise. The profile carries upstream
`can_select` / `can_transact`; decision 10 defines their policy. Then:

- `rank_replacement_candidates` replaces its current inline
  `candidate.position != outgoing.position or candidate.player_id in
  squad_by_id` skip with a call to the helper, so Explorer and Preview share
  one definition of "in the pool" rather than two copies of the same rule.
- `GetTransferPreviewService.execute`
  (`apps/api/src/api/services/get_transfer_preview.py`) calls the helper
  after resolving the outgoing and incoming players and **before** loading
  projections or calling `evaluate_single_transfer`. A non-`None` result
  becomes a new structured failure
  (`TransferPreviewFailure(code="player_not_in_candidate_pool", ...)`). The
  router already maps every failure code other than `player_not_found` to
  422 (this is how `player_not_in_squad` and `missing_projections` already
  surface), so this one needs no router change and the frontend already
  renders the message via its existing `unavailable` preview state.
- `apps/api` contains no pool-eligibility logic of its own — it only
  translates the helper's result into an HTTP failure.

The existing legality evaluation is unchanged and still returns a normal
`ready` preview (`is_legal=False`, Apply disabled) for in-pool candidates
that fail budget, club limit, or another squad-level constraint.

**Rationale (the gap this closes)**: Today, `GetTransferPreviewService`
calls `evaluate_single_transfer` with whatever `player_in_id` it's given,
with no upfront pool check, so it returns a `ready`, legality-aware preview
for a player the spec says must not be previewable at all (FR-013/FR-017:
"Players outside the pool are not choosable and have no Transfer Preview").
Meanwhile `rank_replacement_candidates` already implements the pool rule,
but inline and privately — so the rule exists exactly once today, just not
reachable from Preview.

**Alternatives considered**:
- Re-implementing "same position / not already owned" in `apps/api` —
  rejected, it would duplicate a domain rule (Constitution I).
- Relying on `evaluate_single_transfer`'s errors alone — rejected as the
  only mechanism: it reports a position mismatch as the generic
  `invalid_position_composition` (indistinguishable from a squad-level
  composition failure), and it runs only after projections have been loaded,
  so a missing-projection failure could mask the real reason. A small
  explicit helper is clearer and keeps pool eligibility distinct from
  transfer legality, which is exactly the distinction the spec draws.

**Apply enforcement**: Although the evaluator already rejects wrong-position
and owned incoming players, `ApplyTransferService` must also call the shared
pool helper before loading projections/evaluating/saving, using freshly read
incoming flags. A non-eligible incoming player returns `transfer_illegal`
with the helper's reason and no write (see decision 10). Do not require
incoming-selectability flags on the outgoing player.

## 5. Bench-to-bench substitute reordering

**Decision**: Add a `canReorderBench(benchIdA, benchIdB)` predicate in
`apps/web/src/components/team/my-team-board.tsx` alongside the existing
`canSwapStarterWithBench`: both players must be on the bench, neither may be
the bench goalkeeper (`position === "GK"`), and they must be different
players. A valid reorder swaps their `bench_order` values only. As with
every other save in this feature, the result still passes through the
now-authoritative server-side `validate_squad` (research item 3).

**Rationale**: Mirrors the existing starter/bench swap predicate's style;
keeps the bench goalkeeper carve-out (resolved in clarification) explicit
and testable; requires no schema change since `bench_order` is already a
free-form 1–4 value on each squad player selection.

## 6. Selection interaction replacing Edit Team mode

**Decision**: Replace the `editState`/"Edit Team" toggle in
`my-team-board.tsx` with a single `selectedPlayerId` piece of state that is
always active on the normal squad view. Valid targets are computed on each
render from `canSwapStarterWithBench` / `canReorderBench` against the
current squad, purely for responsive UX; the swap is still saved through
`saveMyTeam` and authoritatively re-validated server-side (research item 3).

**Rationale**: FR-007 explicitly rules out a separate mode; reusing the
existing legality predicates for the *frontend's* candidate-highlighting
keeps that UX layer consistent with what's already enforced when saving,
while the backend — not the frontend — remains the legality authority.

## 7. Projected-points reveal/hide

**Decision**: A single client-only `pointsRevealed` boolean (`useState`,
default `false`) gates the per-player figures, the aggregate
1/3/5-gameweek summary, and the recommendation/comparison panel. Not
persisted (no `localStorage`/cookie/server state), per the clarified
FR-009 — it resets to hidden on reload or a later visit.

**Alternatives considered (rejected)**: Persisting the preference — the
clarification explicitly chose per-view-only behaviour.

## 8. "Explore transfers" entry point

**Decision**: No change needed beyond verification. `SquadPlayerCard`
already renders an unconditional `transferHref` link
(`/transfers?out={playerId}`) regardless of edit/selection state, which
already satisfies FR-010's "distinct, always-visible, independent of
selection" requirement once the Edit Team mode gating elsewhere is removed.

**Rationale**: Confirmed by reading `squad-player-card.tsx` and
`transfer-explorer.tsx`'s existing `?out=` handling — this journey already
works end-to-end; the feature just needs to not regress it while removing
Edit Team mode.

## 9. One shared legality-reason-to-text mapping, used by both surfaces

**Decision**: Add a single presentation-only mapping (e.g.
`apps/web/src/components/transfers/legality-reasons.ts`) from the error
codes the domain already produces (`insufficient_bank`,
`club_limit_exceeded`, and defensively `invalid_position_composition`) to
user-facing text, and use it both where the candidate comparison shows
`unavailable_reasons` (`replacement-table.tsx`) and where Transfer Preview
shows `errors` (`transfer-preview.tsx`). The API keeps returning the raw
codes on both `candidates[].unavailable_reasons` and the existing `errors`
field — no API-level text/i18n concern is introduced.

**Rationale (the gap this closes)**: Today, `transfer-preview.tsx` renders
`state.data.errors.join(", ")` — raw codes like `insufficient_bank` shown
directly to the user. The spec requires a communicated *reason*, not an
internal code, in both places (FR-016). A single shared mapping avoids
reintroducing the same bug in the new candidate-comparison UI and keeps the
two surfaces consistent by construction instead of by convention.

**Alternatives considered (rejected)**: Returning pre-formatted text from
the API — display copy is a presentation concern that belongs in
`apps/web`, consistent with how this codebase already returns
`{code, message}`-style structured errors elsewhere (e.g. the Plans
feature's `RuleViolationError.code`) and lets the caller decide
presentation.

## 10. Resolved: authoritative incoming selectability, advisory playing status

**Decision**: Same position, not already owned, and upstream `can_select`
and `can_transact` both explicitly `true` define incoming pool eligibility.
Playing `status` never determines pool membership or transfer legality.
Injury, doubt and suspension remain advisory; otherwise legal players may
be explored, previewed and applied. Existing availability/minutes projection
behaviour and unified ranking remain unchanged.

**Evidence**: A read-only GET of
`https://fantasy.premierleague.com/api/bootstrap-static/` returned HTTP 200
on 2026-10-12 (response Date: 17:47:01 GMT), with 667 elements. All elements
contained boolean `can_select` and `can_transact`. Observed combinations:

| Playing status | Count | `can_select` | `can_transact` |
|---|---|---|---|
| `a` | 466 | true | true |
| `i` | 69 | true | true |
| `d` | 22 | true | true |
| `s` | 5 | true | true |
| `u` | 105 | false | true |

For example, Saliba (`i`) had both flags true; Martinelli (`u`, departure
news) had `can_select=false`, `can_transact=true`. Thus `can_transact` alone
does not identify a player who can be bought. Requiring both flags is a
conservative incoming-selection policy; this capture establishes field
presence and observed combinations, not a published guarantee about every
combination. Do not apply this incoming-only restriction to selling an
already-owned outgoing player.

**Import gap**: `FplElementDto` has `extra="ignore"` and declares neither
flag, so it discards them. `PlayerSeed`, `map_bootstrap_static`,
`ImportFplDataService`, the domain `Player`, player repository upserts and
`PlayerModel` must carry both flags. The checked-in bootstrap fixture has
only two `status="a"` players and neither flag; it cannot establish current
upstream eligibility. Add representative true/false/missing fixtures when
implementing rather than inferring flags from that fixture's statuses.

**Narrow persistence design**: One Alembic migration adds nullable boolean
`players.can_select` and `players.can_transact`, with no true/status-derived
backfill. `None` means unknown, not eligible. Import retains missing flags
as unknown (including clearing previously-known values when absent); refresh
bootstrap after migration to populate existing rows. Unknown incoming
eligibility fails closed with an explicit refresh-required diagnostic,
never a silent `status == "a"` fallback. No new service, dependency, historical
snapshot field, projection feature or model change is needed.

**Shared enforcement**: Extend decision 4's pure domain pool helper with
the two flag inputs and stable exclusions `player_not_selectable` (either
false) and `selectability_unknown` (missing, unless already explicitly
false). Remove the repository's status filter and retrieve same-position
profiles including flags and status; the helper remains the authority for
Explorer, early Preview rejection and fresh Apply rejection. Preview uses
the existing 422 `player_not_in_candidate_pool` failure; Apply uses its
existing `transfer_illegal` failure with the exclusion reason and does not
write. An unknown selectability failure explains that a data refresh is
required. Explorer reports an explicit refresh-required failure if otherwise
relevant profiles have unknown flags, rather than silently omitting them.

**Advisory presentation**: Add `status: string` to candidate responses and
`player_in_status: string` to the Preview response (which currently exposes
IDs, not an incoming-player object). Use one presentation-only status
mapping in both views; unknown codes remain advisory and get a generic
label. Do not put status codes in `unavailable_reasons` or Preview `errors`,
disable Apply because of status, or change the projection model. Existing
comparison-field types (including existing direct-xPts nullability) stay
unchanged.

**Alternatives rejected**: `status == "a"` eligibility; treating non-`a`
status as transfer illegality; `can_transact` alone; defaulting absent flags
to true; inferring flags from status; fetching live FPL separately on every
Preview/Apply. Apply rechecks the latest imported flags, like existing
price/club data; it is not a live upstream transaction guarantee.
