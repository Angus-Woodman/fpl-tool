# Phase 1 Data Model: My Team UX and Transfer Exploration

One Alembic migration retains upstream incoming-selectability flags on the
existing player record. Replacement Candidate gains legality fields and
advisory status; Transfer Preview gains a rejection case and advisory
`player_in_status`. Existing comparison types remain unchanged, including
the existing nullable direct-xPts field. Lineup Legality wires an existing
domain rule into squad save; no new persisted entity or projection model.

## Imported Player Selectability (extended existing player)

| Field | Source / policy |
|---|---|
| `can_select` | upstream boolean; nullable in imported/domain/persisted data when absent |
| `can_transact` | upstream boolean; nullable in imported/domain/persisted data when absent |
| `status` | existing string; advisory presentation and existing projection input only |

Carry flags through `FplElementDto`, `PlayerSeed`, the mapper/import service,
domain `Player`, repository insert/update and `PlayerModel`, then expose
them on `CandidatePlayerRecord` and the ranking `PricedPlayer` profile.
The migration adds nullable boolean columns with unknown existing values;
no status-derived/default-true backfill. Bootstrap refresh populates them;
an absent flag on a later import clears its prior value to unknown. Retrieve
same-position profiles without the old status filter (rename the repository
method to `list_by_position` and update its ports/call sites). No new
historical snapshot fields or projection features. See research decision 10
for the observed live payload and unknown-data policy.

## Squad Player

Existing entity, unchanged. Source: `MyTeamPlayerViewRecord` /
`CurrentSquadPlayerResponse`.

| Field | Notes |
|---|---|
| `player_id` | identity |
| `position` | GK / DEF / MID / FWD |
| `is_starting` | starting XI vs. bench |
| `bench_order` | 1–4 when on the bench, else `null`; the bench goalkeeper and the 3 outfield subs share this field today — FR-004a's reorder only ever swaps it between two non-GK bench players |
| `is_captain` / `is_vice_captain` | unchanged; carried by whichever player occupies the starting slot after a swap, per existing behaviour |

## Lineup Legality (authoritative, domain-owned)

Not a new entity — this documents wiring the squad-save path to the
existing `fpl_engine.rules.SquadSlot` / `validate_squad` (which composes
`validate_squad_composition` + `validate_starting_formation`), which today
is defined but never called from the save path (see
[research.md](./research.md), decision 3).

| Field (`SquadSlot`) | Source on the save request |
|---|---|
| `player_id` | request player id |
| `position` | `PlayerPosition(...)` from the existing `SquadPlayerLookupItem` lookup |
| `team_id` | same lookup |
| `is_starting`, `bench_order`, `is_captain`, `is_vice_captain` | request fields, unchanged |

`UpsertCurrentSquadService._validate` builds one `SquadSlot` per requested
player from data it already fetches, and calls `validate_squad(slots)`
instead of its current hand-rolled checks. `RuleViolationError` maps to the
same external 400 response as today's `ValueError` — no API contract
change, only an internal implementation swap from a duplicate, incomplete
check to the authoritative one (it additionally enforces
`validate_starting_formation`, which nothing checks today). This is the
backend authority that FR-004's "remains valid under the existing
squad/formation rules" relies on; the frontend's selection predicates
(below) are UX-only and never the final word.

## Selection (new, client-only, not persisted)

Represents the manager's in-progress choice while rearranging the team.
Exists only in `apps/web` component state (`my-team-board.tsx`); never sent
to or stored by the backend as such — a completed swap is sent through the
existing `saveMyTeam` request, which is now authoritatively re-validated
server-side (see Lineup Legality above) regardless of what the frontend
predicate believed was valid.

| Field | Notes |
|---|---|
| `selectedPlayerId` | `number \| null` — the squad player currently selected |
| *(derived)* valid target ids | computed per render from `selectedPlayerId` via `canSwapStarterWithBench` (starter ⇄ bench) or `canReorderBench` (bench ⇄ bench); UX pre-filtering only, never itself stored or authoritative |

Selecting a different player replaces the prior selection (per the spec's
Assumptions); there is no server round-trip until a swap is actually
performed.

## Replacement Candidate (extended)

Source: `RankedReplacement` (domain) → `RankedTransferCandidateResponse`
(API) → `RankedTransferCandidate` (frontend type in `lib/api.ts`).

