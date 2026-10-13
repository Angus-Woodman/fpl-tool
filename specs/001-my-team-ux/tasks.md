---

description: "Task list for My Team UX and Transfer Exploration"
---

# Tasks: My Team UX and Transfer Exploration

**Input**: Design documents from `/specs/001-my-team-ux/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED. The constitution (Principles IV, V, VI, VII) and `quickstart.md` require tests at the layer that owns each behaviour, browser verification, and durable Playwright coverage. Within each phase, write tests first and confirm they fail before implementing.

**Organization**: Grouped by user story (US1-US4 from spec.md) and ordered so every task appears after the tasks it depends on. Phase 3 (selectability data path) is a prerequisite for US2 and US3 only; US1 and US4 do not depend on it, so US1 can ship as the MVP before the migration exists.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1-US4, only on user-story phases
- Python paths are relative to the repo root. Backend commands run from the repo root (see `Makefile`).

## Path Conventions

- `packages/fpl_engine/` - framework-independent domain rules and tests
- `apps/api/src/api/`, `apps/api/tests/` - FastAPI, services, repositories, Alembic (`apps/api/alembic/versions/`)
- `apps/web/src/`, `apps/web/tests/` - Next.js UI, Vitest tests, Playwright specs (`apps/web/tests/e2e/`)

---

## Phase 1: Setup (Baseline)

**Purpose**: Establish a known-green baseline so later failures are attributable to this feature.

- [X] T001 Confirm the branch is `feature/my-team-ux` and the working tree contains only this feature's `specs/001-my-team-ux/` artifacts (no unrelated changes), then run `make lint && make typecheck && make test` and record any pre-existing failures before changing code.
- [X] T002 Run `make test-integration` (it uses only the dedicated `fpl_test` database via `TEST_DATABASE_URL`; never run integration tests against the development database, never bypass `ensure_test_database_url`) and record the baseline.

---

## Phase 2: User Story 1 - Rearrange the starting XI and bench directly (Priority: P1) MVP

**Goal**: Replace Edit Team mode (and the inline Transfer path that lives only inside it) with always-on selection-based swaps (starter/bench and outfield bench priority), authoritative server-side lineup validation, and the saved bank preserved and displayed.

**Independent Test**: On `/my-team`, select a starter, see only legal bench targets, select one, and the swap saves immediately with a visible confirmation, no Edit Team mode, and the saved bank unchanged. A direct `PUT /my-team` with an illegal starting formation returns HTTP 400.

**Depends on**: Setup only. Does not need Phase 3.

### Tests for User Story 1 (write first, confirm failing)

- [X] T003 [P] [US1] Extend `packages/fpl_engine/tests/test_rules.py`: a 5-2-3 starting XI (`MID=2`) passes `validate_squad`; a starting XI with 2 goalkeepers fails with code `formation`. This documents why the frontend's `MID >= 3` check cannot be authoritative.
- [X] T004 [P] [US1] Extend `apps/api/tests/team/test_current_squad_service.py`: saving a starting XI that violates the starting formation (for example 2 GK starting, otherwise a valid 15-player squad) raises `ValueError`; a legal 5-2-3 is accepted; existing messages (size, duplicates, unknown players, bench order, captain, composition) are unchanged and the club-limit message now uses the domain wording ("more than 3 players from one team", previously "three"; an accepted change); no ownership or selectability rule is introduced on this path (the behavioural proof that saving ignores imported `can_select`/`can_transact` is T028, once the flags exist).
- [X] T005 [P] [US1] Extend `apps/api/tests/team/test_my_team_router.py`: `PUT /my-team` with an illegal starting formation returns 400 with the validation message and does not commit.
- [X] T006 [US1] Rewrite the Edit Team tests in `apps/web/tests/team/my-team-board.test.tsx` for the new interaction: no "Edit Team"/"Save Changes"/"Cancel" controls; selecting a player marks it selected and marks only legal targets; selecting a valid starter target performs one `PUT /my-team` with the swap, the loaded `free_transfers` and the loaded `bank` exactly; **bench-first selection**: selecting a bench outfield player first and then a legal starter performs the same swap (and bench GK first then the starter GK); selecting a non-target replaces the selection without error; the selection can be cancelled (toggle the selected player or a clear control); a selected player with no legal targets shows a "no valid swap targets" message; outfield bench-to-bench reorder swaps `bench_order` only; the bench goalkeeper cannot be reordered against outfield subs; a 5-2-3 swap is offered (regression for `MID >= 3`); swapping a captain/vice starter to the bench moves the badge to the incoming starter; **FR-005 confirmation**: after a swap, a polite `aria-live` status naming both players is present and updates on a second swap; selection is disabled while the optimiser mode is not "None" and returns when set back; a rejected save shows the server message and leaves the displayed squad unchanged. **Saved-bank regression**: load a team whose `bank` (for example `2.3`) deliberately differs from `100 - sum(current_price)`; assert the displayed Bank equals the loaded `2.3` (update the existing "renders computed cost/bank" test accordingly; Cost stays the computed sum) and, after a starter/bench swap and after a bench-to-bench reorder, the `PUT /my-team` body's `bank` equals `2.3` exactly with `free_transfers` equal to the loaded value. Remove the old swap-dropdown and inline Transfer tests and assert that no "Transfer" button or "Replacement Player" control renders and that loading My Team does not request the player pool (only Create Starter Squad does).

### Implementation for User Story 1

- [X] T007 [P] [US1] Update `apps/web/src/components/team/squad-player-card.tsx` with the selection API the board will consume: props for selected / valid-target / not-a-target states with matching visual states and an accessible select control (button with `aria-pressed`, labelled with the player name), while keeping the "Explore transfers" link a separate, always-visible element that does not trigger selection. Adjust `apps/web/src/components/team/bench.tsx` / `squad-pitch.tsx` only where needed to pass state through. `RecommendedSquadView` stays read-only and unchanged. Must precede T009.
- [X] T008 [P] [US1] Rewire `UpsertCurrentSquadService._validate` in `apps/api/src/api/services/current_squad.py` onto `fpl_engine.rules.validate_squad`: keep the 15-player count, duplicate and unknown-player checks (the lookup is needed first), then build one `SquadSlot` per requested player (`player_id`, `position=PlayerPosition(...)` and `team_id` from `SquadPlayerLookupItem`; `is_starting`, `bench_order`, `is_captain`, `is_vice_captain` from the request) and call `validate_squad`, letting `RuleViolationError` (a `ValueError`) reach the existing router 400 path. Remove the now-duplicated hand-rolled bench/captain/position/club checks. The domain messages match the previous ones except the club-limit wording ("more than 3 players from one team", previously "three"; accepted), so external behaviour is otherwise unchanged apart from the starting formation now being enforced. Do not add ownership or incoming-selectability checks to `PUT /my-team`; this feature only adds authoritative squad/formation validation there.
- [X] T009 [US1] In `apps/web/src/components/team/my-team-board.tsx`, add a `selectedPlayerId: number | null` state that is active on the current-squad view only while `optimiseMode === "none"` (optimiser modes show a hypothetical lineup and are read-only for rearrangement; the optimiser, gameweek and refresh controls stay visible). Support selection from either side (starter-first and bench-first). Add `canReorderBench(benchIdA, benchIdB, ...)` beside `canSwapStarterWithBench` (both on the bench, different players, neither the bench goalkeeper). Replace the frontend formation check with bounds mirroring `STARTING_POSITION_LIMITS` in `packages/fpl_engine/src/fpl_engine/rules/squad.py` (GK 1, DEF 3-5, MID **2-5**, FWD 1-3), fixing the incorrect `MID >= 3` in `canSwapStarterWithBench`; comment that this is UX pre-filtering and the server is authoritative. Pass the T007 selection props to the cards. Depends on T007.
- [X] T010 [US1] In `my-team-board.tsx`, implement the swap/reorder: selecting a valid target immediately calls `saveMyTeam` with the swapped selections and the currently loaded team's `bank` exactly as returned by `GET /my-team` plus its `free_transfers`; never recompute `bank` from `BUDGET_CAP` or current squad prices, then reloads via `loadMyTeam`. Starter/bench swap keeps the existing captain/vice transfer to the incoming starter and bench order handover; bench/bench reorder swaps only `bench_order`. Show the swap confirmation (`aria-live` text naming both players), disable selection while saving, and on failure show the error and restore the pre-swap view. Selecting a non-target replaces the selection; no navigation guard is needed because selection is ephemeral component state. Depends on T009.
- [X] T011 [US1] In `my-team-board.tsx`, display the saved `loadedTeam.bank` in the header instead of `Number((BUDGET_CAP - totalCost).toFixed(1))`; keep `Cost` as the computed sum of `current_price`. Depends on T010 (same file).
- [X] T012 [US1] Remove the Edit Team-only flows from `my-team-board.tsx` that cannot exist without the mode: header Edit/Save/Cancel buttons, `EditState`/draft state, `handleStartEditing`/`handleCancelEditing`/`handleSaveChanges`, the swap dropdown (`swapTargetStarterId`, `swapChoiceBenchId`, `eligibleBenchOptionsForStarter`, `applyStarterBenchSwap`) and `renderEditControls`, and the entire legacy inline per-player "Transfer" path: the "Transfer" button, the "Replacement Player" dropdown and "Confirm Transfer", state (`transferPlayerPool`, `transferTargetPlayerId`, `transferChoicePlayerId`, `transferSavingPlayerId`, `transferError`) and helpers (`ensureTransferPlayerPool`, `handleOpenTransfer`, `eligibleTransferOptions`, `handleConfirmTransfer`), plus `validateStartingLineup` and any imports left unused. Keep `fetchPlayers` only where Create Starter Squad still needs it. The always-visible Explore transfers, then Preview, then Apply flow (spec FR-007a, FR-010, FR-017) replaces this path. Depends on T010 and T011.
- [X] T013 [US1] Run `ui-browser-verification` for quickstart Scenario 1 against the actual local frontend and API (`make db-up`, `make backend-dev`, `make frontend-dev`) on normal data. If the selectability migration (T024) has already been applied to the development database, run its migration step first (see T029). Cover: no Edit Team and no inline Transfer controls, saved bank displayed and unchanged after a swap and reload, selection, valid-target marking, swap and confirmation, bench-first selection, cancel, replacement of selection, no-target case, bench reorder, bench GK exclusion, optimiser gating, captain badge effect, error state, and the direct `PUT /my-team` HTTP 400 check. Swapping and swapping back is normal usage; do not alter other development data. Record what was observed and what could not be verified.

  **Recorded result (real stack, completed)**: observed no Edit Team and no inline Transfer controls; the saved bank (3.0) displayed and unchanged after swaps and reloads; selection and valid-target marking; a starter/bench swap with its confirmation (selected-first and bench-first, including the bench goalkeeper and an outfield sub); a non-target replacing the selection; a bench-to-bench reorder changing only bench order; the bench goalkeeper not offered as a target for outfield subs; the captain badge moving to the incoming starter and back; and a direct illegal-formation `PUT /my-team` returning HTTP 400 and saving nothing. Every swap was reverted and the saved squad confirmed identical to its starting state. **Not reproduced manually**: optimiser gating (the native `<select>` could not be driven with the available browser tooling), the no-valid-targets message and the save-error state (both need unusual squads or failing saves), and the Clear selection / toggle-cancel interaction; these are covered deterministically by component tests. The task is complete on that basis.

**Checkpoint**: US1 is fully functional and independently verifiable without any later phase (MVP path stops here).

---

## Phase 3: Selectability Data Path and Shared Pool Helper (prerequisite for US2 and US3)

**Purpose**: Carry FPL's `can_select` / `can_transact` through import and persistence and define the single domain pool-eligibility rule (research.md decisions 4 and 10; data-model.md "Imported Player Selectability" and "Candidate pool eligibility"). No user-visible behaviour changes in this phase. US1 and US4 do not depend on it.

**Depends on**: Setup. May run in parallel with Phase 2 by a different person.

### Tests (write first, confirm failing)

- [X] T014 [P] Add `packages/fpl_engine/tests/test_candidate_pool.py` for the new helper `candidate_pool_exclusion(squad, player_out_id, candidate) -> reason | None`. Cover: `None` when same position, not owned, `can_select is True` and `can_transact is True`; `player_already_in_squad`; `different_position`; `player_not_selectable` when either flag is `False`; `selectability_unknown` when either flag is `None` and neither is `False`; a known `False` flag wins over a missing other flag (data-model.md: "A known false flag excludes the player even if the other flag is missing"). **Precedence** is (1) structural (already owned, then wrong position), (2) known non-selectable (either flag `False`), (3) unknown selectability, so an owned or wrong-position player with `can_select=False` or unknown flags reports the structural reason, and a `False` flag beside an unknown one reports `player_not_selectable`; test each ordering. Include a test that `can_transact=True` with `can_select=False` is excluded (live data: 105 such players with status `u`) and that no `status` value changes the result.
- [X] T015 [P] Extend `packages/fpl_engine/tests/test_entities.py`: `Player` accepts `can_select` and `can_transact` as optional (default `None`) without breaking existing constructor calls.
- [X] T016 [P] Extend `apps/api/tests/fpl/test_bootstrap_schemas.py` and `apps/api/tests/fpl/test_bootstrap_mapper.py` using inline payloads (do not edit the captured `data/fixtures/fpl/bootstrap_static.json`): flags parse as `True`, `False` and absent (`None`); the mapper carries them into `PlayerSeed`; flags are independent of `status` (for example `status="a"` with `can_select=False`; `status="i"` with both `True`).
- [X] T017 [P] Extend `apps/api/tests/services/test_import_fpl_data_service.py`: the `Player` objects passed to the player repository carry `can_select` / `can_transact` unchanged, including `None`.
- [X] T018 [P] Add `apps/api/tests/repositories/test_player_repository_integration.py` (`pytestmark = requires_database`, `db_session` fixture, pattern from `test_team_repository_integration.py`): `upsert_many` persists `True`, `False` and `None`; re-importing a player whose flags are now absent clears the previously stored value to `None`; independent of `status`.
- [X] T019 [P] Add `apps/api/tests/repositories/test_player_read_repository_integration.py` (same database guard): `get_by_id` and the by-position list method (`list_available_by_position` at this point; renamed in T048) return `can_select` / `can_transact` on `CandidatePlayerRecord`, and a freshly migrated row (flags never imported) reads as `None`/`None`.

### Implementation

- [X] T020 [P] Add `can_select: bool | None = None` and `can_transact: bool | None = None` to the domain `Player` in `packages/fpl_engine/src/fpl_engine/domain/entities.py`. Constraint (data-model.md): "nullable in imported/domain/persisted data when absent". `None` means unknown, never eligible.
- [X] T021 Create `packages/fpl_engine/src/fpl_engine/transfers/candidate_pool.py` implementing `candidate_pool_exclusion` per T014 and export it from `packages/fpl_engine/src/fpl_engine/transfers/__init__.py`. Add optional `can_select` / `can_transact` fields (default `None`) to `PricedPlayer` in `replacement_ranking.py`, avoiding a circular import with that module (for example by defining the profile type where both modules can import it and re-exporting `PricedPlayer` from `fpl_engine.transfers`). Pure function; no FastAPI/SQLAlchemy imports; stable reason codes `player_already_in_squad`, `different_position`, `player_not_selectable`, `selectability_unknown`, evaluated in the precedence defined in T014. `status` is not an input.
- [X] T022 [P] Add `can_select: bool | None = None` and `can_transact: bool | None = None` to `FplElementDto` in `apps/api/src/api/adapters/fpl/schemas.py` (keep `extra="ignore"`), to `PlayerSeed` in `apps/api/src/api/adapters/fpl/mappers.py`, and map them in `map_bootstrap_static`. Do not default absent flags to `True` and do not derive them from `status`.
- [X] T023 Pass the flags from `PlayerSeed` into the domain `Player` in `ImportFplDataService.import_bootstrap_static` (`apps/api/src/api/services/import_fpl_data.py`). Depends on T020 and T022.
- [X] T024 Add nullable `can_select` and `can_transact` Boolean columns to `PlayerModel` in `apps/api/src/api/models/entities.py` and write one Alembic migration by hand in `apps/api/alembic/versions/` (unique 12-hex revision id) with `down_revision = "a1c8f3e6d940"` (current head). Add the columns nullable with no server default and no backfill from `status` or any default-true value; downgrade drops them. Do not run `alembic revision --autogenerate` or `make db-revision` against the development database (autogenerate connects to the configured `DATABASE_URL`). Verify upgrade/downgrade only against `fpl_test` via `make test-integration` (`db-test-up` runs `alembic upgrade head` on `fpl_test`).
- [X] T025 Persist the flags in `PlayerRepository.upsert_many` (`apps/api/src/api/repositories/player_repository.py`) in both the insert values and the `on_conflict_do_update` `set_` map taken from `statement.excluded`, so an absent flag overwrites a stale value with `NULL`. Depends on T024.
- [X] T026 Add `can_select` and `can_transact` (`bool | None`) to `CandidatePlayerRecord` and select them in `PlayerReadRepository.get_by_id` and `list_available_by_position` in `apps/api/src/api/repositories/player_read_repository.py`. Leave the `status == "a"` filter untouched here (removed in T051). Depends on T024.
- [X] T027 Update the existing `CandidatePlayerRecord` helper constructors in `apps/api/tests/transfers/test_apply_transfer_service.py`, `test_get_transfer_explorer_service.py` and `test_get_transfer_preview_service.py` to supply explicit flag values (test helper default `True`/`True`) so existing tests keep their meaning. Depends on T026.
- [X] T028 Add a behavioural regression proving `PUT /my-team` does not enforce incoming selectability: a guarded integration test `apps/api/tests/team/test_current_squad_selectability_integration.py` (`pytestmark = requires_database`, `db_session` fixture, `TEST_DATABASE_URL` and the existing `_test` safeguard; never the development database) that persists a valid 15-player squad's players via `PlayerRepository.upsert_many` with `can_select=False`, `can_transact=False` and unknown (`None`) flags, then calls the real `UpsertCurrentSquadService` with the real current-squad and lookup repositories, and asserts the save succeeds and the squad is persisted. Do not replace this with a structural (attribute-absence) test. Depends on T024 and T025.
- [X] T029 **Operational gate (human-run or human-confirmed; not performed by the agent without confirmation)**: apply the migration to the local development database with `make db-migrate`, then, once T022, T023 and T025 are done, run `make data-refresh` so existing rows get `can_select`/`can_transact`. This gate is required before any real-backend manual or browser verification of US2, US3, US4 and the final pass (T040, T058, T062, T064), and before re-running T013 if T024 has already landed. Until the refresh every player reads as unknown and Explorer returns `selectability_unknown`. The steps are additive and non-destructive; never truncate or reset development data. Automated tests never depend on this task. Depends on T022, T023, T024 and T025.

**Checkpoint**: `make lint`, `make typecheck`, `make test` and `make test-integration` pass; `make test-integration` applies the new migration to `fpl_test`; existing behaviour unchanged.

---

## Phase 4: User Story 2 - Explore and preview a transfer starting from a squad player (Priority: P2)

**Goal**: Exploration starts from a specific squad player with context preserved; every in-pool selection reaches Preview before mutation; Preview and Apply authoritatively reject incoming players outside the pool.

**Independent Test**: From My Team, open "Explore transfers" for a player; `/transfers?out=<id>` shows that player already selected; open a Preview (squad unchanged); Apply updates the squad, backing out changes nothing. A direct Preview or Apply request for a wrong-position, owned or non-selectable player is rejected.

**Depends on**: Phase 3 (T021, T026, T027).

### Tests for User Story 2 (write first, confirm failing)

- [ ] T030 [P] [US2] Extend `apps/api/tests/transfers/test_get_transfer_preview_service.py`: for wrong-position, already-owned, `can_select=False`/`can_transact=False` and unknown-flag incoming players, `execute` returns `TransferPreviewFailure(code="player_not_in_candidate_pool")` and never calls the projection repositories (fakes assert no call), with a refresh-required message for unknown flags; an injured/doubtful/suspended (`status` `i`/`d`/`s`) player with both flags `True` previews normally; the reported reason follows the T014 precedence (a wrong-position or owned player with unknown flags reports the structural exclusion, not `selectability_unknown`).
- [ ] T031 [P] [US2] Extend `apps/api/tests/transfers/test_transfer_preview_router.py`: the new failure surfaces as HTTP 422 with `{code, message, missing_player_ids}` (not 404).
- [ ] T032 [P] [US2] Extend `apps/api/tests/transfers/test_apply_transfer_service.py`: a known non-selectable, unknown-flag, wrong-position or owned incoming player returns `ApplyTransferFailure(code="transfer_illegal", errors=(<reason>,))` before projections and `save_current` is never called; a player eligible at Preview time but now non-selectable is rejected; an eligible non-`a` status player applies when otherwise legal; outgoing players are not subject to the incoming flags; the reported reason follows the T014 precedence (an owned player with a `False` flag reports `player_already_in_squad`).
- [ ] T033 [P] [US2] Extend `apps/api/tests/transfers/test_apply_transfer_router.py`: HTTP 422 with `detail.code == "transfer_illegal"` and `detail.errors` containing the reason, session rolled back, no commit.
- [ ] T034 [P] [US2] Extend `apps/web/tests/transfers/transfer-explorer.test.tsx`: a 422 `player_not_in_candidate_pool` preview shows its message in the existing unavailable state with no Apply button; an illegal preview shows mapped text (for example the budget message) and never the raw code `insufficient_bank`; opening a Preview issues no `PUT /my-team` or apply request.
- [ ] T035 [US2] Extend `apps/web/tests/team/my-team-board.test.tsx` (after T006, same file): every starter and bench card shows an "Explore transfers" link to `/transfers?out=<player_id>` both with and without a selected player.

### Implementation for User Story 2

- [ ] T036 [US2] Add one small API-layer translation module `apps/api/src/api/services/candidate_pool_failures.py` mapping the domain pool reasons (`player_already_in_squad`, `different_position`, `player_not_selectable`, `selectability_unknown`) to failure messages, with a refresh-required message for unknown. It translates the helper's result only and contains no eligibility rules; reused by Preview (T037), Apply (T038) and Explorer (T049). Depends on T021.
- [ ] T037 [US2] In `apps/api/src/api/services/get_transfer_preview.py`, after resolving the outgoing and incoming players and before loading projections or calling `evaluate_single_transfer`, call `candidate_pool_exclusion` (built from the current squad profile and the incoming `CandidatePlayerRecord`, including its flags). A non-`None` result returns `TransferPreviewFailure(code="player_not_in_candidate_pool", message=<from T036>)`. The router already maps non-`player_not_found` failures to 422; no router change. Depends on T021, T026 and T036.
- [ ] T038 [US2] In `apps/api/src/api/services/apply_transfer.py`, read the incoming profile fresh and call the same helper before projections, evaluation or `save_current`; a non-`None` result returns `ApplyTransferFailure(code="transfer_illegal", message=<from T036>, errors=(reason,))` and writes nothing. Do not apply incoming-selectability checks to the outgoing player. Eligibility is checked against the latest imported data, not live FPL. Depends on T021, T026 and T036.
- [ ] T039 [P] [US2] Add `apps/web/src/components/transfers/legality-reasons.ts`: one presentation-only mapping from `insufficient_bank` (insufficient budget), `club_limit_exceeded` (already have 3 players from that club) and `invalid_position_composition` (squad composition constraint) to user-facing text, with a generic fallback so raw codes are never shown. Use it in `apps/web/src/components/transfers/transfer-preview.tsx` in place of `state.data.errors.join(", ")`.
- [ ] T040 [US2] After T029, run `ui-browser-verification` against the actual local frontend and API for quickstart Scenarios 3 and 5: the Explore link preserves `?out=` on starter and bench cards, Preview leaves the saved squad unchanged and backing out changes nothing, and a direct read-only Preview `GET` for a wrong-position or non-selectable player is rejected with a readable 422. Apply a transfer on the real stack only with the human's explicit consent (it changes the saved squad); otherwise Apply is covered by the stubbed Playwright spec (T063). Do not mutate development data to manufacture states. Record observations and anything not verified.

**Checkpoint**: US1 and US2 work independently; Preview and Apply share one authoritative pool rule.

---

## Phase 5: User Story 3 - See replacement candidates even when currently illegal (Priority: P3)

**Goal**: In-pool candidates that fail budget/club/squad constraints stay visible with full comparison data and a readable reason; Preview stays reachable with Apply disabled; playing status is advisory; non-selectable players are absent; unknown selectability yields the explicit refresh-required state.

**Independent Test**: Explore a player with an unaffordable in-pool candidate: it is listed, marked unavailable with a user-facing reason, keeps its resulting bank and 1/3/5-GW gain, opens a Preview with Apply disabled. An injured but selectable candidate is listed with a status label and can be previewed and applied if otherwise legal. A non-selectable, wrong-position or owned player is absent.

**Depends on**: Phase 3 and US2 (T036 translation module, T037/T038 helper wiring, T039 mapping).

### Tests for User Story 3 (write first, confirm failing)

- [ ] T041 [P] [US3] Extend `packages/fpl_engine/tests/test_replacement_ranking.py`: in-pool candidates failing `insufficient_bank` or `club_limit_exceeded` are returned (not dropped) with `is_legal=False`, the matching `errors`, and real `team_gain_by_horizon`, `resulting_bank` (including negative) and `gameweeks_evaluated`; legal and illegal candidates share one sort (descending primary-horizon gain, `player_id` tie-break) and interleave; wrong-position, owned, non-selectable and unknown-flag candidates are excluded via the shared helper.
- [ ] T042 [P] [US3] Extend `apps/api/tests/transfers/test_get_transfer_explorer_service.py` (using the renamed port method `list_by_position`): non-`a` selectable candidates are included with their `status`; non-selectable and wrong-position/owned players are absent; if any profile is unknown after the T014 precedence (it passes the structural and known-non-selectable tiers), `execute` returns `TransferExplorerFailure(code="selectability_unknown")` before projections are loaded rather than an incomplete pool, while structurally excluded or known non-selectable profiles never trigger it; illegal candidates keep all comparison fields; `direct_xpts_difference` keeps its existing `float | None` type with no new nullability.
- [ ] T043 [P] [US3] Extend `apps/api/tests/transfers/test_transfer_explorer_router.py`: candidates serialise `is_legal`, `unavailable_reasons` and `status`; a `selectability_unknown` failure returns HTTP 422 with the structured detail.
- [ ] T044 [US3] Extend `apps/api/tests/transfers/test_get_transfer_preview_service.py` and `test_transfer_preview_router.py` (after T030/T031; same files): the ready result and response carry `player_in_status` for the incoming player; illegal-but-in-pool previews still return `is_legal=false` with errors only for legality reasons, never status.
- [ ] T045 [P] [US3] Add or extend web tests in `apps/web/tests/transfers/transfer-explorer.test.tsx` (and a new `apps/web/tests/transfers/replacement-table.test.tsx` if clearer): an illegal candidate stays listed, visually marked unavailable with the mapped reason, keeps its comparison figures, and its Preview action is enabled; a legal injured candidate shows the advisory status and is applicable; Preview shows `player_in_status` separately from legality messages and Apply is disabled only when `is_legal` is false; an unknown status code renders a generic advisory label and never disables Apply; a 422 `selectability_unknown` Explorer failure shows its refresh message; empty-state copy is accurate now that illegal candidates are included (the existing "no legal candidates" wording needs review).
- [ ] T046 [P] [US3] Add `apps/api/tests/repositories/test_player_read_repository_pool_integration.py` (`pytestmark = requires_database`, `db_session` fixture, `TEST_DATABASE_URL` and the existing `_test` safeguard; never the development database): seed same-position players with statuses `a`, `i`, `d`, `s`, `u`, `n` and varied flag values plus a player of another position; assert `list_by_position` returns the otherwise eligible non-`"a"` players (for example `i`, `d`, `s` with both flags true) and in fact every same-position player regardless of status, excludes the other position, and applies no `status == "a"` SQL filter (eligibility is decided only by the domain helper). This test fails until T051.

### Implementation for User Story 3

- [ ] T047 [US3] Update `rank_replacement_candidates` in `packages/fpl_engine/src/fpl_engine/transfers/replacement_ranking.py`: replace the inline same-position/owned skip with `candidate_pool_exclusion`; stop `break`-ing on an illegal evaluation and stop dropping the candidate; capture `is_legal` and `errors` once per candidate and add `is_legal: bool` and `errors` to `RankedReplacement`; keep one sort across the whole pool. Update the function docstring (it currently says only legal candidates are returned). Existing `direct_xpts_difference` handling stays in the API service. Depends on T021.
- [ ] T048 [US3] Behaviour-preserving rename `list_available_by_position` to `list_by_position` in `apps/api/src/api/repositories/player_read_repository.py`, keeping the `status == "a"` filter for now; update `TransferPlayerRepositoryPort` in `apps/api/src/api/services/get_transfer_explorer.py`, its call site, all fakes and the T019 test. No behaviour change. Depends on T026.
- [ ] T049 [US3] In `apps/api/src/api/services/get_transfer_explorer.py`: call `candidate_pool_exclusion` per same-position profile before loading projections and return `TransferExplorerFailure(code="selectability_unknown", message=<from T036>)` if any profile is unknown after the T014 precedence (structurally excluded and known non-selectable profiles never trigger it); pass `PricedPlayer` flags into the ranker; add `is_legal`, `unavailable_reasons` and `status` to `RankedTransferCandidate`, mapping `is_legal`/`errors` from `RankedReplacement`. A refresh normally resolves the condition; if upstream omits the field the diagnostic intentionally persists. Depends on T036, T047 and T048.
- [ ] T050 [US3] Update `apps/api/src/api/schemas/transfers.py` and the candidate mapping in `apps/api/src/api/routers/my_team.py`: `is_legal: bool` ("`false` means the candidate is visible, fully comparable, but currently unavailable to apply"), `unavailable_reasons: list[str]` ("the same error codes `evaluate_single_transfer` already produces ... empty when `is_legal` is `true`") and `status: str` (advisory only; never an unavailability reason or Apply gate). Existing fields keep their types, including nullable `direct_xpts_difference`. Depends on T049.
- [ ] T051 [US3] Remove the `PlayerModel.status == "a"` filter from `PlayerReadRepository.list_by_position` and fix the `CandidatePlayerRecord` docstring that claims availability is the only filter. Pool membership is now decided only by `candidate_pool_exclusion`, already wired into the ranker and Explorer service by T047 and T049 (this must come after them so the wider pool is never returned unfiltered). Makes T046 pass. Depends on T046, T047, T048 and T049.
- [ ] T052 [US3] Add `player_in_status: str` to `TransferPreviewResult` in `apps/api/src/api/services/get_transfer_preview.py`, to `TransferPreviewResponse` in `apps/api/src/api/schemas/transfer_preview.py`, and to the router response mapping in `apps/api/src/api/routers/my_team.py`, from the incoming profile's `status`. Existing fields are unchanged. Depends on T037 and T044.
- [ ] T053 [P] [US3] Extend types in `apps/web/src/lib/api.ts`: `RankedTransferCandidate` gains `is_legal`, `unavailable_reasons`, `status`; `TransferPreviewResponse` gains `player_in_status`. Do not add nullability to existing fields.
- [ ] T054 [P] [US3] Add `apps/web/src/components/transfers/playing-status.ts`: one presentation-only mapping from FPL status codes (`a`, `d`, `i`, `s`, `u`, `n`) to advisory labels with a generic fallback for unknown codes; contains no legality logic.
- [ ] T055 [US3] Update `apps/web/src/components/transfers/replacement-table.tsx`: render unavailable candidates visually distinct from available ones, show mapped `unavailable_reasons` via `legality-reasons.ts`, show the advisory status via `playing-status.ts`, and keep the "Preview transfer" action enabled for every candidate (only Apply inside Preview is disabled). Depends on T039, T053 and T054.
- [ ] T056 [US3] Update `apps/web/src/components/transfers/transfer-preview.tsx` to show `player_in_status` as advisory information separate from legality messages; Apply stays disabled only when `!state.data.is_legal`. Depends on T039, T053 and T054.
- [ ] T057 [US3] Update `apps/web/src/components/transfers/transfer-explorer.tsx`: show the structured `selectability_unknown` failure through the existing unavailable state, correct the empty-pool copy, and pass the new candidate fields through. Depends on T053.
- [ ] T058 [US3] After T029 and T051, run `ui-browser-verification` against the actual local frontend and API for quickstart Scenarios 4 and 6A, limited to states that refreshed imported data actually contains: a same-position injured/doubtful/suspended player with both flags true appears with an advisory status and can be previewed; `u` non-selectable players are absent and a direct read-only Preview `GET` for one returns 422; an unavailable (for example over-budget) candidate only if the current squad and data naturally produce one. Do not mutate development data to manufacture any state, and do not attempt Scenario 6B states (artificial flag/status combinations, flag flips after Preview, unknown/refresh-required) on the real stack; those are covered by tests T014, T030-T033, T042 and the stubbed Playwright spec. Report which states were and were not observed.

**Checkpoint**: US1-US3 work independently.

---

## Phase 6: User Story 4 - Projected points available but not cluttering My Team (Priority: P4)

**Goal**: All My Team projection figures are hidden by default, revealable and re-hideable, and reset on reload or revisit.

**Independent Test**: Load My Team: no per-player xPts, no 1/3/5-GW cards, no recommended-vs-current panel. Reveal shows all three; hide removes them; reload hides again.

**Depends on**: Setup and US1 (same `my-team-board.tsx` and `squad-player-card.tsx`); not on Phase 3.

### Tests for User Story 4 (write first, confirm failing)

- [ ] T059 [US4] Extend `apps/web/tests/team/my-team-board.test.tsx` (and `recommendation-summary.test.tsx` only if its contract changes): by default there is no per-player "GW xPts", no 1/3/5 GW xPts cards, and no recommendation summary or Current/Recommended toggle; a reveal control shows all three; the same control hides them again; hiding while the Recommended view is active returns to the Current view; unmounting and remounting hides them again; nothing is written to `localStorage`, `sessionStorage` or cookies; the optimiser, gameweek-navigation and "Refresh xPts" controls remain visible while figures are hidden; existing recommendation fallbacks (no squad, 422 unavailable) still render when revealed. Existing tests that assert xPts figures must reveal first.

### Implementation for User Story 4

- [ ] T060 [P] [US4] Add an optional `showProjectedPoints` prop (default `true`) to `apps/web/src/components/team/squad-player-card.tsx` that omits the "GW xPts" line when `false`.
- [ ] T061 [US4] In `apps/web/src/components/team/my-team-board.tsx` add a client-only `pointsRevealed` state (`useState(false)`, not persisted) with a visible reveal/hide control gating the per-player figures (T060), the `projectionCards` aggregate, and `RecommendationSummary` with `RecommendedSquadView`. Hiding resets `viewMode` to `"current"`. The optimiser dropdown, gameweek navigation and "Refresh xPts" stay visible (they are not projected-points figures). Recommendation fetching stays unchanged and never writes the squad. Depends on T060.
- [ ] T062 [US4] After T029, run `ui-browser-verification` against the actual local frontend and API for quickstart Scenario 2 (default hidden, reveal, hide, reload resets) and record observations.

**Checkpoint**: All four user stories are independently functional.

---

## Phase 7: Polish and Cross-Cutting Concerns

- [ ] T063 Add `apps/web/tests/e2e/my-team-ux.spec.ts`, one durable Playwright Test spec with the API stubbed via `page.route` against `http://127.0.0.1:8000` (no dependence on database state). Cover: rearrange (the swap's `PUT /my-team` body carries the stubbed saved `bank` exactly), explore, an unavailable candidate whose Preview keeps Apply disabled, preview and apply of a legal candidate, **and one case where a non-`"a"` (for example injured) but authoritatively selectable player remains explorable, previewable and applicable**. Do not cover every Scenario 6 permutation: artificial flag transitions and unknown/refresh-required combinations stay in the lower-layer tests. `playwright.config.ts` has no `webServer` and none is added; the spec runs against an already-running `make frontend-dev`, and no full-stack harness is created. Depends on T012, T055, T056, T057 and T061.
- [ ] T064 Final real-browser verification against the actual local frontend and API (`make db-up`, `make backend-dev`, `make frontend-dev`) after T029, T013, T040, T058 and T062: walk `specs/001-my-team-ux/quickstart.md` following its rules, covering normal flows and Scenario 6A. Skip Scenario 6B on the real stack (deterministic only) and do not mutate development data. Apply a transfer only with the human's consent. Confirm the quickstart's expected automated coverage list is satisfied and correct `quickstart.md` only if a step is stale. This is separate from the API-stubbed spec in T063; report exactly what was observed and what could not be verified.
- [ ] T065 Run the full gates and record results: `make lint`, `make typecheck`, `make test`, `make test-integration`, and `pnpm --filter web build`.
- [ ] T066 Independent review per `.github/skills/code-review/SKILL.md`: inspect the final `git diff` against spec.md acceptance criteria, architecture boundaries (no pool/lineup rules in `apps/api` or `apps/web` beyond UX pre-filtering and translation), the migration, the removal in T012, saved-bank handling, silent error handling, and unintended scope. Report files changed, decisions, checks run, browser verification performed, known limitations, and anything not verified.

