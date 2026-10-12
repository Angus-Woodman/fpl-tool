# Phase 0 Research: My Team UX and Transfer Exploration

The specification (including its clarifications) leaves no `NEEDS
CLARIFICATION` items in Technical Context — this is additive UX work on an
existing, well-understood stack. The research below records the concrete
implementation-approach decisions needed to turn the spec's resolved
behaviour into a plan, grounded in the current codebase rather than invented.

## 1. Surfacing unavailable-but-in-pool candidates

**Decision**: Extend `rank_replacement_candidates`
(`packages/fpl_engine/src/fpl_engine/transfers/replacement_ranking.py`) to
stop `continue`-ing past candidates whose `evaluate_single_transfer` result
has `is_legal=False`. Instead, include them in the returned list carrying
the `is_legal` flag and the `errors` tuple already produced by
`evaluate_single_transfer` (`insufficient_bank`, `club_limit_exceeded`,
`invalid_position_composition`), with `team_gain_by_horizon` /
`resulting_bank` left absent (no reliable gain once a transfer is illegal).
The API response (`RankedTransferCandidateResponse`) gains matching optional
fields.

**Rationale**: `evaluate_single_transfer` already computes per-candidate
legality and error codes; this only changes what the caller does with an
illegal result (surface it instead of discarding it). The legality decision
itself never leaves `packages/fpl_engine` (Constitution I).

**Alternatives considered**:
- Filtering/annotating in `apps/api` instead — rejected, would duplicate the
  domain's legality logic outside `packages/fpl_engine`.
- Filtering/annotating in `apps/web` — rejected for the same reason, and it
  would require shipping the raw legality inputs (bank, club counts) to the
  client with no single authoritative source.

## 2. Ordering of now-included illegal candidates

**Decision**: Keep legal candidates sorted exactly as today (by team gain at
the primary horizon, player id as tie-break). Append illegal candidates
after all legal ones, sorted by player id for a stable, deterministic order.

**Rationale**: The spec requires illegal candidates to remain visible and
distinguishable, not that they be ranked by a gain metric that can't be
reliably computed once a transfer is illegal (evaluation stops at the first
illegal gameweek). No ordering requirement beyond that is stated.

**Alternatives considered**: Interleaving illegal candidates by price or by
a partial/best-effort gain estimate — rejected as unnecessary complexity the
spec doesn't ask for.

## 3. Bench-to-bench substitute reordering

**Decision**: Add a `canReorderBench(benchIdA, benchIdB)` predicate in
`apps/web/src/components/team/my-team-board.tsx` alongside the existing
`canSwapStarterWithBench`: both players must be on the bench, neither may be
the bench goalkeeper (`position === "GK"`), and they must be different
players. A valid reorder swaps their `bench_order` values only.

**Rationale**: Mirrors the existing starter/bench swap predicate's style;
keeps the bench goalkeeper carve-out (resolved in clarification) explicit
and testable; requires no backend change since `bench_order` is already a
free-form 1–4 value on each squad player selection.

## 4. Selection interaction replacing Edit Team mode

**Decision**: Replace the `editState`/"Edit Team" toggle in
`my-team-board.tsx` with a single `selectedPlayerId` piece of state that is
always active on the normal squad view. Valid targets are computed on each
render from `canSwapStarterWithBench` / `canReorderBench` against the
current squad. Selecting a valid target performs the swap/reorder
immediately (no separate "save" step is required by the spec for this
interaction, distinct from the transfer-apply journey).

**Rationale**: FR-007 explicitly rules out a separate mode; reusing the
existing legality predicates keeps the legality decision consistent with
what's already enforced when saving (`validateStartingLineup`).

## 5. Projected-points reveal/hide

**Decision**: A single client-only `pointsRevealed` boolean (`useState`,
default `false`) gates the per-player figures, the aggregate
1/3/5-gameweek summary, and the recommendation/comparison panel. Not
persisted (no `localStorage`/cookie/server state), per the clarified
FR-009 — it resets to hidden on reload or a later visit.

**Alternatives considered**: Persisting the preference — rejected, the
clarification explicitly chose per-view-only behaviour.

## 6. "Explore transfers" entry point

**Decision**: No change needed beyond verification. `SquadPlayerCard`
already renders an unconditional `transferHref` link
(`/transfers?out={playerId}`) regardless of edit/selection state, which
already satisfies FR-010's "distinct, always-visible, independent of
selection" requirement once the Edit Team mode gating elsewhere is removed.

**Rationale**: Confirmed by reading `squad-player-card.tsx` and
`transfer-explorer.tsx`'s existing `?out=` handling — this journey already
works end-to-end; the feature just needs to not regress it while removing
Edit Team mode.
