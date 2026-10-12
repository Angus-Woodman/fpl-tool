---

description: "Task list for My Team UX and Transfer Exploration"
---

# Tasks: My Team UX and Transfer Exploration

**Input**: Design documents from `/specs/001-my-team-ux/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED. The constitution (Principles IV, V, VI, VII) and `quickstart.md` require tests at the layer that owns each behaviour, browser verification, and durable Playwright coverage. Within each phase, write tests first and confirm they fail before implementing.

**Organization**: Grouped by user story (US1-US4 from spec.md). Phase 2 is the imported-selectability data path and domain pool helper; it blocks US2 and US3 only. US1 and US4 do not depend on it.

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

- [ ] T001 Confirm the working tree is on `feature/my-team-ux` and clean, then run `make lint && make typecheck && make test` and record any pre-existing failures before changing code.
- [ ] T002 Run `make test-integration` (it uses only the dedicated `fpl_test` database via `TEST_DATABASE_URL`; never run integration tests against the development database, never bypass `ensure_test_database_url`) and record the baseline.

---

## Phase 2: Foundational - Imported Selectability and Shared Pool Helper (blocks US2 and US3)

**Purpose**: Carry FPL's `can_select` / `can_transact` through import and persistence and define the single domain pool-eligibility rule (research.md decisions 4 and 10; data-model.md "Imported Player Selectability" and "Candidate pool eligibility"). No user-visible behaviour changes in this phase. The repository's `status == "a"` filter is deliberately left in place until US3 rewires the Explorer.

**CRITICAL**: US2 and US3 cannot start until this phase is complete. US1 and US4 may run in parallel with it.

### Tests for Foundational work (write first, confirm failing)

- [ ] T003 [P] Add `packages/fpl_engine/tests/test_candidate_pool.py` for the new helper `candidate_pool_exclusion(squad, player_out_id, candidate) -> reason | None`. Cover: `None` when same position, not owned, `can_select is True` and `can_transact is True`; `player_already_in_squad`; `different_position`; `player_not_selectable` when either flag is `False`; `selectability_unknown` when either flag is `None` and neither is `False`; a known `False` flag wins over a missing other flag (data-model.md: "A known false flag excludes the player even if the other flag is missing"); exclusion precedence is fixed as (1) structural (already owned / wrong position), then (2) known non-selectable (either flag `False`), then (3) unknown selectability, so an owned or wrong-position player with `can_select=False` or unknown flags reports the structural reason, and a `False` flag beside an unknown one reports `player_not_selectable`. Within the structural tier, report `player_already_in_squad` before `different_position` and test that order. Include a test that `can_transact=True` with `can_select=False` is excluded (live data: 105 such players with status `u`) and that no `status` value changes the result.
- [ ] T004 [P] Extend `packages/fpl_engine/tests/test_entities.py`: `Player` accepts `can_select` and `can_transact` as optional (default `None`) without breaking existing constructor calls.
- [ ] T005 [P] Extend `apps/api/tests/fpl/test_bootstrap_schemas.py` and `apps/api/tests/fpl/test_bootstrap_mapper.py` using inline payloads (do not edit the captured `data/fixtures/fpl/bootstrap_static.json`): flags parse as `True`, `False` and absent (`None`); mapper carries them into `PlayerSeed`; flags are independent of `status` (e.g. `status="a"` with `can_select=False`; `status="i"` with both `True`).
- [ ] T006 [P] Extend `apps/api/tests/services/test_import_fpl_data_service.py`: the `Player` objects passed to the player repository carry `can_select` / `can_transact` unchanged, including `None`.
- [ ] T007 [P] Add `apps/api/tests/repositories/test_player_repository_integration.py` (`pytestmark = requires_database`, `db_session` fixture, pattern from `test_team_repository_integration.py`): `upsert_many` persists `True`, `False` and `None`; re-importing a player whose flags are now absent clears the previously stored value to `None`; independent of `status`.
- [ ] T008 [P] Add `apps/api/tests/repositories/test_player_read_repository_integration.py` (same database guard): `get_by_id` and `list_available_by_position` return `can_select` / `can_transact` on `CandidatePlayerRecord`, and a freshly migrated row (flags never imported) reads as `None`/`None`.

### Implementation for Foundational work

- [ ] T009 [P] Add `can_select: bool | None = None` and `can_transact: bool | None = None` to the domain `Player` in `packages/fpl_engine/src/fpl_engine/domain/entities.py`. Constraint (data-model.md): "nullable in imported/domain/persisted data when absent". `None` means unknown, never eligible.
- [ ] T010 Create `packages/fpl_engine/src/fpl_engine/transfers/candidate_pool.py` implementing `candidate_pool_exclusion` per T003 and export it from `packages/fpl_engine/src/fpl_engine/transfers/__init__.py`. Add optional `can_select` / `can_transact` fields (default `None`) to `PricedPlayer` in `replacement_ranking.py`, avoiding a circular import with that module (for example by defining the profile type where both modules can import it and re-exporting `PricedPlayer` from `fpl_engine.transfers`). Pure function; no FastAPI/SQLAlchemy imports; stable reason codes `player_already_in_squad`, `different_position`, `player_not_selectable`, `selectability_unknown`, evaluated in the precedence defined in T003. `status` is not an input.
- [ ] T011 [P] Add `can_select: bool | None = None` and `can_transact: bool | None = None` to `FplElementDto` in `apps/api/src/api/adapters/fpl/schemas.py` (keep `extra="ignore"`), to `PlayerSeed` in `apps/api/src/api/adapters/fpl/mappers.py`, and map them in `map_bootstrap_static`. Do not default absent flags to `True` and do not derive them from `status`.
- [ ] T012 Pass the flags from `PlayerSeed` into the domain `Player` in `ImportFplDataService.import_bootstrap_static` (`apps/api/src/api/services/import_fpl_data.py`); depends on T009 and T011.
- [ ] T013 Add nullable `can_select` and `can_transact` Boolean columns to `PlayerModel` in `apps/api/src/api/models/entities.py` and write one Alembic migration in `apps/api/alembic/versions/` with `down_revision = "a1c8f3e6d940"` (current head). Add the columns nullable with no server default and no backfill from `status` or any default-true value; downgrade drops them. Author by hand or via `make db-revision m="add_player_selectability_flags"` and review the generated file. Verify only against the test database via `make test-integration` (`db-test-up` runs `alembic upgrade head` on `fpl_test`).
- [ ] T014 Persist the flags in `PlayerRepository.upsert_many` (`apps/api/src/api/repositories/player_repository.py`) in both the insert values and the `on_conflict_do_update` `set_` map taken from `statement.excluded`, so an absent flag overwrites a stale value with `NULL`; depends on T013.
- [ ] T015 Add `can_select` and `can_transact` (`bool | None`) to `CandidatePlayerRecord` and select them in `PlayerReadRepository.get_by_id` and `list_available_by_position` in `apps/api/src/api/repositories/player_read_repository.py`. Leave the `status == "a"` filter untouched here (removed in US3, T044); depends on T013.
- [ ] T016 Update the existing `CandidatePlayerRecord` helper constructors in `apps/api/tests/transfers/test_apply_transfer_service.py`, `test_get_transfer_explorer_service.py` and `test_get_transfer_preview_service.py` to supply explicit flag values (test helper default `True`/`True`), so existing tests keep their meaning.

**Checkpoint**: `make lint`, `make typecheck`, `make test` and `make test-integration` pass; `make test-integration` applies the new migration to `fpl_test`; existing behaviour unchanged.

**Real-backend gate**: once T013 exists, the local database must be migrated (and, for flag-dependent checks, bootstrap-refreshed) via T059 before any manual or browser verification against the real backend (T026, T037, T053, T057, T060). Deterministic automated tests keep using fixtures, fakes and the guarded `fpl_test` database and do not depend on T059.

---

## Phase 3: User Story 1 - Rearrange the starting XI and bench directly (Priority: P1) MVP

**Goal**: Replace Edit Team mode with always-on selection-based swaps (starter/bench and outfield bench priority), authoritative server-side lineup validation.

**Independent Test**: On `/my-team`, select a starter, see only legal bench targets, select one, and the swap saves immediately with no Edit Team mode. A direct `PUT /my-team` with an illegal starting formation returns HTTP 400.

### Tests for User Story 1 (write first, confirm failing)

- [ ] T017 [P] [US1] Extend `packages/fpl_engine/tests/test_rules.py`: a 5-2-3 starting XI (`MID=2`) passes `validate_squad`; a starting XI with 2 goalkeepers fails with code `formation`. This documents why the frontend's `MID >= 3` check cannot be authoritative.
- [ ] T018 [P] [US1] Extend `apps/api/tests/team/test_current_squad_service.py`: saving a starting XI that violates the starting formation (for example 2 GK starting, otherwise valid 15-player squad) raises `ValueError`; a legal 5-2-3 is accepted; existing messages (size, duplicates, unknown players, bench order, captain, composition, club limit) are unchanged; no ownership or selectability rule is introduced on this path (saving still succeeds regardless of any imported `can_select`/`can_transact` value).
- [ ] T019 [P] [US1] Extend `apps/api/tests/team/test_my_team_router.py`: `PUT /my-team` with an illegal starting formation returns 400 with the validation message and does not commit.
- [ ] T020 [US1] Rewrite the Edit Team tests in `apps/web/tests/team/my-team-board.test.tsx` for the new interaction: no "Edit Team"/"Save Changes"/"Cancel" controls; selecting a player marks it selected and marks only legal targets; selecting a valid target performs one `PUT /my-team` with the swap, the loaded `free_transfers`, and the loaded `bank` exactly (see the bank regression below); selecting a non-target replaces the selection without error; the selection can be cancelled (toggle the selected player or a clear control); a selected player with no legal targets shows a "no valid swap targets" message; outfield bench-to-bench reorder swaps `bench_order` only; the bench goalkeeper cannot be reordered against outfield subs; a 5-2-3 swap is offered (regression for `MID >= 3`); swapping a captain/vice starter to the bench moves the badge to the incoming starter; selection is disabled while the optimiser mode is not "None"; a rejected save shows the server message and leaves the displayed squad unchanged. Add a bank regression: load a team whose `bank` (for example `2.3`) deliberately differs from `100 - sum(current_price)` of the squad; after a starter/bench swap and after a bench-to-bench reorder, the `PUT /my-team` body's `bank` equals the loaded `2.3` exactly, with `free_transfers` equal to the loaded value. Remove the old swap-dropdown and inline Transfer tests (see T024) and assert that no inline "Transfer" button or "Replacement Player" control renders and that loading My Team does not request the player pool (only Create Starter Squad does).

### Implementation for User Story 1

- [ ] T021 [US1] Rewire `UpsertCurrentSquadService._validate` in `apps/api/src/api/services/current_squad.py` onto `fpl_engine.rules.validate_squad`: keep the 15-player count, duplicate and unknown-player checks (the lookup is needed first), then build one `SquadSlot` per requested player (`player_id`, `position=PlayerPosition(...)` and `team_id` from `SquadPlayerLookupItem`; `is_starting`, `bench_order`, `is_captain`, `is_vice_captain` from the request) and call `validate_squad`, letting `RuleViolationError` (a `ValueError`) reach the existing router 400 path. Remove the now-duplicated hand-rolled bench/captain/position/club checks. The domain messages are identical to the existing ones, so external behaviour stays the same except that the starting formation is now enforced. Do not add ownership or incoming-selectability checks to `PUT /my-team`; this feature only adds authoritative squad/formation validation there.
- [ ] T022 [US1] In `apps/web/src/components/team/my-team-board.tsx`, replace `EditState`/draft/Edit Team with a `selectedPlayerId: number | null` state that is always active on the current-squad view (and only while `optimiseMode === "none"`, because other modes display a hypothetical lineup, not the real squad). Add `canReorderBench(benchIdA, benchIdB, ...)` beside `canSwapStarterWithBench` (both on the bench, different players, neither the bench goalkeeper). Replace the frontend formation check with bounds mirroring `STARTING_POSITION_LIMITS` in `packages/fpl_engine/src/fpl_engine/rules/squad.py` (GK 1, DEF 3-5, MID **2-5**, FWD 1-3), fixing the incorrect `MID >= 3` in `canSwapStarterWithBench`; comment that this is UX pre-filtering and the server is authoritative. Delete `validateStartingLineup` if unused afterwards.
- [ ] T023 [US1] In `my-team-board.tsx`, implement the swap: selecting a valid target immediately calls `saveMyTeam` with the swapped selections and the currently loaded team's `bank` exactly as returned by `GET /my-team` plus its `free_transfers`; never recompute `bank` from `BUDGET_CAP` or current squad prices (the previous save did), then reloads via `loadMyTeam`. Starter/bench swap keeps the existing captain/vice transfer to the incoming starter and bench order handover; bench/bench reorder swaps only `bench_order`. Show a clear confirmation of the swap (`aria-live` text naming both players), disable selection while saving, and on failure show the error and restore the pre-swap view. Selecting a non-target replaces the selection (spec Assumptions); no navigation guard needed because selection is ephemeral component state.
- [ ] T024 [US1] Remove the Edit Team-only flows from `my-team-board.tsx` that cannot exist without the mode: header Edit/Save/Cancel buttons, `handleStartEditing`/`handleCancelEditing`/`handleSaveChanges`, the swap dropdown (`swapTargetStarterId`, `swapChoiceBenchId`, `eligibleBenchOptionsForStarter`, `applyStarterBenchSwap`) and `renderEditControls`, and the entire legacy inline per-player "Transfer" path: the "Transfer" button, the "Replacement Player" dropdown and "Confirm Transfer", state (`transferPlayerPool`, `transferTargetPlayerId`, `transferChoicePlayerId`, `transferSavingPlayerId`, `transferError`) and helpers (`ensureTransferPlayerPool`, `handleOpenTransfer`, `eligibleTransferOptions`, `handleConfirmTransfer`), plus any imports left unused. Keep `fetchPlayers` only where Create Starter Squad still needs it. The always-visible Explore transfers, then Preview, then Apply flow (FR-010, FR-017) replaces this path; it saved directly via `PUT /my-team`, bypassing Preview.
- [ ] T025 [P] [US1] Update `apps/web/src/components/team/squad-player-card.tsx` with selection visual states (selected, valid target, not a target) and an accessible select control (button with `aria-pressed`, labelled with the player name) while keeping the "Explore transfers" link a separate, always-visible element that does not trigger selection. Adjust `apps/web/src/components/team/bench.tsx` / `squad-pitch.tsx` only if needed to pass state through. `RecommendedSquadView` stays read-only and unchanged.
- [ ] T026 [US1] Once T013 exists, complete T059 first (the ORM model then expects the new columns); then run `ui-browser-verification` for quickstart Scenario 1 against the actual local frontend and API (`make db-up`, `make backend-dev`, `make frontend-dev`), checking that a swap leaves the displayed bank unchanged after reload: select, valid-target marking, swap, cancel, replacement of selection, no-target case, bench reorder, bench GK exclusion, captain badge effect, error state, and no Edit Team control. Record what was observed and what could not be verified (including the direct `PUT /my-team` HTTP 400 check).

**Checkpoint**: US1 is fully functional and independently verifiable without US2-US4.

---

## Phase 4: User Story 2 - Explore and preview a transfer starting from a squad player (Priority: P2)

**Goal**: Exploration starts from a specific squad player with context preserved; every in-pool selection reaches Preview before mutation; Preview and Apply authoritatively reject incoming players outside the pool.

**Independent Test**: From My Team, open "Explore transfers" for a player; `/transfers?out=<id>` shows that player already selected; open a Preview (squad unchanged); Apply updates the squad, backing out changes nothing. A direct Preview or Apply request for a wrong-position, owned or non-selectable player is rejected.

**Depends on**: Phase 2.

### Tests for User Story 2 (write first, confirm failing)

- [ ] T027 [P] [US2] Extend `apps/api/tests/transfers/test_get_transfer_preview_service.py`: for wrong-position, already-owned, `can_select=False`/`can_transact=False` and unknown-flag incoming players, `execute` returns `TransferPreviewFailure(code="player_not_in_candidate_pool")` and never calls the projection repositories (fakes assert no call), with a refresh-required message for unknown flags; an injured/doubtful/suspended (`status` `i`/`d`/`s`) player with both flags `True` previews normally; the reported reason follows the T003 precedence (a wrong-position or owned player with unknown flags reports the structural exclusion, not `selectability_unknown`).
- [ ] T028 [P] [US2] Extend `apps/api/tests/transfers/test_transfer_preview_router.py`: the new failure surfaces as HTTP 422 with `{code, message, missing_player_ids}` (not 404).
- [ ] T029 [P] [US2] Extend `apps/api/tests/transfers/test_apply_transfer_service.py`: a known non-selectable, unknown-flag, wrong-position or owned incoming player returns `ApplyTransferFailure(code="transfer_illegal", errors=(<reason>,))` before projections and `save_current` is never called; a player that was eligible at Preview time but is now non-selectable is rejected; an eligible non-`a` status player applies when otherwise legal; outgoing players are not subject to the incoming flags; the reported reason follows the T003 precedence (an owned player with a `False` flag reports `player_already_in_squad`).
- [ ] T030 [P] [US2] Extend `apps/api/tests/transfers/test_apply_transfer_router.py`: HTTP 422 with `detail.code == "transfer_illegal"` and `detail.errors` containing the reason, session rolled back, no commit.
- [ ] T031 [P] [US2] Extend `apps/web/tests/transfers/transfer-explorer.test.tsx`: a 422 `player_not_in_candidate_pool` preview shows its message in the existing unavailable state with no Apply button; an illegal preview shows mapped text (for example budget message) and never the raw code `insufficient_bank`; opening a Preview issues no `PUT /my-team` or apply request.
- [ ] T032 [P] [US2] Extend `apps/web/tests/team/my-team-board.test.tsx`: every starter and bench card shows an "Explore transfers" link to `/transfers?out=<player_id>` both with and without a selected player.

### Implementation for User Story 2

- [ ] T033 [US2] Add one small API-layer translation module (for example `apps/api/src/api/services/candidate_pool_failures.py`) mapping the domain pool reasons (`player_already_in_squad`, `different_position`, `player_not_selectable`, `selectability_unknown`) to failure messages, with a refresh-required message for unknown. It translates the helper's result only and contains no eligibility rules; reused by Explorer, Preview and Apply (T034, T035, T045).
- [ ] T034 [US2] In `apps/api/src/api/services/get_transfer_preview.py`, after resolving the outgoing and incoming players and before loading projections or calling `evaluate_single_transfer`, call `candidate_pool_exclusion` (built from the current squad profile and the incoming `CandidatePlayerRecord`, including its flags). A non-`None` result returns `TransferPreviewFailure(code="player_not_in_candidate_pool", message=...)`. The router already maps non-`player_not_found` failures to 422; no router change.
- [ ] T035 [US2] In `apps/api/src/api/services/apply_transfer.py`, read the incoming profile fresh and call the same helper before projections, evaluation or `save_current`; a non-`None` result returns `ApplyTransferFailure(code="transfer_illegal", message=..., errors=(reason,))` and writes nothing. Do not apply incoming-selectability checks to the outgoing player. Eligibility is checked against the latest imported data, not live FPL.
- [ ] T036 [P] [US2] Add `apps/web/src/components/transfers/legality-reasons.ts`: one presentation-only mapping from `insufficient_bank` (insufficient budget), `club_limit_exceeded` (already have 3 players from that club) and `invalid_position_composition` (squad composition constraint) to user-facing text, with a generic fallback so raw codes are never shown. Use it in `apps/web/src/components/transfers/transfer-preview.tsx` in place of `state.data.errors.join(", ")`.
- [ ] T037 [US2] After T059, run `ui-browser-verification` against the actual local frontend and API for quickstart Scenarios 3 and 5: Explore link preserves `?out=`, Preview leaves the squad unchanged, Apply updates it, backing out does not, and an out-of-pool Preview request is rejected with a readable message. Record observations and anything not verified.

**Checkpoint**: US1 and US2 work independently; Preview and Apply share one authoritative pool rule.

---

## Phase 5: User Story 3 - See replacement candidates even when currently illegal (Priority: P3)

**Goal**: In-pool candidates that fail budget/club/squad constraints stay visible with full comparison data and a readable reason; Preview stays reachable with Apply disabled; playing status is advisory; non-selectable players are absent.

**Independent Test**: Explore a player with an unaffordable in-pool candidate: it is listed, marked unavailable with a user-facing reason, keeps its resulting bank and 1/3/5-GW gain, opens a Preview with Apply disabled. An injured but selectable candidate is listed with a status label and can be previewed and applied if otherwise legal. A non-selectable, wrong-position or owned player is absent.

**Depends on**: Phase 2 and US2 (shared helper wiring and mapping modules).

### Tests for User Story 3 (write first, confirm failing)

- [ ] T038 [P] [US3] Extend `packages/fpl_engine/tests/test_replacement_ranking.py`: in-pool candidates failing `insufficient_bank` or `club_limit_exceeded` are returned (not dropped) with `is_legal=False`, the matching `errors`, and real `team_gain_by_horizon`, `resulting_bank` (including negative) and `gameweeks_evaluated`; legal and illegal candidates share one sort (descending primary-horizon gain, `player_id` tie-break) and interleave; wrong-position, owned, non-selectable and unknown-flag candidates are excluded via the shared helper.
- [ ] T039 [P] [US3] Extend `apps/api/tests/transfers/test_get_transfer_explorer_service.py`: no status filter is applied (the fake repository exposes `list_by_position`); non-`a` selectable candidates are included with their `status`; non-selectable and wrong-position/owned players are absent; only profiles that pass the structural and known-non-selectable tiers of the T003 precedence yet have unknown flags return `TransferExplorerFailure(code="selectability_unknown")` before projections are loaded (structurally excluded or known non-selectable profiles never trigger it); illegal candidates keep all comparison fields; `direct_xpts_difference` keeps its existing `float | None` type with no new nullability.
- [ ] T040 [P] [US3] Extend `apps/api/tests/transfers/test_transfer_explorer_router.py`: candidates serialise `is_legal`, `unavailable_reasons` and `status`; a `selectability_unknown` failure returns HTTP 422 with the structured detail.
- [ ] T041 [US3] Extend `apps/api/tests/transfers/test_get_transfer_preview_service.py` and `test_transfer_preview_router.py` (after T027/T028; same files): the ready result and response carry `player_in_status` for the incoming player; illegal-but-in-pool previews still return `is_legal=false` with errors only for legality reasons, never status.
- [ ] T042 [P] [US3] Add or extend web tests in `apps/web/tests/transfers/transfer-explorer.test.tsx` (and a new `apps/web/tests/transfers/replacement-table.test.tsx` if clearer): an illegal candidate stays listed, visually marked unavailable with the mapped reason, keeps its comparison figures, and its Preview action is enabled; a legal injured candidate shows the advisory status and is applicable; Preview shows `player_in_status` separately from legality messages and Apply is disabled only when `is_legal` is false; an unknown status code renders a generic advisory label and never disables Apply; a 422 `selectability_unknown` Explorer failure shows its refresh message; empty-state copy is accurate now that illegal candidates are included (the existing "no legal candidates" wording needs review).

### Implementation for User Story 3

- [ ] T043 [US3] Update `rank_replacement_candidates` in `packages/fpl_engine/src/fpl_engine/transfers/replacement_ranking.py`: replace the inline same-position/owned skip with `candidate_pool_exclusion`; stop `break`-ing on an illegal evaluation and stop dropping the candidate; capture `is_legal` and `errors` once per candidate and add `is_legal: bool` and `errors` to `RankedReplacement`; keep one sort across the whole pool. Update the function docstring (it currently says only legal candidates are returned). Existing `direct_xpts_difference` handling stays in the API service.
- [ ] T044 [US3] Rename `list_available_by_position` to `list_by_position` and remove the `PlayerModel.status == "a"` filter in `apps/api/src/api/repositories/player_read_repository.py`; fix the `CandidatePlayerRecord` docstring that claims availability is the only filter; update `TransferPlayerRepositoryPort` and all fakes/call sites (`get_transfer_explorer.py`, tests). Pool membership is now decided only by `candidate_pool_exclusion`.
- [ ] T045 [US3] In `apps/api/src/api/services/get_transfer_explorer.py`: call `candidate_pool_exclusion` per same-position profile before loading projections and return `TransferExplorerFailure(code="selectability_unknown", message=<from T033>)` if any profile is unknown after the T003 precedence (structurally excluded and known non-selectable profiles never trigger it); pass `PricedPlayer` flags into the ranker; add `is_legal`, `unavailable_reasons` and `status` to `RankedTransferCandidate`, mapping `is_legal`/`errors` from `RankedReplacement`.
- [ ] T046 [US3] Update `apps/api/src/api/schemas/transfers.py` and the candidate mapping in `apps/api/src/api/routers/my_team.py`: `is_legal: bool` ("`false` means the candidate is visible, fully comparable, but currently unavailable to apply"), `unavailable_reasons: list[str]` ("the same error codes `evaluate_single_transfer` already produces ... empty when `is_legal` is `true`") and `status: str` (advisory only; never an unavailability reason or Apply gate). Existing fields keep their types, including nullable `direct_xpts_difference`.
- [ ] T047 [US3] Add `player_in_status: str` to `TransferPreviewResult` in `apps/api/src/api/services/get_transfer_preview.py`, to `TransferPreviewResponse` in `apps/api/src/api/schemas/transfer_preview.py`, and to the router response mapping in `apps/api/src/api/routers/my_team.py`, from the incoming profile's `status`. Existing fields are unchanged.
- [ ] T048 [P] [US3] Extend types in `apps/web/src/lib/api.ts`: `RankedTransferCandidate` gains `is_legal`, `unavailable_reasons`, `status`; `TransferPreviewResponse` gains `player_in_status`. Do not add nullability to existing fields.
- [ ] T049 [P] [US3] Add `apps/web/src/components/transfers/playing-status.ts`: one presentation-only mapping from FPL status codes (`a`, `d`, `i`, `s`, `u`, `n`) to advisory labels with a generic fallback for unknown codes; contains no legality logic.
- [ ] T050 [US3] Update `apps/web/src/components/transfers/replacement-table.tsx`: render unavailable candidates visually distinct from available ones, show mapped `unavailable_reasons` via `legality-reasons.ts`, show the advisory status via `playing-status.ts`, and keep the "Preview transfer" action enabled for every candidate (only Apply inside Preview is disabled).
- [ ] T051 [US3] Update `apps/web/src/components/transfers/transfer-preview.tsx` to show `player_in_status` as advisory information separate from legality messages; Apply stays disabled only when `!state.data.is_legal`.
- [ ] T052 [US3] Update `apps/web/src/components/transfers/transfer-explorer.tsx`: show the structured `selectability_unknown` failure through the existing unavailable state, correct the empty-pool copy, and pass the new candidate fields through.
- [ ] T053 [US3] After T059 (migration and bootstrap refresh are prerequisites), run `ui-browser-verification` against the actual local frontend and API for quickstart Scenarios 4 and 6, covering an unavailable candidate, an injured-selectable candidate, non-selectable absence, and the refresh-required state. If T059 cannot be completed, report this verification as not performed rather than substituting stubbed results.

**Checkpoint**: US1-US3 work independently.

---

## Phase 6: User Story 4 - Projected points available but not cluttering My Team (Priority: P4)

**Goal**: All My Team projection information is hidden by default, revealable and re-hideable, and reset on reload or revisit.

**Independent Test**: Load My Team: no per-player xPts, no 1/3/5-GW cards, no recommended-vs-current panel. Reveal shows all three; hide removes them; reload hides again.

**Depends on**: Setup only (touches `my-team-board.tsx`; sequence after US1 to avoid conflicts).

### Tests for User Story 4 (write first, confirm failing)

- [ ] T054 [US4] Extend `apps/web/tests/team/my-team-board.test.tsx` (and `recommendation-summary.test.tsx` only if its contract changes): by default there is no per-player "GW xPts", no 1/3/5 GW xPts cards, and no recommendation summary or Current/Recommended toggle; a reveal control shows all three; the same control hides them again; hiding while the Recommended view is active returns to the Current view; unmounting and remounting hides them again; nothing is written to `localStorage`, `sessionStorage` or cookies; existing recommendation fallbacks (no squad, 422 unavailable) still render when revealed. Existing tests that assert xPts figures must reveal first.

### Implementation for User Story 4

- [ ] T055 [P] [US4] Add an optional `showProjectedPoints` prop (default `true`) to `apps/web/src/components/team/squad-player-card.tsx` that omits the "GW xPts" line when `false`.
- [ ] T056 [US4] In `apps/web/src/components/team/my-team-board.tsx` add a client-only `pointsRevealed` state (`useState(false)`, not persisted) with a visible reveal/hide control gating the per-player figures (T055), the `projectionCards` aggregate, and `RecommendationSummary` with `RecommendedSquadView`. Hiding resets `viewMode` to `"current"`. Keep the gameweek navigation, "Refresh xPts" and the optimiser dropdown visible (controls, not projected-points figures; confirm in Notes). Recommendation fetching stays unchanged and never writes the squad.
- [ ] T057 [US4] After T059, run `ui-browser-verification` against the actual local frontend and API for quickstart Scenario 2 (default hidden, reveal, hide, reload resets) and record observations.

**Checkpoint**: All four user stories are independently functional.

---

## Phase 7: Polish and Cross-Cutting Concerns

- [ ] T058 Add `apps/web/tests/e2e/my-team-ux.spec.ts`, one durable Playwright Test spec for the journey rearrange, explore, view an unavailable candidate (Apply disabled), preview and apply a legal candidate. The API base URL is `http://127.0.0.1:8000`, so stub it deterministically with `page.route` and do not depend on database state. `playwright.config.ts` has no `webServer` and none is added: the spec runs against an already-running `make frontend-dev`, and no full-stack harness is created for this feature. Assert that the swap's `PUT /my-team` body carries the stubbed loaded `bank` exactly. Add only the affected journey; no broader E2E coverage. Real-stack verification is T060, not this spec.
- [ ] T059 Prerequisite for all real-backend manual/browser verification (T026, T037, T053, T057, T060); perform it as soon as T013 exists, not at the end. Human-run or human-confirmed, not performed by the agent without confirmation: apply the migration to the local development database with `make db-migrate` (required as soon as T013 exists, because the ORM model then expects the new columns), and after T011, T012 and T014 are in place run `make data-refresh` so existing rows get `can_select`/`can_transact`. Until the refresh, every player reads as unknown and Explorer returns `selectability_unknown`. These steps are additive and non-destructive; never truncate or reset development data. Automated tests do not depend on this step.
- [ ] T060 Final real-browser verification against the actual local frontend and API (`make db-up`, `make backend-dev`, `make frontend-dev`) after T059: walk through every scenario in `specs/001-my-team-ux/quickstart.md` (Scenarios 1-6) and confirm the expected automated coverage list is satisfied; correct `quickstart.md` only if a step is stale. This is separate from the API-stubbed Playwright spec in T058; report exactly what was observed and what could not be verified.
- [ ] T061 Run the full gates and record results: `make lint`, `make typecheck`, `make test`, `make test-integration`, and `pnpm --filter web build`.
- [ ] T062 Independent review per `.github/skills/code-review/SKILL.md`: inspect the final `git diff` against spec.md acceptance criteria, architecture boundaries (no pool/lineup rules in `apps/api` or `apps/web` beyond UX pre-filtering and translation), the migration, the removal in T024, silent error handling, and unintended scope. Report files changed, decisions, checks run, browser verification performed, known limitations, and anything not verified.

