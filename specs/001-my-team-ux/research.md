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
candidates. Only `is_legal: bool` and `unavailable_reasons: list[str]` are
new.

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
(`player_already_in_squad`, `different_position`) otherwise. Then:

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

**`ApplyTransferService` needs no equivalent change for position/ownership**:
it already rejects anything `evaluate_single_transfer` marks illegal
(`transfer_illegal`) before saving, so a different-position or already-owned
`player_in_id` can never mutate the squad today. (Candidate *status* is a
separate, open question — see decision 10.)

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

## 10. OPEN DECISION — candidate availability status (human decision required)

**Mismatch found**: FR-013 defines the candidate pool as "same position as
the outgoing player, not already in the manager's squad." The current
implementation applies a third filter that the spec does not mention:
`PlayerReadRepository.list_available_by_position()` only returns players with
`status == "a"` (FPL "available"), so injured (`i`), doubtful (`d`),
suspended (`s`), unavailable (`u`) and not-in-squad (`n`) players never reach
`rank_replacement_candidates` at all. The repository docstring describes
this status filter as the one filter it deliberately owns.

This plan does **not** choose a product rule here. Whichever way the
decision goes, the pool-eligibility *helper* in decision 4 stays limited to
position/ownership (the FPL-rule part); candidate status is player-availability
data, not a squad-legality rule, and would live at the data-access/service
boundary. The decision changes behaviour as follows:

| Option | Explorer | Preview / Apply (direct API) | Spec impact |
|---|---|---|---|
| **A. Keep non-`"a"` players excluded** (today's Explorer behaviour) | unchanged | Today `get_by_id` applies no status filter, so Preview (and Apply, since `evaluate_single_transfer` has no status rule) currently accept a non-`"a"` `player_in_id`. To honour "out-of-pool candidates have no Preview" consistently, Preview would also need to reject non-`"a"` players (and Apply should not be able to buy one). | FR-013 amended to name the availability condition; Preview rejection reason extended. |
| **B. Include non-`"a"` players as visible-but-unavailable candidates** | widened pool; status becomes a new unavailability reason alongside budget/club limit | Preview stays reachable; Apply must be blocked while the candidate is unavailable | New legality-style reason + user-facing text; the existing "pool is not widened" clarification would need revisiting |
| **C. Include non-`"a"` players with no special treatment** | widened pool | Preview and Apply unchanged | Behaviour change with no signal to the user that the player is injured/suspended — flagged here only for completeness |

**Recommendation to review (not adopted)**: Option A is the smallest change
and matches both today's Explorer and the previously clarified "pool is not
widened" answer, but it should be a deliberate, spec-recorded rule rather
than an unrecorded repository detail — and it implies the Preview/Apply
status gap noted above must be closed for consistency.

Until this is decided, `spec.md` FR-013 is left unchanged and `tasks.md`
should not be generated.
