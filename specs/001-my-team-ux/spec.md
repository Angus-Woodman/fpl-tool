# Feature Specification: My Team UX and Transfer Exploration

**Feature Branch**: `feature/my-team-ux`

**Created**: 2026-10-12

**Status**: Draft

**Input**: User description: "Improve the My Team experience so that managing the current squad and exploring potential transfers feels direct, intuitive and useful for making FPL decisions. Remove the separate Edit Team mode in favour of direct selection-based rearrangement; reduce default projected-points clutter on My Team; let the user start transfer exploration from a specific squad player while preserving that context; show relevant transfer candidates even when they are currently illegal, with a clear legality reason; and preserve the existing Transfer Preview / explicit apply journey."

## Clarifications

### Session 2026-10-12

- Q: Should direct rearrangement also support reordering bench substitute priority (bench order 1-4) between two bench players, or only starting-XI <-> bench swaps? → A: Also bench-to-bench reordering is in scope (refined below to exclude the bench goalkeeper).
- Q: Which projected-points elements on My Team should be hidden by default? → A: Everything projection-related — per-player figures, the aggregate gameweek summary, and the recommended-vs-current comparison panel.
- Q: Should selecting a player to rearrange the team and starting transfer exploration for a player be the same interaction, or two separate affordances? → A: Separate affordances — exploring transfers remains a distinct, always-visible action per player, independent of rearrangement selection.
- Q: Can a manager open Transfer Preview for a currently-unavailable candidate, or only for a selectable one? → A: Yes — Transfer Preview can be opened for an unavailable candidate; it shows the same unavailability reason there and keeps Apply disabled (matches current Preview behaviour).
- Q: Can the bench goalkeeper be reordered against outfield substitutes, or only outfield substitutes among themselves? → A: Only outfield substitutes can be reordered among themselves (1st/2nd/3rd sub priority); the bench goalkeeper is not part of this reordering.
- Q: Should the candidate pool include other positions or already-owned players? → A: No: keep same-position/not-owned scope; stop dropping in-pool candidates on budget/club/squad-legality grounds. This does not preserve the old playing-status exclusion; the later status clarification below supersedes that interpretation.
- Q: Does revealing projected points stay revealed after a reload or later visit, or reset to hidden each time? → A: The reveal choice only lasts for the current page view; reloading My Team or returning to it later starts hidden again.
- Q: Does playing availability define incoming transfer eligibility? → A: No. Use authoritative FPL selectability/transactability alongside same position and not already owned. Injury, doubt, suspension and other playing statuses are advisory, never automatic transfer-illegality reasons. Selectable players may be explored, previewed and applied if otherwise legal; existing availability/minutes projections remain unchanged. Genuinely non-selectable players have no Preview.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rearrange the starting XI and bench directly (Priority: P1)

A manager viewing My Team wants to swap a starting player with a bench player (or otherwise correct their lineup) without first switching into a separate editing mode. They select the player they want to move, see which of their other players can legally swap into that spot, and select one of those valid targets to complete the swap.

**Why this priority**: This is the core interaction being changed. It replaces the existing "Edit Team" mode and is the most visible behavioural change in the feature; every other story builds on the same squad view.

**Independent Test**: On a page showing a saved squad, select a starting player and confirm that only legal swap targets are indicated as selectable; select one of those targets and confirm the lineup updates immediately to reflect the swap, without ever needing to enter a distinct "edit" mode.

**Acceptance Scenarios**:

1. **Given** a saved squad is displayed on My Team, **When** the manager selects one of their players, **Then** that player is clearly indicated as selected.
2. **Given** a player is selected, **When** the manager views the rest of the squad, **Then** every player who could legally swap into the selected player's spot is clearly identifiable as a valid target, and players who cannot legally swap are not presented as valid targets.
3. **Given** a player is selected, **When** the manager selects a valid target, **Then** the two players swap places and the resulting lineup remains valid under the existing squad/formation rules, and the UI clearly indicates the swap has taken place.
4. **Given** a player is selected, **When** the manager wants to stop without swapping, **Then** there is a clear way to cancel or change the current selection.
5. **Given** the squad view, **When** the manager looks for a way to rearrange their team, **Then** no separate "Edit Team" mode is required to do so.

---

### User Story 2 - Explore and preview a transfer starting from a squad player (Priority: P2)

A manager looking at a specific player on My Team wants to see what replacing that player would look like, without having to re-select who they're replacing once they get to the transfer tools. They move from My Team into transfer exploration for that player, compare replacement candidates, and review a Transfer Preview before anything about their real squad changes.