---

## Dependencies and Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: after Setup; blocks US2 and US3 only.
- **US1 (Phase 3)**: after Setup; independent of Phase 2.
- **US2 (Phase 4)**: after Phase 2.
- **US3 (Phase 5)**: after Phase 2 and US2 (T033 translation module, T034/T035 helper wiring, T036 mapping).
- **US4 (Phase 6)**: after Setup; edits `my-team-board.tsx`, so sequence after US1.
- **Real-backend verification gate**: T059 (migration, then bootstrap refresh) must precede every real-backend manual or browser check once T013 exists (T026, T037, T053, T057, T060). T059 sits in Phase 7 only for traceability and may be run as soon as T013 exists (the refresh additionally needs T011, T012 and T014); automated tests and T058 never depend on it.
- **Polish (Phase 7)**: after all desired stories.

```text
Setup -> US1 -> US4
Setup -> Foundational -> US2 -> US3
                 all -> Polish
```

### Within Each Story

- Tests first and failing, then implementation.
- Domain (`packages/fpl_engine`) before API services before schemas/routers before web.
- Same-file tasks are sequential: `my-team-board.tsx` (T022-T024, T056), `get_transfer_preview.py` (T034, T047), `replacement-table.tsx` / `transfer-preview.tsx` / `transfer-explorer.tsx` (T036, T050-T052), `my-team-board.test.tsx` (T020, T032, T054).

