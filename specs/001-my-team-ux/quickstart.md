# Quickstart: My Team UX and Transfer Exploration

Manual end-to-end validation guide for this feature. Pair with the
`ui-browser-verification` skill and the Playwright coverage added under
`apps/web/tests/e2e/` for the core journey.

## Prerequisites

```sh
make db-up
make backend-dev   # separate terminal
make frontend-dev  # separate terminal
```

A saved squad must already exist on My Team (use the existing "Create
Starter Squad" action if not).

After implementing the player-flag migration, migrate through the existing
workflow and refresh bootstrap data so imported players have authoritative
`can_select` / `can_transact` values. Never backfill them from status. Use
representative deterministic fixtures for the cases below if live data
lacks them; do not alter persistent development data to manufacture cases.

## Scenario 1 — Direct rearrangement, no Edit Team mode

1. Open `/my-team`.
2. Confirm there is no "Edit Team" button/mode to enter.
3. Select a starting player; confirm it's clearly indicated as selected and
   only legal bench targets are highlighted as valid.
4. Select a valid bench target; confirm the swap happens immediately and is
   clearly indicated, and the lineup stays formation-valid.
5. Select a player, then select a different player who isn't a valid target
   for the first; confirm the new selection replaces the old one rather than
   erroring.
6. Select two non-goalkeeper bench players and confirm their substitute
   order reorders; confirm the bench goalkeeper cannot be reordered against
   outfield subs (see [data-model.md](./data-model.md)).
7. Backend authority check: with the frontend open, attempt to save a squad
   via a direct `PUT /my-team` call using a starting XI that violates
   `STARTING_POSITION_LIMITS` (e.g. 2 goalkeepers starting); confirm the API
   rejects it with a 400, proving the save path is now authoritatively
   validated by `validate_squad` rather than only by frontend predicates
   (see [data-model.md](./data-model.md), "Lineup Legality").

## Scenario 2 — Projected points hidden by default

1. Reload `/my-team`. Confirm per-player points, the 1/3/5-GW summary, and
   the recommended-vs-current panel are all hidden by default.
2. Use the reveal control; confirm all three become visible.
3. Hide them again; reload the page; confirm they are hidden again (not
   remembered — see [research.md](./research.md), decision 7).

## Scenario 3 — Explore transfers from My Team, preserving context

1. From a squad player's card, use "Explore transfers".
2. Confirm `/transfers` opens already showing that player as the one being
   replaced (`?out=` preserved), without re-selecting them.

## Scenario 4 — Unavailable candidates stay visible, comparable, and previewable

1. In the resulting candidate comparison, find or construct a candidate
   that fails a transfer-legality constraint (e.g. priced above the
   available budget).
2. Confirm it is still listed (not omitted), visually marked unavailable,
   with a user-facing reason shown — not a raw code like `insufficient_bank`
   (see [contracts/transfer-explorer-get.md](./contracts/transfer-explorer-get.md)
   and [data-model.md](./data-model.md), "Legality reason mapping").
3. Confirm it still shows the same comparison figures (resulting bank,
   1/3/5-GW gain, direct xPts difference) as a legal candidate would — these
   are not hidden or blanked out merely because the candidate is unavailable.
4. Open its Transfer Preview; confirm the preview opens normally, repeats
   the (mapped, non-raw) reason, and keeps Apply disabled.
5. Confirm a player of a different position, or already in the squad, does
   not appear in the comparison at all, **and** that directly requesting a
   Transfer Preview for such a player (e.g. via the API) is rejected rather
   than returning an illegal-but-viewable preview (see
   [contracts/transfer-preview-get.md](./contracts/transfer-preview-get.md)).

## Scenario 5 — Preview → explicit apply

1. Choose a fully legal candidate; open its Transfer Preview.
2. Confirm the manager's actual squad is unchanged while the preview is
   open.
3. Apply the transfer; confirm the squad updates to reflect it.
4. Repeat, but back out of the preview instead; confirm no change was made.

## Scenario 6 — Advisory Playing Status Versus Incoming Selectability

1. Use a same-position, not-owned player with `status="i"`, `"d"` or `"s"`
   and both upstream flags true. Confirm it appears with a useful advisory
   status, retains existing availability-adjusted projections and unified
   gain ranking, and reaches Preview with the same advisory status.
2. If budget/club/squad legality passes, confirm Apply is enabled and works;
   if it fails, confirm only the existing legality reason disables Apply,
   not the playing-status warning.
3. Use a player with either flag false (including `can_select=false`,
   `can_transact=true` and `status="a"`). Confirm no candidate row, direct
   Preview returns 422 `player_not_in_candidate_pool`, and direct Apply
   returns 422 `transfer_illegal` without a write.
4. In isolated test fixtures, change an incoming flag from true to false
   after a legal Preview. Confirm Apply rechecks it and rejects without
   changing the saved squad.
5. With otherwise relevant unknown flags and neither false, confirm Explorer
   returns 422 `selectability_unknown`, Preview explains the refresh need
   through 422 `player_not_in_candidate_pool`, and Apply reports
   `transfer_illegal` / `selectability_unknown` without mutation. Refreshing
   populated flags resolves the condition; status never supplies a fallback.
6. Confirm an already-owned outgoing player with incoming flags false can
   still be sold for an eligible replacement. No new projection model or
   availability-driven transfer-legality rule should be introduced.

## Automated coverage expected from `tasks.md`

- `packages/fpl_engine/tests/test_replacement_ranking.py`: illegal
  in-pool candidates are now returned (not dropped) with `is_legal=False`,
   the matching `errors`, and their full comparison data with unchanged
   types (including existing direct-xPts nullability).
- `packages/fpl_engine/tests/test_candidate_pool.py`: the shared
  pool-eligibility helper returns `None` for a same-position, not-owned
   candidate with both flags true; exclusions cover owned, position, either
   false flag, both/mixed missing flags and false-plus-missing precedence.
   Non-`a` status must not change eligibility; ranking uses the helper.
- `packages/fpl_engine/tests` (squad rules): a 5-2-3 starting formation
  (`MID=2`) round-trips as legal through `validate_squad`, documenting why
  the frontend's stricter `MID >= 3` check cannot be authoritative.
- `apps/api/tests` (squad save / `current_squad`): saving a starting XI
  that violates `validate_starting_formation` is now rejected by the API,
  where today it is accepted.
- `apps/api/tests/transfers/`: Transfer Explorer response includes the new
  additive fields with full comparison data for illegal candidates;
  Transfer Preview rejects an out-of-pool `player_in_id` (422,
  `player_not_in_candidate_pool`) and still returns a normal, legality-aware
  preview for an in-pool-but-illegal one.
- `apps/api/tests/fpl/`, repository tests and guarded DB tests: parsing,
  mapping and insert/update preserve true/false/unknown flags independently
  of status; missing flags clear stale values; migration leaves existing
  rows unknown and bootstrap refresh fills them; position queries no longer
  filter status. DB checks use only `TEST_DATABASE_URL` with the existing
  `_test` safeguard, never the development database.
- `apps/api/tests/transfers/`: Scenario 6 at service/router boundaries,
  including all three endpoints, advisory response fields, unknown-data
  messages, rejection before missing projections, stale-Preview Apply,
  non-selectable outgoing sales and zero writes on rejected Apply.
- `apps/web/tests/team/` and `apps/web/tests/transfers/`: selection/swap/
  reorder interactions, points reveal/hide, unavailable-candidate rendering
  with preserved comparison data, and the shared reason-mapping used by both
   the candidate comparison and Transfer Preview; shared advisory status
   mapping and unknown-code rendering, independent from legality/Apply state.
- `apps/web/tests/e2e/`: one durable Playwright spec for Scenario 1 and
  Scenario 4/5 end-to-end (rearrange, explore, see an unavailable candidate,
   preview and apply a legal one), plus Scenario 6's important browser
   journey for a selectable non-`a` player and the refresh-required state.