**Why this priority**: This connects the existing My Team and transfer exploration workflows, which is the second most important behavioural change, and depends on User Story 1's squad view but not on Stories 3-4.

**Independent Test**: From My Team, start exploring transfers for a specific player and confirm the exploration view already shows that player as the one being replaced; choose a candidate, open its Transfer Preview, and confirm the manager's actual squad is unchanged until they explicitly apply the transfer.

**Acceptance Scenarios**:

1. **Given** a squad player on My Team, **When** the manager chooses to explore transfers for that player, **Then** the transfer exploration view opens already showing that player as the one being considered for replacement, without the manager having to re-select them.
2. **Given** the manager is exploring replacements for a squad player, **When** they view the candidate list, **Then** it is clear which existing squad player is being replaced and which candidates are being compared.
3. **Given** a candidate the manager is interested in, **When** they choose to proceed, **Then** they reach a Transfer Preview for that specific candidate before any change is made to their squad.
4. **Given** a Transfer Preview is open, **When** the manager has not explicitly applied it, **Then** their actual squad remains exactly as it was.
5. **Given** a Transfer Preview is open, **When** the manager explicitly applies the transfer, **Then** their squad is updated to reflect it; **When** they instead back out, **Then** no change is made.

---

### User Story 3 - See relevant replacement candidates even when currently illegal (Priority: P3)

While comparing replacement candidates for a squad player, a manager wants to see strong or interesting candidates even if they can't be transferred in right now (for example, due to budget), so they can plan ahead, rather than having those candidates silently disappear from the comparison.

**Why this priority**: This improves the usefulness of the comparison introduced/preserved in Story 2, but is not required for the core rearrangement or exploration journeys to work.

**Independent Test**: Open transfer exploration for a squad player who has at least one candidate within the comparison pool that is not currently affordable or otherwise fails a transfer-legality constraint, and confirm that candidate remains visible, clearly marked as unavailable, with a reason, and can still be opened in Transfer Preview there, though not applied while it remains unavailable; separately confirm a player of a different position, or already in the manager's squad, does not appear in the comparison at all.

**Acceptance Scenarios**:

1. **Given** a candidate within the comparison pool that currently fails a transfer-legality constraint, **When** the manager views the candidate comparison, **Then** that candidate is still visible rather than omitted.
2. **Given** such a candidate, **When** the manager looks at it, **Then** it is clearly and visually distinguished as currently unavailable, as opposed to a candidate that is currently available to apply.
3. **Given** such a candidate, **When** the manager opens its Transfer Preview, **Then** the preview opens normally, shows the reason it is currently unavailable, and keeps applying disabled, so the manager cannot apply it while it remains unavailable.
4. **Given** a candidate that is currently available, **When** the manager views the comparison, **Then** it is clearly distinguishable from the unavailable candidates, and can be opened in Transfer Preview and applied there.
5. **Given** a player of a different position than the outgoing player, already owned, or genuinely non-selectable in FPL, **When** the manager views the candidate comparison or directly requests a Preview, **Then** that player is outside the pool and has no Transfer Preview.
6. **Given** a same-position, not-owned player whom FPL permits selecting despite injury, doubt, suspension or another playing status, **When** the manager explores and previews that player, **Then** relevant advisory status is visible, the existing availability-adjusted projections are retained, and Apply is allowed if all transfer-legality constraints pass.
7. **Given** an eligible player has been previewed but becomes non-selectable in the latest imported data, **When** the manager attempts Apply, **Then** no squad change occurs.
8. **Given** incoming selectability cannot be established from imported FPL data, **When** the manager explores or directly requests Preview/Apply, **Then** the product explicitly explains that a data refresh is required rather than inferring eligibility from playing status or applying the transfer.

---

### User Story 4 - Projected points available but not cluttering My Team (Priority: P4)

A manager opening My Team wants a clean view of their squad first, with detailed projected-points figures available on request rather than shown everywhere by default.

**Why this priority**: This is a visual decluttering improvement. It makes the squad view introduced/changed in Story 1 easier to read but does not change any underlying capability, so it delivers value independently and can be the last story implemented.

**Independent Test**: Load My Team and confirm projected-points figures on the squad view are not shown by default, then use the provided control to reveal them and confirm they become visible.

**Acceptance Scenarios**:

1. **Given** the manager opens My Team, **When** the squad view first renders, **Then** projected-points figures on that view are hidden by default.
2. **Given** projected points are hidden, **When** the manager uses the provided control to reveal them, **Then** the projected-points figures become visible.
3. **Given** projected points have been revealed, **When** the manager wants the clean view back, **Then** there is a clear way to hide them again.
4. **Given** projected points have been revealed, **When** the manager reloads My Team or returns to it on a later visit, **Then** projected points are hidden again by default.

---

### Edge Cases

- What happens when a selected player has no legal swap targets at all (for example, an unusual squad shape)? The selection should still be clearly indicated, and the manager should be able to tell that no valid targets are currently available rather than it appearing broken.
- What happens if the manager selects a second player who is not a valid target for the first selection? The interaction must not perform an invalid swap; reasonable behaviour is to treat the new selection as replacing the previous one (see Assumptions).
- What happens if a manager starts rearranging their team, then navigates away (for example, into transfer exploration) before completing a swap? The in-progress selection should not be left in a confusing or partially-applied state.
- What happens if a transfer candidate is unavailable for more than one reason at once (for example, both over budget and from a club already at its limit)? The manager must still be given at least one clear, accurate reason; it is acceptable to show more than one.
- What happens if a previously-available candidate becomes unavailable (or vice versa) between opening exploration and reaching Transfer Preview (for example, because budget assumptions change)? Transfer Preview must reflect current legality and must not let the manager apply a transfer that is not actually legal.
- What happens on a squad that has no saved team yet, or where projections are unavailable? Existing current-product fallback behaviour for these states is unaffected by this feature.
- What happens when upstream selectability is missing, or changes after Preview? Unknown eligibility is surfaced as a refresh-required condition; Apply rechecks the latest imported data and never buys a known non-selectable or unknown incoming player. An owned outgoing player can still be sold even if no longer selectable as an incoming player.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: My Team MUST allow a manager to select one of their squad players directly from the normal squad view, without entering a separate editing mode.
- **FR-002**: My Team MUST clearly indicate which player is currently selected.
- **FR-003**: While a player is selected, My Team MUST clearly identify every other squad player who could legally swap into the selected player's spot as a valid target, and MUST NOT present players who cannot legally swap as valid targets.
- **FR-004**: Selecting a valid target MUST perform the swap and MUST result in a lineup that remains valid under the existing squad/formation rules.
- **FR-004a**: Direct rearrangement MUST support swapping a starting player with a bench player, and MUST also support reordering substitute priority (1st/2nd/3rd sub) between two outfield bench players using the same select-and-target interaction. The bench goalkeeper slot is not reorderable against outfield substitutes.
- **FR-005**: My Team MUST clearly indicate when a swap has taken place.
- **FR-006**: My Team MUST provide a clear way to cancel or change the current selection without performing a swap.
- **FR-007**: My Team MUST NOT require a distinct "Edit Team" mode for a manager to rearrange their starting XI and bench.
- **FR-008**: The My Team squad view MUST hide all projected-points information by default, including the per-player projected-points value shown on each squad card, the aggregate gameweek projection summary (the 1/3/5-gameweek totals), and the recommended-vs-current comparison panel.
- **FR-009**: The My Team squad view MUST provide a simple, clearly visible way for the manager to reveal projected-points information, and to hide it again. The reveal choice applies only to the current page view; reloading My Team or returning to it on a later visit MUST show projected points hidden by default again.
- **FR-010**: My Team MUST provide a clear way to start transfer exploration for a specific squad player directly from that player, as a distinct, always-visible action per player that is independent of whether a player is currently selected for rearrangement.
- **FR-011**: When transfer exploration is started from a squad player, the exploration view MUST already show that player as the one being considered for replacement, without requiring the manager to re-select them.
- **FR-012**: The transfer exploration view MUST make clear which squad player is being replaced and which candidates are being compared.
- **FR-013**: The candidate pool consists of same-position, not-already-owned players whose incoming selection/transaction is permitted by authoritative FPL data. Wrong-position, owned and genuinely non-selectable players are outside the pool and MUST NOT appear or have Transfer Preview. Playing availability MUST NOT define pool eligibility. Within the pool, budget, club-limit or other applicable squad-level transfer failures MUST NOT remove candidates from comparison.
- **FR-013a**: Injury, doubt, suspension and other playing statuses MUST be advisory information, not automatic transfer-illegality reasons. Relevant status MUST be visible in candidate comparison and Preview. Otherwise legal, FPL-selectable candidates MUST remain explorable, previewable and applicable regardless of playing status; projections MUST continue using the existing availability/minutes model without a new model or ranking policy.
- **FR-013b**: Missing authoritative incoming eligibility MUST NOT be inferred from playing status. The product MUST surface an explicit refresh-required condition and prevent Preview/Apply until eligibility is established. Apply MUST recheck incoming eligibility against the latest imported data, without imposing incoming-selectability restrictions on selling the outgoing player.
- **FR-014**: The transfer exploration view MUST clearly and visually distinguish pool candidates that can currently be applied as a transfer from pool candidates that cannot; the latter remain selectable to open in Transfer Preview, they just cannot be applied there while unavailable.
- **FR-015**: A pool candidate that currently fails an applicable transfer-legality constraint (budget, the three-players-per-club limit, or another squad-level constraint) MUST NOT be applied as a transfer. A manager MAY still open a Transfer Preview for such a candidate; that preview MUST explain why the transfer is currently unavailable and MUST keep applying disabled for as long as the transfer remains illegal.
- **FR-016**: For each pool candidate that currently fails a transfer-legality constraint, both the transfer exploration view and its Transfer Preview MUST communicate the specific reason (for example, insufficient budget, the three-players-per-club limit, or another applicable squad-composition constraint), drawn from the application's existing legality rules.
- **FR-017**: Choosing any candidate within the pool MUST lead to a Transfer Preview for that specific candidate before any change is made to the manager's squad, regardless of whether the candidate currently passes all transfer-legality constraints. Players outside the pool are not choosable and have no Transfer Preview.
- **FR-018**: Exploring or selecting a candidate MUST NOT itself change the manager's saved squad.
- **FR-019**: The manager MUST be able to review a Transfer Preview and back out of it without any change being made to their squad.
- **FR-020**: The manager MUST be able to explicitly apply a previewed transfer, at which point their squad is updated to reflect it.
- **FR-021**: Existing My Team, transfer exploration, and Transfer Preview behaviour not addressed by this specification MUST remain unchanged.