### Parallel Opportunities

- Phase 2 tests T003-T008 together; T009 and T011 together; T013 then T014/T015.
- US1 tests T017-T019 together while T020 proceeds separately; T025 parallel with T021.
- US2 tests T027-T032 (distinct files except `my-team-board.test.tsx`, which is T032 only).
- US3 tests T038-T040 and T042; T048 and T049 together.
- US1 and Phase 2 can be worked in parallel by different people.

### Parallel Example: Foundational Tests

```text
Task: "tests/test_candidate_pool.py"               (packages/fpl_engine/tests)
Task: "tests/fpl/test_bootstrap_mapper.py"          (apps/api/tests)
Task: "tests/repositories/test_player_repository_integration.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup, then Phase 3 (US1). Stop and validate: swaps work from the normal My Team view, `PUT /my-team` rejects illegal formations, no Edit Team mode.
2. US1 does not need the selectability work, so it can ship first.

### Incremental Delivery

1. Add Phase 2 + US2: authoritative Preview/Apply boundary and Explore flow.
2. Add US3: visible illegal candidates and advisory status (the largest slice; consider splitting domain/API from web if a single review is too large).
3. Add US4: projected-points decluttering.
4. Polish: Playwright spec, gates, independent review.

---

## Notes

- **Resolved (T024)**: the legacy inline Transfer controls, state and helpers inside Edit Team are removed with the mode; the always-visible Explore transfers, then Preview, then Apply flow replaces that path.
- **Resolved scope (T021)**: incoming-selectability enforcement stays out of `PUT /my-team`; this feature only adds authoritative squad/formation validation there. Selectability is enforced on Explorer, Preview and Apply only.
- **Behaviour to confirm**: unknown selectability for any relevant candidate makes the whole Explorer return `selectability_unknown` (per the accepted design: no silent omission). Until the dev database is migrated and refreshed (T059), all players are unknown.
- **Resolved precedence (T003, T010)**: structural exclusion (already owned / wrong position), then known non-selectable flags, then unknown selectability. The owned-before-wrong-position order inside the structural tier is a deterministic tie-break, not a product rule.
- **Resolved bank handling (T020, T023, T058)**: lineup and bench rearrangement preserves the currently loaded `bank` exactly; it is never recomputed from current squad prices, with regression coverage in the component test and the stubbed Playwright spec.
- **Projection controls (T056)**: the optimiser dropdown, gameweek navigation and "Refresh xPts" stay visible; FR-008 names per-player figures, aggregate summary and the comparison panel.
- Eligibility uses the latest imported data, not a live FPL guarantee; the checked-in bootstrap fixture predates the flags, so tests use inline payloads.
- Do not commit or push as part of these tasks without the human's instruction.