---

## Dependencies and Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **US1 (Phase 2)**: after Setup. Independent of Phase 3, so it is the MVP path and can be implemented and verified before the migration exists.
- **Selectability data path (Phase 3)**: after Setup; blocks US2 and US3 only. It may run in parallel with US1 (different files, except the shared test helpers noted below). Its operational gate T029 sits immediately after the persistence tasks that it needs.
- **US2 (Phase 4)**: after Phase 3.
- **US3 (Phase 5)**: after Phase 3 and US2.
- **US4 (Phase 6)**: after Setup and US1 (shared `my-team-board.tsx`); not dependent on Phase 3.
- **Polish (Phase 7)**: after all desired stories.

```text
Setup -> US1 (MVP) -> US4
Setup -> Selectability -> US2 -> US3
                           all -> Polish
```

### Task-Level Dependencies

- Card API before board work: T007 -> T009 -> T010 -> T011 -> T012 (same file `my-team-board.tsx`, sequential).
- Selectability chain: T020, T022 -> T023; T024 -> T025, T026 -> T027; T024, T025 -> T028; T022, T023, T024, T025 -> T029 (gate).
- Shared helper before consumers: T021 -> T036, T037, T038, T047; T036 -> T037, T038, T049.
- Repository, filter and Explorer eligibility, in order: T026 -> T048 (rename, behaviour preserved) -> T049 (Explorer eligibility via helper) -> T051 (remove status filter, after T047 and T049, test T046).
- Preview file: T037 -> T052 (same file `get_transfer_preview.py`).
- Web: T039 and T053/T054 -> T055, T056; T053 -> T057. `my-team-board.test.tsx` is edited by T006, T035, T059 in that order.
- Real-backend gate: T029 -> T040, T058, T062, T064. T013 (US1) runs on current data and needs T029's migration step only if T024 has already landed.