### Key Entities

- **Squad Player**: A player currently in the manager's 15-player squad, including whether they are in the starting XI or on the bench, and their bench order if applicable.
- **Selection**: The manager's current choice of squad player to rearrange, and the set of other squad players that are currently valid swap targets for that choice.
- **Replacement Candidate**: A player being compared as a possible replacement for a specific outgoing squad player, including whether the candidate can currently be legally transferred in and, if not, why.
- **Transfer Preview**: A preview of the outcome of replacing one specific squad player with one specific candidate, reviewed by the manager before it is applied.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A manager can rearrange their starting XI and bench (select a player, see valid targets, select a target) entirely from the normal My Team view, with no separate mode to enter or leave.
- **SC-002**: When a swap is legal, completing it takes exactly two player selections (the player to move, then the target), and an illegal target is never available to select by mistake.
- **SC-003**: On first opening My Team, a manager does not see detailed projected-points figures until they choose to reveal them, and can hide them again just as easily.
- **SC-004**: A manager can go from looking at a specific squad player on My Team to a Transfer Preview for a chosen replacement without ever having to re-specify which player they are replacing.
- **SC-005**: When comparing replacements for a squad player, a manager can see every relevant candidate worth comparing, including ones they cannot currently transfer in, and can always tell why an unavailable one is unavailable.
- **SC-006**: A manager's saved squad only ever changes when they explicitly apply a transfer or a lineup swap; exploring, comparing, or previewing never changes it on its own.

## Assumptions

- Direct rearrangement (Story 1) applies to the manager's actual, editable squad view. It does not apply to any read-only "recommended" comparison view the product already offers; that view continues to be for comparison only.
- When a starting player who is captain or vice-captain is moved to the bench via a swap, captaincy/vice-captaincy follows the existing product's current behaviour (it transfers to the player taking their starting spot). This feature does not change captaincy/vice-captaincy rules.
- If a manager selects a new player while another selection is already active and the new selection is not a valid target for the first, the new selection replaces the previous one (effectively cancelling the first selection) rather than the interaction being blocked or erroring.
- Wrong-position, owned and genuinely non-selectable players are outside the pool, not visible-but-illegal candidates. Playing status is advisory; the existing transfer evaluator still owns budget/club/squad legality and the existing model owns availability-adjusted projections. Eligibility uses the latest imported FPL data, not a live upstream transaction guarantee.
- Starting transfer exploration for a player (Story 2) is a distinct, always-visible action on each squad player, independent of the swap-selection interaction from Story 1; selecting a player to rearrange the team does not itself offer transfer exploration as an option.
