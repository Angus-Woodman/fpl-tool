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
   via a direct `POST /my-team` call using a starting XI that violates
   `STARTING_POSITION_LIMITS` (e.g. 2 goalkeepers starting); confirm the API
   rejects it with a 400, proving the save path is now authoritatively
   validated by `validate_squad` rather than only by frontend predicates
   (see [data-model.md](./data-model.md), "Lineup Legality").

## Scenario 2 — Projected points hidden by default

1. Reload `/my-team`. Confirm per-player points, the 1/3/5-GW summary, and
   the recommended-vs-current panel are all hidden by default.
2. Use the reveal control; confirm all three become visible.
3. Hide them again; reload the page; confirm they are hidden again (not
   remembered — see [research.md](./research.md), decision 5).

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

## Automated coverage expected from `tasks.md`

- `packages/fpl_engine/tests/test_replacement_ranking.py`: illegal
  in-pool candidates are now returned (not dropped) with `is_legal=False`,
  the matching `errors`, and their full, non-null comparison data.
- `packages/fpl_engine/tests` (squad rules): a 5-2-3 starting formation
  (`MID=2`) round-trips as legal through `validate_squad`, documenting why
  the frontend's stricter `MID >= 3` check cannot be authoritative.
- `apps/api/tests` (squad save / `current_squad`): saving a starting XI
  that violates `validate_starting_formation` is now rejected by the API,
  where today it is accepted.
- `apps/api/tests/transfers/`: Transfer Explorer response includes the new
  additive fields with full comparison data for illegal candidates;
  Transfer Preview rejects an out-of-pool `player_in_id` with
  `player_not_in_candidate_pool` and still returns a normal, legality-aware
  preview for an in-pool-but-illegal one.
- `apps/web/tests/team/` and `apps/web/tests/transfers/`: selection/swap/
  reorder interactions, points reveal/hide, unavailable-candidate rendering
  with preserved comparison data, and the shared reason-mapping used by both
  the candidate comparison and Transfer Preview.
- `apps/web/tests/e2e/`: one durable Playwright spec for Scenario 1 and
  Scenario 4/5 end-to-end (rearrange, explore, see an unavailable candidate,
  preview and apply a legal one).
