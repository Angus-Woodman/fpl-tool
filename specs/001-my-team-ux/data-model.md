# Phase 1 Data Model: My Team UX and Transfer Exploration

No database schema changes. All entities below map to existing persisted
records or existing/extended API response shapes; only the "Replacement
Candidate" shape gains new fields.

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

## Selection (new, client-only, not persisted)

Represents the manager's in-progress choice while rearranging the team.
Exists only in `apps/web` component state (`my-team-board.tsx`); never sent
to or stored by the backend.

| Field | Notes |
|---|---|
| `selectedPlayerId` | `number \| null` — the squad player currently selected |
| *(derived)* valid target ids | computed per render from `selectedPlayerId` via `canSwapStarterWithBench` (starter ⇄ bench) or `canReorderBench` (bench ⇄ bench); never itself stored |

Selecting a different player replaces the prior selection (per the spec's
Assumptions); there is no server round-trip until a swap is actually
performed, and swaps are persisted immediately via the existing `saveMyTeam`
call, same as today's Edit Team save.

## Replacement Candidate (extended)

Source: `RankedReplacement` (domain) → `RankedTransferCandidateResponse`
(API) → `RankedTransferCandidate` (frontend type in `lib/api.ts`).

| Field | Status | Notes |
|---|---|---|
| `player_id`, `web_name`, `team_short_name`, `price` | unchanged | pool membership fields (same position, not owned) are already enforced before this stage and never change |
| `resulting_bank`, `team_gain_by_horizon`, `direct_xpts_difference`, `gameweeks_evaluated` | now **optional** | present only when `is_legal` is `true`; a transfer that fails legality has no reliable post-transfer gain to report |
| `is_legal` | **new** | `bool`; `false` means the candidate is visible but currently unavailable |
| `unavailable_reasons` | **new** | `list[str]`; the same error codes `evaluate_single_transfer` already produces (`insufficient_bank`, `club_limit_exceeded`, `invalid_position_composition`); empty when `is_legal` is `true` |

Reason-code → user-facing text mapping (presentation concern, `apps/web`):

| Code | Shown as |
|---|---|
| `insufficient_bank` | insufficient budget |
| `club_limit_exceeded` | already have 3 players from that club |
| `invalid_position_composition` | squad composition constraint (defensive; should not normally occur since the pool is already position-filtered upstream) |

## Transfer Preview

Existing entity, **no schema change**. Source: `TransferPreviewResult` /
`TransferPreviewResponse`. Already carries `is_legal: bool` and
`errors: tuple[str, ...]` (reusing the same codes above), and the existing
`TransferPreview` component already renders a legality-aware preview with
Apply disabled when illegal — this is exactly FR-015/FR-016's Preview-side
behaviour, already in place.
