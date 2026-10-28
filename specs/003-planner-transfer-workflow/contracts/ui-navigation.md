# UI Navigation and Component Contract

## Addresses

| Page | Address | Parameters |
|---|---|---|
| Explorer, My Team mode (unchanged) | `/transfers` or `/transfers?out={playerId}` | no `plan` parameter |
| Explorer, Planner mode | `/transfers?plan={planId}&gw={n}[&out={playerId}][&h=1\|3\|5][&run={runId}]` | `plan` and `gw` required; `out` optional (selector shown when absent); `h` primary horizon, default 5; `run` pinned projection run |
| Plan page | `/plans/{planId}` | unchanged when opened normally |
| Plan page, on return from the Explorer | `/plans/{planId}?gw={n}[&highlight={playerId}]` | honoured on arrival only; no `gw` means today's default gameweek |

Invalid Planner-mode parameters (non-numeric `plan`, `gw` or `out`) show an explicit invalid-link state; they never fall back to My Team.

## Navigation rules

1. **Planner to Explorer.** Per-player "Explore transfers" (existing `SquadPlayerCard.transferHref`) links to `/transfers?plan&gw&out`. A gameweek-level "Explore transfers for this gameweek" links without `out`. Just before navigation the Planner calls `history.replaceState` on its own entry to `?gw={n}` (no other URL writes) so browser Back restores the gameweek.
2. **Explorer to Planner after a saved confirmation.** Navigate (push) to `/plans/{planId}?gw={n}&highlight={incomingPlayerId}` after the coordinator reports `saved` with an acknowledged revision above the one previewed. A one-shot `sessionStorage` entry (`plannerTransferNotice:{planId}`) carries the message "Transferred X for Y in GW n"; the Planner reads and clears it.
3. **Explorer without confirming.** "Back to plan" and browser Back return to the same plan and gameweek with no change.
4. **Reload and new tab** inside the Explorer restore mode, plan, gameweek, outgoing player, horizon and pinned run from the address.
5. **Departure protection.** While a confirmation is saving or not saved, leaving the Explorer shows the same warning as the Planner (link click, `beforeunload`, Back/Forward guard).

## Planner page changes

- Header row: "Back to plans" (left, existing markup) and "Duplicate Plan" (right), in one flex row inside `PlanBoard` (the server page no longer renders the link; loading, error and missing states still show it).
- Highlight: the incoming player's card gains a visible highlighted state and is scrolled into view once on arrival; reduced-motion respected.
- Confirmation notice region (`role="status"`) shows the one-shot message.

## Explorer (Planner mode) screen contract

Regions, top to bottom:

1. Context banner: "Planner mode", plan name, gameweek, link "Back to plan".
2. Projection badge (existing `ProjectionRunBadge`) plus "newer run available" notice when applicable.
3. Outgoing summary: player, purchase basis (with "Estimated" indicator), market price, selling price, bank before, free transfers and hit before.
4. Horizon selector (1, 3, 5) with the evaluated gameweeks shown, partial coverage flagged, Free Hit limit explained.
5. Preview panel above the table (as in My Team mode): per-gameweek table (saved plan, then a visibly separated "Assumed continuation (no plan decisions)" block), totals (never summed), hit and net, later-gameweek consequences, conflict explanation, and the commit region (wording distinct from preview: "Add to plan GW n").
6. Candidate table: Player, Team, Price, Resulting bank, best-XI gain (1/3/5), Plan impact (selected horizon), fixtures, state chip ("Available", "Unavailable: reasons", "Blocked by GW n planned transfer"), Preview button. Controls: name search, club filter, maximum price, "available to apply only", playing-status filter; sort by gain (1/3/5), price, resulting bank, fixture difficulty; visible, clearable active filters; explicit empty state.

States: loading, empty pool, unavailable data (code-specific messages), invalid transfer (reasons), blocked by later decision, saving, saved, rejected (including prices changed), not saved (Retry same edit, Check save status), conflict (reload and preview again), plan missing, plan awaiting initialisation.

Accessibility and viewports: keyboard operable controls with labels, visible focus, tap targets and layout verified at 1440 and 390 widths, consistent with Planner Foundations.

## Component contract (new)

| Component | Responsibility | Inputs |
|---|---|---|
| `TransferExplorerEntry` | choose mode from `plan` parameter | search params |
| `PlannerTransferExplorer` | state machine, fetching, coordinator interplay, navigation | `planId`, `gameweek`, `out`, `horizon`, `run` |
| `PlannerContextBanner` | mode and context | plan summary |
| `PlannerCandidateTable` | rendering, client-side search, filter, sort of server results (no domain logic) | candidates, horizon, controls state |
| `PlannerTransferPreview` | preview and commit region | preview state, coordinator snapshot |
| `DuplicatePlanButton` | gating, single-flight, navigation, errors | coordinator snapshot, plan id and name |
| `useDepartureGuard` | extracted unsaved-work protection | coordinator |

Client-side only presentation: sorting, filtering and formatting. Legality, money, gains, impact and fixtures are always server values.