| Field | Status | Notes |
|---|---|---|
| `player_id`, `web_name`, `team_short_name`, `price` | unchanged | the shared domain helper decides same-position/not-owned/authoritatively-selectable pool membership |
| `resulting_bank`, `team_gain_by_horizon`, `direct_xpts_difference`, `gameweeks_evaluated` | **unchanged, still always present** | `evaluate_single_transfer` already computes these for every in-pool candidate regardless of legality (position composition is preserved by same-position swaps); they are **not** made optional (see [research.md](./research.md), decision 1) |
| `is_legal` | **new** | `bool`; `false` means the candidate is visible, fully comparable, but currently unavailable to apply |
| `unavailable_reasons` | **new** | `list[str]`; the same error codes `evaluate_single_transfer` already produces (`insufficient_bank`, `club_limit_exceeded`, and defensively `invalid_position_composition`); empty when `is_legal` is `true` |
| `status` | **new** | imported playing-status string; mapped to advisory text, never an unavailability reason or Apply gate |

Sort order: a single key — descending `team_gain_by_horizon[primary_horizon]`,
`player_id` tie-break — applied across the whole pool, legal and illegal
candidates together (no special-casing; see research.md, decision 2).

## Legality reason mapping (shared, presentation-only)

One mapping, used by **both** the candidate comparison's
`unavailable_reasons` and Transfer Preview's `errors` (same code
vocabulary), so the two surfaces can never drift or show raw codes to the
user (see [research.md](./research.md), decision 9):

| Code | Shown as |
|---|---|
| `insufficient_bank` | insufficient budget |
| `club_limit_exceeded` | already have 3 players from that club |
| `invalid_position_composition` | squad composition constraint (defensive; should not normally occur for in-pool candidates since position already matches) |

## Candidate pool eligibility (shared domain helper)

Pool eligibility (same position, not owned, `can_select` and `can_transact`
both explicitly true) is distinct from transfer legality (budget, club limit) and is
expressed **once**, in `packages/fpl_engine`, as a small pure helper (see
[research.md](./research.md), decision 4):

| Input | Output |
|---|---|
| squad, `player_out_id`, candidate profile including nullable flags | `None` if in the pool; otherwise `player_already_in_squad`, `different_position`, `player_not_selectable` (either flag false), or `selectability_unknown` (missing, unless explicitly false) |

Use it in Explorer ranking, early Preview rejection and fresh Apply
validation. Services translate its result, never duplicate its rules.
Playing status is not an input. Explorer surfaces `selectability_unknown`
as an explicit refresh-required failure for otherwise relevant profiles;
Preview uses `player_not_in_candidate_pool` with a refresh-required message;
Apply uses `transfer_illegal` with the exclusion reason and no write. A
known false flag excludes the player even if the other flag is missing.
Only the incoming player is subject to these flags.

One presentation-only playing-status mapping is shared between Explorer
and Preview (separate from legality reasons). Unknown status codes get a
generic advisory label, never a legality failure.

## Transfer Preview

Source: `TransferPreviewResult` / `TransferPreviewResponse`. Response
schema gains `player_in_status: str`; existing fields are unchanged, including `is_legal: bool` and
`errors: tuple[str, ...]` (reusing the same codes above), and the existing
`TransferPreview` component already renders a legality-aware preview with
Apply disabled when illegal for in-pool candidates — this is exactly
FR-015/FR-016's Preview-side behaviour, already in place (its only bug is
displaying `errors` raw instead of through the shared mapping above).

**New rejection case (service-level, not a schema change)**: before
loading projections or evaluating legality, `GetTransferPreviewService`
calls the shared pool-eligibility helper above. A non-`None` result returns
a new `player_not_in_candidate_pool` failure. The router already maps every
failure code other than `player_not_found` to 422 (as it does for
`player_not_in_squad`), so this surfaces as a 422 with `{code, message}` and
the frontend's existing `unavailable` preview state displays the message —
Transfer Preview is unreachable for an out-of-pool player, per
FR-013/FR-017. This check runs *before* — and is distinct from — the
existing legality evaluation, which still produces a normal `ready` preview
(`is_legal=false`, Apply disabled) for in-pool candidates that merely fail
budget, club limit, or another squad-level constraint (see
[research.md](./research.md), decision 4).

## Transfer Apply (eligibility recheck)

The request and success schemas stay unchanged. Before projections or
evaluation, read the current incoming profile and call the same helper;
reject excluded or unknown incoming players via existing `transfer_illegal`
failure/errors, without saving. Eligible injured/doubtful/suspended players
remain applicable when the unchanged transfer evaluator reports legal.