### Parallel Opportunities

- Phase 2 tests T003-T005 together while T006 proceeds; T007 and T008 together.
- Phase 3 tests T014-T019 together; T020 and T022 together; T025 and T026 after T024.
- US2 tests T030-T034 (distinct files); T039 beside T037/T038.
- US3 tests T041-T043, T045, T046; T053 and T054 together.
- Phase 2 and Phase 3 can be worked in parallel by different people.

### Parallel Example: Phase 3 Tests

```text
Task: "tests/test_candidate_pool.py"               (packages/fpl_engine/tests)
Task: "tests/fpl/test_bootstrap_mapper.py"          (apps/api/tests)
Task: "tests/repositories/test_player_repository_integration.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup, then Phase 2 (US1). Stop and validate: swaps work from the normal My Team view, the saved bank is displayed and preserved, `PUT /my-team` rejects illegal formations, and there is no Edit Team mode or inline Transfer.
2. US1 does not need the selectability work, so it can ship first.

### Incremental Delivery

1. Add Phase 3 + US2: authoritative Preview/Apply boundary and Explore flow.
2. Add US3: visible illegal candidates, advisory status and the refresh-required state (the largest slice; consider splitting domain/API from web if a single review is too large).
3. Add US4: projected-points decluttering.
4. Polish: stubbed Playwright spec, final real-stack verification, gates, independent review.

---

## Notes

- **Resolved: inline Transfer removal (T012)**: the legacy inline Transfer / Replacement Player / Confirm Transfer controls, state and helpers inside Edit Team are removed with the mode (spec FR-007a); the always-visible Explore transfers, then Preview, then Apply flow replaces that path and does not conflict with FR-021.
- **Resolved: `PUT /my-team` scope (T004, T008)**: incoming-selectability enforcement stays out of `PUT /my-team`; it only gains authoritative squad/formation validation. Selectability is enforced on Explorer, Preview and Apply.
- **Resolved: saved bank (T006, T010, T011, T063)**: My Team displays the saved `loadedTeam.bank`, and rearrangement preserves that exact bank; it is never recomputed from current squad prices. Cost remains the computed sum.
- **Resolved: precedence (T014, T021)**: structural exclusion (already owned, then wrong position), then known non-selectable flags, then unknown selectability.
- **Resolved: unknown selectability (T042, T049)**: if any otherwise-relevant candidate profile is unknown, Explorer returns the explicit `selectability_unknown` state rather than an incomplete pool. A refresh normally resolves it; if upstream omits the field, continuing to surface the diagnostic is intentional.
- **Resolved: optimiser (T009, T061)**: direct rearrangement is available only on the actual saved lineup (`optimiseMode === "none"`); optimiser modes are hypothetical and read-only for rearrangement. Optimiser, gameweek and refresh controls may stay visible while projected-point figures are hidden.
- **Resolved: verification split (T029, T040, T058, T063, T064)**: the migration and bootstrap refresh are an operational gate before any real-backend verification. Real-stack checks cover normal flows and states present in refreshed data and never mutate development data. Artificial flag/status combinations, flag transitions after Preview and unknown/refresh-required states are verified only by deterministic tests and the API-stubbed Playwright spec, which includes one non-`"a"` selectable case.
- Eligibility uses the latest imported data, not a live FPL guarantee; the checked-in bootstrap fixture predates the flags, so tests use inline payloads.
- **Known limitation (US1 saves)**: every lineup swap sends the whole squad (players, `bank`, `free_transfers`) from the page's loaded snapshot, so a swap made from a stale page can overwrite a change made elsewhere (for example another tab). Proper protection needs optimistic concurrency/versioning or a narrower mutation endpoint, which is outside this feature; no refetch-before-save workaround is added.
- **Approved behaviour**: after a successful lineup save the viewed gameweek stays selected (covered by a component test).
- **Non-blocking follow-ups (not in this feature)**: a board-level error state when the reload fails after an already-successful save; accessibility polish on the select control (label versus `aria-pressed`, not-a-target conveyed only by opacity, identical consecutive live-region messages); the frontend formation limits duplicating the domain table; and `saveMyTeam` not surfacing array-shaped (422) `detail` bodies.
- Do not commit or push as part of these tasks without the human's instruction.
