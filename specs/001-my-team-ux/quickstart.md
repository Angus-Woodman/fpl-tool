# Quickstart: My Team UX and Transfer Exploration

Validation guide for this feature. Pair with the `ui-browser-verification`
skill. Verification has three layers with distinct jobs (see
[research.md](./research.md), decision 13).

| Layer | Owns |
|---|---|
| Deterministic tests (domain, API, component, guarded DB) | Every artificial or transient state: `status="a"` with a false flag, flag flips after Preview, unknown/refresh-required combinations, outgoing sales, repository filter removal |
| One API-stubbed Playwright spec (`apps/web/tests/e2e/my-team-ux.spec.ts`) | The durable journey, including one non-`"a"` but selectable player |
| Real-stack manual/browser verification (this guide) | Normal flows and states that refreshed imported data actually contains |

## Prerequisites

```sh
make db-up
make backend-dev   # separate terminal
make frontend-dev  # separate terminal
```

A saved squad must already exist on My Team (use the existing "Create
Starter Squad" action if not).

**Migration and refresh gate** (needed for real-stack checks of Scenarios 3-6
and the final pass once the player-flag migration exists): run
`make db-migrate`, then `make data-refresh`, so imported players carry
authoritative `can_select` / `can_transact` values. Never backfill them from
status. These steps are additive; they are human-run or human-confirmed.
Scenario 1 needs only the migration if it has already been applied.

**Rules for real-stack verification**

- Verify normal flows and representative states that refreshed data actually
  contains. Do not mutate development data to manufacture a state.
- Anything the data cannot naturally produce is verified with deterministic
  tests or stubs, not here: `status="a"` with a false flag, a flag changing after
  Preview, and unknown/refresh-required combinations.
- Applying a transfer on the real stack changes the saved squad; do it only with
  the human's explicit consent. Otherwise rely on the stubbed Playwright spec for
  Apply. Swapping lineup players and swapping back is normal usage.

## Scenario 1 — Direct rearrangement, no Edit Team mode

1. Open `/my-team` with no optimiser mode selected. Confirm there is no "Edit
   Team" mode, and no per-player "Transfer" button, "Replacement Player"
   dropdown or "Confirm Transfer" (spec FR-007a).
2. Note the displayed Bank. Confirm it is the saved bank (it need not equal
   `100 - Cost`; spec FR-004b).
3. Select a starting player; confirm it is clearly indicated as selected and only
   legal bench targets are highlighted.
4. Select a valid bench target; confirm the swap happens immediately, a swap
   confirmation naming both players appears (FR-005), the lineup stays
   formation-valid, and the displayed Bank is unchanged after reload.
5. Select a bench outfield player first, then a legal starter; confirm the same
   swap happens in the other direction.
6. Select a player, then a different player who is not a valid target; confirm
   the new selection replaces the old one without an error. Confirm selecting
   the selected player again (or a clear control) cancels the selection.
7. Select two outfield bench players and confirm their substitute order
   reorders; confirm the bench goalkeeper cannot be reordered against outfield
   subs.
8. Switch the optimiser to xPts or Fixture difficulty; confirm selection is
   unavailable while it shows a hypothetical lineup, and returns when set to
   None. The optimiser, gameweek and refresh controls stay available.
9. Backend authority: send a direct `PUT /my-team` using a starting XI that
   violates the formation limits (for example 2 goalkeepers starting); confirm
   HTTP 400 (see [data-model.md](./data-model.md), "Lineup Legality"). The
   request is rejected before saving.

## Scenario 2 — Projected points hidden by default

1. Reload `/my-team`. Confirm per-player points, the 1/3/5-GW summary and the
   recommended-vs-current panel are hidden by default.
2. Use the reveal control; confirm all three become visible.
3. Hide them again; reload; confirm they are hidden again (not remembered, see
   [research.md](./research.md), decision 7).

## Scenario 3 — Explore transfers from My Team, preserving context

1. From a squad player's card (starter and bench), use "Explore transfers".
2. Confirm `/transfers` opens already showing that player as the one being
   replaced (`?out=` preserved), with no re-selection.
3. Confirm the link is present on every card whether or not a player is
   selected for rearrangement.

## Scenario 4 — Unavailable candidates stay visible, comparable and previewable

Real-stack check applies only when the refreshed data and current squad
naturally contain a candidate failing a legality constraint (for example a
premium-priced candidate for a budget outgoing player). Otherwise rely on
deterministic tests and the stubbed Playwright spec.

1. Find such a candidate. Confirm it is listed, visually marked unavailable, and
   shows a user-facing reason, not a raw code like `insufficient_bank` (see
   [contracts/transfer-explorer-get.md](./contracts/transfer-explorer-get.md) and
   [data-model.md](./data-model.md), "Legality reason mapping").
2. Confirm it keeps its comparison figures (resulting bank, 1/3/5-GW gain, direct
   xPts difference).
3. Open its Transfer Preview; confirm it opens normally, repeats the mapped
   reason and keeps Apply disabled.
4. Confirm a wrong-position, already-owned or non-selectable player is absent,
   and that a direct read-only `GET` Preview for such a player is rejected with
   422 `player_not_in_candidate_pool` (see
   [contracts/transfer-preview-get.md](./contracts/transfer-preview-get.md)).

## Scenario 5 — Preview, then explicit Apply

1. Choose a fully legal candidate; open its Transfer Preview.
2. Confirm the saved squad is unchanged while the preview is open, and that
   backing out changes nothing.
3. Apply only with the human's consent (it changes the saved squad); confirm the
   squad updates. Otherwise this step is covered by the stubbed Playwright spec.

## Scenario 6 — Advisory playing status versus incoming selectability

**6A, real-stack (states present in refreshed data):**

1. Find a same-position, not-owned player with `status` `i`, `d` or `s` that has
   both flags true. Confirm it appears with a useful advisory status, keeps
   existing availability-adjusted projections and unified ranking, and reaches
   Preview with the same advisory status.
2. Confirm that when legality passes, Apply is enabled; when it fails, only the
   existing legality reason disables Apply, never the status warning.
3. Confirm players with `can_select=false` (for example status `u`) do not
   appear, and a direct read-only Preview `GET` for one returns 422
   `player_not_in_candidate_pool`.

**6B, deterministic only (never manufactured on development data):**

- `status="a"` with `can_select=false` or `can_transact=false`.
- A flag changing from true to false after a legal Preview; Apply rechecks and
  rejects with no write.
- Unknown flags: Explorer returns 422 `selectability_unknown`, Preview returns 422
  `player_not_in_candidate_pool` with a refresh message, Apply returns
  `transfer_illegal` / `selectability_unknown` with no write. A refresh normally
  resolves it; if upstream omits the field the diagnostic intentionally persists.
- Exclusion precedence: structural, then known non-selectable, then unknown.
- An owned outgoing player with false incoming flags can still be sold.

## Automated coverage expected from `tasks.md`

- `packages/fpl_engine/tests/test_replacement_ranking.py`: illegal in-pool
  candidates are returned (not dropped) with `is_legal=False`, the matching
  `errors` and full comparison data with unchanged types (including existing
  direct-xPts nullability); one unified sort.
- `packages/fpl_engine/tests/test_candidate_pool.py`: the shared helper returns
  `None` for a same-position, not-owned candidate with both flags true;
  exclusions cover owned, position, either false flag, missing flags, and the
  precedence structural, then known non-selectable, then unknown (including a
  false flag beside a missing one). Non-`a` status never changes eligibility.
- `packages/fpl_engine/tests` (squad rules): a 5-2-3 starting formation (`MID=2`)
  is legal through `validate_squad`; two starting goalkeepers fail.
- `apps/api/tests` (squad save): an illegal starting formation is now rejected,
  existing messages are unchanged, and no selectability rule is applied on this
  path.
- `apps/api/tests/transfers/`: Explorer, Preview and Apply for every Scenario 6B
  case, advisory response fields, `selectability_unknown`, rejection before
  projections load, stale-Preview Apply, outgoing sales, zero writes on rejected
  Apply.
- `apps/api/tests/fpl/`, `tests/services/`, guarded repository integration tests
  (`requires_database`, `TEST_DATABASE_URL`, `_test` safeguard; never the
  development database): flags parsed, mapped, persisted and cleared
  independently of status; a freshly migrated row reads as unknown; **and
  `list_by_position` returns otherwise eligible non-`"a"` players and no longer
  applies the old `status == "a"` SQL filter.**
- `apps/web/tests/team/`: selection, valid targets, swap and bench reorder
  (starter-first and bench-first), the swap confirmation (`aria-live`),
  displayed Bank equals the saved bank, swap/reorder request `bank` equals the
  saved bank, optimiser gating, no inline Transfer controls, Explore links, and
  points reveal/hide.
- `apps/web/tests/transfers/`: unavailable-candidate rendering, shared reason and
  status mappings, `selectability_unknown` display, Apply disabled only when
  `is_legal` is false.
- `apps/web/tests/e2e/my-team-ux.spec.ts`: one durable, **API-stubbed** Playwright
  spec for rearrange, explore, an unavailable candidate (Apply disabled), a legal
  preview and apply, **plus one case where a non-`"a"` but authoritatively
  selectable player remains explorable, previewable and applicable.** Flag
  transitions and unknown/refresh-required combinations stay in the lower-layer
  tests above, not Playwright.
