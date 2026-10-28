# Feature Specification: Planner Foundations

**Feature Branch**: `feature/planner-foundations`

**Created**: 2026-10-14

**Last reconciled**: 2026-10-14 (verified FPL rules and product decisions applied)

**Status**: Draft

**Input**: User description: "Make the Planner's gameweek state and FPL-rule handling trustworthy before adding richer transfer exploration, historical analysis, optimisation, or broader UI redesign. The Planner should let the user establish the relevant starting state for a plan (available free transfers and chips already used in the applicable half of the season), and chip availability, free transfers, transfers made, points hits, bank and squad state should flow correctly from one gameweek to the next under the 2026/27 FPL rules. Editing a gameweek should persist naturally as the user works and navigates between gameweeks, with no explicit 'Save Gameweek' button. The Planner's starting-XI/bench rearrangement should match the direct rearrangement already established on My Team, while FPL squad and formation legality stays authoritative in the domain layer. The specification must explicitly cover Wildcard, Free Hit, Bench Boost and Triple Captain availability and usage across the two chip periods (including a chip planned for a gameweek versus a chip already used before the plan begins), free-transfer accumulation, use, points hits and unlimited-transfer gameweeks. Out of scope: navigating to the Transfer Explorer to make planned transfers; Transfer Explorer filtering/sorting redesign; actual-points-versus-xPts analysis; changes to the xPts model; historical My Team reconstruction; optimal multi-gameweek planning; general page visual redesign."

**Later product decisions folded in**: official purchase and selling-price accounting is in scope; the meaning of the starting free-transfer value; same-gameweek out-and-back transfers are deliberately unsupported; several FPL rules confirmed (see **FPL Rules and Product Constraints**).

Q-1, Q-2, Q-3 and Q-5 are accepted product decisions: reject contradictory chip changes; reject new invalid planning edits while surfacing retryable technical save failures; carry financial/squad state forward but keep lineup choices gameweek-specific; allow completed gameweeks to remain editable. A corrected starting purchase-price provenance is retained even if it exposes financial invalidity in existing saved decisions (Q-7). These decisions are not pending confirmation.

## Background: what the Planner does today

This section describes current, user-visible behaviour (from the existing screens and rules code) so the gaps this feature closes are explicit. It is context, not a requirement.

- A plan is created from the saved My Team squad over a chosen range of gameweeks. Each gameweek holds its own full squad, starting XI, bench order, captain and optional chip.
- The free-transfer count a plan starts with is copied from whatever is saved on My Team. The Planner offers no way to state it.
- The Planner has no concept of chips already used earlier in the season, so a chip the manager has really used can still be planned.
- The Planner accepts any chip in gameweek 1, including Wildcard and Free Hit, and accepts Free Hit in both gameweek 19 and gameweek 20.
- After a Wildcard or Free Hit gameweek the Planner adds the free transfer that arose for the chip gameweek to the bank, which is one more than the confirmed rule (R-07).
- Transfers planned in a plan's first gameweek do not appear to be counted, because the first gameweek is not compared with the starting squad.
- Bank and transfer affordability treat a player's current market price as both what was paid and what they sell for; no purchase price is recorded anywhere.
- A gameweek's edits are held as an unsaved draft until the user presses "Save Gameweek". Moving to another gameweek replaces the draft with the last saved state, so unsaved work is lost without warning.
- Rearranging the starting XI and bench uses a separate dropdown-and-button interaction with its own formation check in the screen, different from the select-and-target rearrangement on My Team.

## Clarifications

### Session 2026-10-14

- Q: May a plan proceed with assumed starting purchase prices, or must the user explicitly confirm them before its finances are treated as valid? (Q-6) → A: Allow planning without confirmation. Use authoritative purchase prices where available; otherwise pre-fill current market price as assumed, with a small per-player "Estimated" indicator and a concise plan-level indication. Calculations depending on an assumed cost basis are provisional. The user may correct or confirm a price later, removing that player's assumption warning without claiming an estimate is authoritative history.
- Q: How should future planned prices and saved transfer finances behave across ordinary FPL data refreshes? (Q-4; resolved directly by the product owner) → A: On creation, save the outgoing player's calculated selling price and incoming player's latest known market/acquisition price. These transaction prices determine carried-forward bank and do not change on ordinary data refresh. Editing or replacing that transfer uses the latest known market prices and appropriate carried-forward purchase-price basis. No predicted movements or user-entered speculative future prices.
- Q: When an upstream purchase-price correction changes the cost basis of an already-saved later sale, how should that dependent transfer be recalculated? (Q-7) → A: Recalculate the dependent selling price using its already-saved market-price assumption and corrected purchase-price basis; keep incoming acquisition prices fixed and do not fetch latest market prices into the decision. Recalculate dependent finances forward. Accept and persist the provenance correction even if it exposes a shortfall, preserving existing transfers. Identify the earliest financially invalid gameweek, the reason and shortfall amount, and mark its dependent financial chain as requiring resolution. Allow repairs and remove resolved downstream invalidity after recalculation. This is distinct from Q-2's rejection of a new invalid planning edit.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Establish a plan's starting state (Priority: P1)

A manager opening a plan can establish, in one place, the starting information the plan cannot infer: free transfers remaining, already-used chips, Free Hit immediately before a plan starting at the chip-period boundary, and each starting player's known or explicitly assumed purchase price. Missing historical prices do not block planning. Every gameweek then reflects that starting state.

**Why this priority**: Every later calculation (free transfers, hits, chip availability, bank) is only as trustworthy as the starting state. Today it cannot be stated.

**Independent Test**: Create a plan starting in gameweek 12 and state 3 free transfers remaining and "Wildcard already used" for the first chip period. The first gameweek shows 3 free transfers, Wildcard is unavailable in gameweeks 12-19 with the reason "used before this plan", and Wildcard is available again from gameweek 20.

**Acceptance Scenarios**:

1. **Given** a new plan starting after gameweek 1, **When** the user views its starting state, **Then** the free transfers remaining default conceptually to 1 and can be set to any whole number from 0 to 5 (R-05, PC-02).
2. **Given** a user who has already used a transfer in the current gameweek, **When** they create a plan, **Then** they can state 0 free transfers remaining, and an ordinary transfer planned in its first gameweek costs a hit, including with Bench Boost or Triple Captain but not with Wildcard or Free Hit.
3. **Given** a plan starting in gameweek 12, **When** the user views its starting state, **Then** they can mark each of the four chips as already used or not used for the chip period that contains gameweek 12.
4. **Given** a plan starting in gameweek 1, **When** the user views its starting state, **Then** no chips can be marked as used (nothing has happened yet) and free transfers are shown as not applicable, because gameweek 1 is unlimited.
5. **Given** a plan starting in gameweek 20, **When** the user views its starting state, **Then** no second-period chips can be marked as used; first-period usage is not requested except whether Free Hit was played in gameweek 19. All four second-period chips are unused, but Free Hit is unavailable in gameweek 20 if it was played in gameweek 19 (R-04).
6. **Given** a plan starting in gameweek 25, **When** the user views its starting state, **Then** they can mark chips as already used for the second chip period only.
7. **Given** an existing plan, **When** the user changes its starting free transfers, used chips or starting-squad purchase prices, **Then** every gameweek in the plan is recalculated immediately and consistently.
8. **Given** a plan with a chip planned in gameweek 14, **When** the user tries to mark that same chip as already used for the same period, **Then** the change is refused with an explanation naming gameweek 14, and nothing changes (Q-1).
9. **Given** the starting squad, **When** the user views the starting state, **Then** every player's purchase price is visible and editable; authoritative prices are used where available and otherwise current market prices are pre-filled as assumed, with a small per-player "Estimated" indicator and a concise plan-level indication (Q-6).
10. **Given** assumed starting purchase prices, **When** the user creates or uses a plan, **Then** no confirmation of all 15 players is required, planning remains available, and dependent financial results are provisional without prominent repeated warnings; correcting or confirming a price later removes that player's assumption warning.

---

### User Story 2 - Plan chips correctly across both chip periods (Priority: P1)

A manager can plan Wildcard, Free Hit, Bench Boost and Triple Captain across the plan's gameweeks, and the Planner only offers a chip where it could really be played. A chip planned for a gameweek and a chip already used before the plan begins are clearly different things, shown differently, and both reduce what is available.

**Why this priority**: Chip use is the highest-stakes planning decision and the easiest to get silently wrong.

**Independent Test**: In a plan spanning gameweeks 17-22 with Free Hit marked already used in the first chip period, plan Wildcard in gameweek 18. Wildcard is then unavailable in 17 and 19 (planned in 18) but available in 20-22; Free Hit is unavailable in 17-19 (used before plan) and available in 20-22; Bench Boost and Triple Captain are available throughout; clearing the planned Wildcard makes it available again in 17-19.

**Acceptance Scenarios**:

1. **Given** a plan with no chips used or planned, **When** the user plans an eligible chip in a gameweek, **Then** that gameweek shows that chip as planned, subject to the gameweek-1 and Free Hit restrictions below.
2. **Given** a chip planned in a gameweek, **When** the user looks at any other gameweek in the same chip period, **Then** that chip is unavailable there with the reason "planned for gameweek N".
3. **Given** a chip marked as already used before the plan, **When** the user looks at any plan gameweek in that chip period, **Then** that chip is unavailable with the reason "used before this plan", visibly distinct from "planned for gameweek N", and it cannot be planned.
4. **Given** a chip planned in the first period, **When** the user looks at a gameweek in the second period, **Then** the same chip is still available there, and vice versa, except for Free Hit in gameweeks 19 and 20 (R-04); first-period chips that are never planned or used simply lapse after gameweek 19 and do not carry over (R-01).
5. **Given** a gameweek that already has one chip planned, **When** the user tries to plan a second chip in that gameweek, **Then** it is refused with an explanation (only one chip per gameweek, R-02).
6. **Given** a plan that includes gameweek 1, **When** the user tries to plan Wildcard or Free Hit in gameweek 1, **Then** it is refused with an explanation, while Bench Boost and Triple Captain can be planned there (R-03).
7. **Given** a plan spanning gameweeks 19 and 20, **When** the user plans Free Hit in gameweek 19 and then in gameweek 20 (or the reverse), **Then** the second is refused with an explanation that Free Hit cannot be played in consecutive gameweeks 19 and 20 (R-04); and **When** the user plans any other chip in both gameweeks, **Then** both are accepted, because they fall in different chip periods.
8. **Given** a plan starting in gameweek 20 where the user states Free Hit was played in gameweek 19, **When** the user looks at gameweek 20, **Then** Free Hit is unavailable there with the reason that it was played in gameweek 19.
9. **Given** a planned chip, **When** the user removes it or moves it to another gameweek, **Then** its availability elsewhere in that period updates immediately.
10. **Given** a request to plan an unavailable chip made directly (not through the screen), **When** it reaches the application, **Then** it is rejected with the same explanation: chip rules are enforced authoritatively, not only by the screen hiding the option.

---

### User Story 3 - Free transfers, transfers, hits and squad flow from gameweek to gameweek (Priority: P1)

As a manager edits gameweeks, the Planner shows, for each gameweek, the free transfers available, the transfers made, any points hit and the squad, and each gameweek's values follow correctly from the previous gameweek's, including across Wildcard and Free Hit gameweeks.

**Why this priority**: The Planner exists to answer "what will this sequence of moves cost and leave me with?". If the carried-forward numbers are wrong, every plan is misleading.

**Independent Test**: Plan gameweeks 8-12 starting with 2 free transfers remaining and no chips. Make 1 transfer in gameweek 8, none in 9, and 4 in 10. Gameweek 8 shows 2 available, gameweek 9 shows 2, gameweek 10 shows 3 with a 4-point hit for the one extra transfer, gameweek 11 shows 1. Plan Wildcard in 11: no hit, and gameweek 12 shows 1 (the free transfer that arose for gameweek 11 was consumed by the chip). If gameweek 11 instead had 3 available with Wildcard planned, gameweek 12 would show 3.

**Acceptance Scenarios**:

1. **Given** an ordinary gameweek after gameweek 1, including Bench Boost or Triple Captain, where fewer transfers are made than free transfers available, **When** the next gameweek is shown, **Then** it has one more free transfer than the unused remainder, never more than five (R-05).
2. **Given** an ordinary gameweek after gameweek 1, including Bench Boost or Triple Captain, where more transfers are made than free transfers available, **When** the gameweek is shown, **Then** it shows a points hit of 4 points for each transfer beyond the free ones (R-06), and the next gameweek has exactly one free transfer.
3. **Given** a gameweek with Wildcard or Free Hit planned and N free transfers available, **When** it is shown, **Then** its transfers are unlimited with no points hit, and the next gameweek has the transfers that were already banked before the chip gameweek (N minus the one that arose for it, never below zero) plus the one arising for the next gameweek, capped at five (R-07).
4. **Given** the plan's first gameweek has Wildcard or Free Hit planned with the starting free transfers at 0, **When** the next gameweek is shown, **Then** it has exactly 1 free transfer (nothing was banked and none was created).
5. **Given** a plan starting in gameweek 1, **When** gameweek 2 is shown, **Then** it has exactly one free transfer regardless of gameweek 1 activity, including Bench Boost or Triple Captain use (R-05; formerly U-01).
6. **Given** a gameweek that follows a Free Hit gameweek, **When** it is shown, **Then** its starting squad and bank are the restored pre-Free-Hit state, not the temporary state; its own transfers and bank changes are then applied against that restored state (R-10; formerly U-02).
7. **Given** a gameweek that follows a Wildcard gameweek, **When** it is shown, **Then** its squad and financial ownership state continue from the Wildcard squad (R-11; formerly U-03).
8. **Given** a transfer planned in the plan's first gameweek, **When** it is shown, **Then** it is counted against the starting squad; outside gameweek 1, Wildcard and Free Hit it consumes the starting free transfers or costs a hit if there are none.
9. **Given** a transfer planned in gameweek N, **When** later gameweeks that still contain the outgoing player are shown, **Then** the incoming player holds that place in them too, except that a Free Hit gameweek's squad does not carry beyond itself.
10. **Given** the user changes anything in an earlier gameweek (starting state, chip, squad), **When** later gameweeks are shown, **Then** every later free-transfer, transfers-made, hit and bank value has been recalculated and none is stale.
11. **Given** a gameweek, **When** it is shown, **Then** the user can see the free transfers available, the transfers made, the points hit, the free transfers carried into the next gameweek and the bank; and the plan shows its total points hit.
12. **Given** Bench Boost or Triple Captain is planned with 3 free transfers available, **When** no transfers are made, **Then** the following gameweek has 4 free transfers; if 1 transfer is made it has 3, and if 4 are made there is a 4-point hit and it has 1. Neither chip consumes the gameweek's arising free transfer merely by being activated.

---

### User Story 4 - Bank and affordability follow the official selling-price rules (Priority: P1)

A manager sees bank and affordability calculated with what each player would actually sell for under FPL rules, not with their current market price, so planned moves are neither falsely affordable nor falsely unaffordable.

**Why this priority**: Using market price for both sides overstates or understates the bank whenever a player's price has changed since purchase, which makes planned transfers misleading.

**Independent Test**: A player bought at £5.0m with a current market price of £5.3m sells for £5.1m, so selling him raises the bank by £5.1m, not £5.3m. A player bought at £5.0m now at £4.8m sells for £4.8m.

**Acceptance Scenarios**:

1. **Given** a player whose market-price assumption for the decision is at or below their purchase price, **When** the Planner calculates their sale, **Then** the selling price equals that market-price assumption (bought £5.0m, assumed market £4.8m, sells £4.8m).
2. **Given** a player whose market-price assumption for the decision is above their purchase price, **When** the Planner calculates their sale, **Then** the selling price is the purchase price plus £0.1m for each complete £0.2m of rise above it (bought £5.0m: assumed market £5.1m sells £5.0m; £5.2m sells £5.1m; £5.3m sells £5.1m; £5.4m sells £5.2m).
3. **Given** a planned sale, **When** it is shown, **Then** the user can inspect latest current market price, saved market-price assumption, purchase-price basis and the selling price actually used, without confusing live information with the saved decision's assumptions.
4. **Given** a player transferred into the planned squad in gameweek N, **When** the Planner later plans their sale, **Then** the price paid for that acquisition is their purchase price, and it carries forward through later gameweeks (except beyond a Free Hit gameweek).
5. **Given** a gameweek with transfers, **When** its bank is shown, **Then** it equals its starting bank plus saved outgoing selling prices minus saved acquisition prices; its starting bank reverts under Free Hit. A new unaffordable planning edit is rejected; an existing saved decision rendered unaffordable by provenance correction is preserved and marked as requiring resolution, not presented as financially valid (Q-7).
6. **Given** a plan, **When** the user looks at how future market prices are treated, **Then** the convention used is stated explicitly (Q-4), and the selling-price rule itself is applied identically whatever the convention.
7. **Given** a starting-squad player whose purchase price is assumed, **When** it is shown or used, **Then** it is never presented as confirmed, dependent financial results remain provisional, and the assumption does not block planning (Q-6).
8. **Given** a saved planned transfer, **When** ordinary FPL data refreshes change current market prices, **Then** its saved outgoing selling price, incoming acquisition price and resulting downstream bank remain unchanged (Q-4).
9. **Given** a saved planned transfer, **When** the user edits or replaces that transfer, **Then** the edited decision uses the latest known market prices and the appropriate carried-forward purchase-price basis, saves its new transaction prices, and recalculates dependent bank balances (Q-4).
10. **Given** a player bought at £5.0m before a Free Hit, **When** the temporary squad replaces them and their genuine market price rises from £5.2m to £5.4m, **Then** the following gameweek restores their original £5.0m cost basis and pre-Free-Hit bank; a newly created sale uses the latest £5.4m market price and sells for £5.2m, while an already-saved sale keeps its saved transaction price (R-10, R-12, Q-4).
11. **Given** a Wildcard acquisition, **When** later gameweeks are shown, **Then** its saved acquisition price becomes the permanent carried-forward cost basis; a Free Hit acquisition does not replace the underlying player's cost basis beyond that Free Hit (R-11, R-12).
12. **Given** a saved sale using assumed purchase £5.0m and saved market £5.4m, **When** purchase provenance is corrected to £4.8m after live market price has moved to £5.6m, **Then** the saved sale is recalculated from £5.2m to £5.1m using the unchanged £5.4m assumption, the incoming acquisition price is unchanged, and dependent bank decreases by £0.1m (Q-7).
13. **Given** that correction makes a previously affordable gameweek £0.1m over budget, **When** it is accepted, **Then** the corrected provenance and unchanged planned transfers are saved; the earliest invalid gameweek shows the reason and £0.1m shortfall, and its dependent financial chain is marked as requiring resolution, even if a later projected bank becomes non-negative.
14. **Given** a plan requiring financial resolution, **When** the user repairs the affected decisions, **Then** finances recalculate forward and resolved invalidity is cleared. Unrelated existing downstream issues do not block an otherwise legal repair, but new invalid planning edits remain rejected under Q-2.
15. **Given** an assumed starting cost basis used during a temporary Free Hit, **When** it is corrected, **Then** dependent temporary selling prices and any post-reversion sales recalculate from their own saved market assumptions, while the restored underlying ownership provenance carries the correction and temporary bank changes still do not carry beyond Free Hit.
16. **Given** an acquisition explicitly edited in an earlier gameweek, **When** its acquisition price changes the cost basis of a later saved sale, **Then** that dependent sale recalculates using its own saved market assumption without repricing its incoming acquisition. The explicit upstream transfer edit still follows Q-2 validation and is rejected if it introduces an unaffordable decision; only starting-price provenance correction has the Q-7 acceptance exception.

---

### User Story 5 - Edits persist as the user works (Priority: P2)

A manager's accepted changes persist automatically, including corrected provenance and any resulting financial-resolution status. Successfully saved work remains available after moving between gameweeks or reopening; pending or failed persistence is surfaced before a departure that would lose work. There is no "Save Gameweek" button. Saved and financially valid are separate states.

**Why this priority**: Losing planning work when switching gameweeks makes the Planner untrustworthy. It builds on the rule handling above, so it follows it.

**Independent Test**: Make a valid change in gameweek 9 (for example change the captain), immediately select gameweek 10, then return to gameweek 9 and reload the page: the change is present each time with no save action taken.

**Acceptance Scenarios**:

1. **Given** an accepted edit, **When** the user takes no further action, **Then** it is saved automatically and the Planner shows a clear but unobtrusive persistence status (saving, saved, or not saved), separate from any financial-resolution status.
2. **Given** an accepted edit still being saved, **When** the user selects another gameweek, **Then** it is not silently lost; a technical failure is surfaced and retryable rather than claimed as saved.
3. **Given** a sequence of rapid accepted edits, **When** they settle and persistence succeeds, **Then** the saved state is the final state, never an intermediate one.
4. **Given** a new planning edit that introduces a rule violation (for example an illegal formation, a chip already used, or an unaffordable squad), **When** it is attempted, **Then** it is rejected and the previous accepted state is retained without the invalid draft. An outstanding technical save failure remains not saved and retryable; an existing Q-7 resolution status is not erased or presented as financially valid (Q-2).
5. **Given** an accepted edit that cannot be saved for a technical reason, **When** the failure occurs, **Then** the user is told, the edit remains visible and marked "not saved", and retrying is possible; a failed save is never silent.
6. **Given** the Planner screen, **When** it is shown, **Then** there is no "Save Gameweek" control.
7. **Given** a successfully saved accepted edit, **When** the page is reloaded or reopened later, **Then** the same latest saved state and any financial-resolution status are shown; an outstanding technical failure is never presented as a successful save.
8. **Given** a provenance correction that leaves the plan requiring financial resolution, **When** automatic persistence succeeds and the plan is reopened, **Then** both the correction and preserved decisions remain, with the financial-resolution status distinct from the saved status (Q-7).

---

### User Story 6 - Rearrange the starting XI and bench the way My Team does (Priority: P3)

A manager rearranges a planned gameweek's starting XI and bench by selecting a player and then selecting a valid target, exactly as on My Team, with FPL squad and formation legality decided by the authoritative rules rather than by the screen alone.

**Why this priority**: Consistency and correctness of an existing interaction. It does not change the numbers the Planner reports, so it is last.

**Independent Test**: In a planned gameweek, select a starter and see only legal bench targets highlighted; select one and the swap happens immediately with a visible confirmation and is saved without any other action; selecting a target that would produce an illegal formation is never offered; a direct request for an illegal lineup is rejected.

**Acceptance Scenarios**:

1. **Given** a planned gameweek, **When** the user selects a starter or bench player, **Then** the selected player is clearly indicated and only players who could legally swap into that spot are marked as valid targets.
2. **Given** a selected player and a valid target, **When** the user selects the target, **Then** the swap happens immediately, a confirmation naming both players is shown, and the change is saved automatically.
3. **Given** a selected player, **When** the user selects a non-target, selects the same player again, or uses a clear control, **Then** the selection is replaced or cancelled without any change to the squad.
4. **Given** two outfield bench players, **When** the user selects one and then the other, **Then** their substitute priority swaps; the bench goalkeeper cannot be reordered against outfield substitutes.
5. **Given** a swap involving the captain or vice-captain, **When** it completes, **Then** captaincy behaves as it does on My Team.
6. **Given** a lineup that would break squad or formation rules, **When** it is requested through any route, **Then** the authoritative rules reject it with the same explanation, and the screen's own pre-filtering of targets is only a convenience.
7. **Given** a Planner gameweek and My Team, **When** the same squad and the same swap are made in each, **Then** the same targets are offered and the same lineup results.
8. **Given** a lineup change (starting XI, bench order, captain or vice-captain) in one gameweek, **When** later gameweeks are shown, **Then** their own lineup choices are unchanged (Q-3).

---

### Edge Cases

- A plan starts in gameweek 1: starting free transfers are not applicable, no chips can be declared used, Wildcard and Free Hit cannot be planned in gameweek 1, and gameweek 2 begins with exactly one free transfer.
- A plan starts in a gameweek after 1 with 0 free transfers remaining: ordinary transfers in the first gameweek are charged a hit, including with Bench Boost or Triple Captain; Wildcard and Free Hit remain hit-free. The next gameweek has exactly one free transfer.
- A plan starts at the first gameweek of the second chip period (gameweek 20): no second-period chips can have been used, and the user can state whether Free Hit was played in gameweek 19. A plan starts in gameweek 19 or earlier: Free Hit planned in 19 makes it unavailable in 20 if the plan reaches 20.
- A plan spans both chip periods: starting-state chip declarations apply only to the period containing the plan's first gameweek (plus the gameweek-19 Free Hit statement for a gameweek-20 start); chips planned in each period are checked per period; the 19/20 Free Hit rule is checked across the boundary.
- A chip planned in a gameweek, then the starting state changed to mark that chip used in the same period, or to state Free Hit was played in gameweek 19 while Free Hit is planned for gameweek 20: refused with an explanation (Q-1).
- Wildcard and Free Hit in the same gameweek, or Bench Boost with Triple Captain in the same gameweek: refused (one chip per gameweek).
- A Wildcard or Free Hit gameweek that is the plan's first gameweek or its last, or a Free Hit immediately before or after a Wildcard: free-transfer, bank, ownership cost basis and squad flow still follow the stated rules. Bench Boost and Triple Captain follow ordinary transfer accounting.
- A gameweek with five free transfers available: Wildcard or Free Hit leaves five available for the next gameweek; an ordinary gameweek, including Bench Boost or Triple Captain, with no transfers leaves five, but transfers use the allowance normally.
- A player transferred out and later bought back within the same gameweek is not supported (PC-01); a player out in one gameweek and back in a later gameweek is two ordinary planned transfers, each counted in its own gameweek.
- A planned transfer in gameweek N, then a later gameweek's own edits that re-add the outgoing player, or two gameweeks that both transfer the same player out: derived transfer counts and hits remain correct and deterministic.
- Selling-price edge: a rise of £0.1m above purchase adds nothing to the selling price; only complete £0.2m steps count; a fall below purchase is taken in full.
- Free Hit temporary transactions use the official selling-price rule and saved transaction-price policy, but do not change the underlying squad's ownership provenance. At the following deadline its original squad, bank and cost basis continue. Genuine market-price changes still affect original players' latest market prices and newly created or edited sales, not the frozen prices of saved transactions (R-09, R-10, R-12, Q-4).
- Purchase prices unavailable from authoritative information are pre-filled at current market price and marked assumed; lightweight indicators and provisional dependent finances do not block plan creation or use. Later confirmation or correction removes the player's assumption warning (FR-032, Q-6).
- A player sold in one gameweek and bought back in a later gameweek acquires a new cost basis at that later decision's saved acquisition price; a Free Hit's temporary buy-back does not reset the underlying cost basis.
- Sequential edits while an automatic save is in flight or after failure MUST preserve the final accepted state, including provenance corrections and financial-resolution status. Concurrent editing in another tab is not specially protected; latest accepted save wins and conflict merging is out of scope (see Assumptions).
- New planning edits are validated across the affected plan. A larger legal points hit is not itself invalid; a newly introduced unaffordable squad or illegal lineup causes rejection with the affected gameweek named (Q-2). A starting purchase-price provenance correction instead remains accepted: recalculate dependent sales with their saved market assumptions, preserve incoming prices and transfer decisions, and mark any exposed shortfall and dependent financial chain for resolution (Q-7).
- Confirmation of an assumed price without changing its value removes the assumption indicator and updates dependent provisional status, but does not reprice transfers. Correcting its value recalculates only the affected cost-basis dependencies, including temporary Free Hit sales and later sales of the restored underlying squad; a genuine later buy-back has its own acquisition basis.
- A corrected sale leaves a gameweek over budget but a later projected bank recovers: the earliest deficit and dependent chain remain requiring resolution until the earlier invalid decision is repaired. Unrelated branches after Free Hit reversion do not inherit temporary bank deficits solely from that temporary squad, but the unresolved Free Hit gameweek remains visible as a plan issue.
- The plan horizon is shortened or lengthened: starting-state declarations remain valid, chips planned outside the new range are discarded exactly as the plan's gameweeks are, and accounting is recalculated.
- Completed gameweeks inside a plan remain editable (Q-5); editing a completed planned transfer uses the latest known prices under Q-4, not reconstructed historical market prices.

## Requirements *(mandatory)*

Rule references use registers defined in **FPL Rules and Product Constraints**: `R-nn` are confirmed FPL rules and `PC-nn` are product constraints. Former U-01 to U-04 assumptions are now confirmed and traced to R-05 and R-10 to R-12. Accepted product decisions retain their `Q-n` references in **Open Clarifications** for traceability, not as requests for reconfirmation.

### Functional Requirements

**Starting state**

- **FR-001**: The Planner MUST let the user state, for a plan, the free transfers remaining at the point they begin the plan, as a whole number from 0 to 5, defaulting conceptually to 1. The value MUST NOT be redefined as the allowance at the opening of a fresh gameweek. For a plan starting in gameweek 1 the value is not applicable and MUST NOT be requested. `[R-05, PC-02]`
- **FR-002**: The Planner MUST let the user state, for each of the four chips, whether it was already used before the plan's first gameweek within the chip period that contains that gameweek. Earlier-period chips MUST NOT be requested or have any effect except for the gameweek-19 Free Hit declaration under FR-003. A gameweek-1 start has no used-chip declarations; a gameweek-20 start has no second-period used-chip declarations but does include FR-003. `[R-01, R-04]`
- **FR-003**: For a plan whose first gameweek is gameweek 20, the Planner MUST let the user state whether Free Hit was played in gameweek 19, and if so MUST treat Free Hit as unavailable in gameweek 20. `[R-04]`
- **FR-004**: The starting state MUST include the starting squad's purchase prices (FR-032), visible from the plan and editable at any time.
- **FR-005**: The starting state MUST be visible from the plan, editable at any time, and treated as an input to every gameweek's calculation.
- **FR-006**: A starting-state change MUST immediately recalculate affected free transfers, transfers made, points hits, chip availability, bank and selling prices across the plan under FR-035. New violations from planning edits MUST be rejected under FR-040. Starting purchase-price provenance corrections MUST instead be accepted under FR-048/FR-049 even if they expose financial invalidity in existing saved decisions; they MUST NOT be rejected to preserve apparent affordability. `[Q-2, Q-7]`
- **FR-007**: A change to the starting state that contradicts an already planned chip (marking a chip as used when the same chip is planned in the same chip period, or stating Free Hit was played in gameweek 19 while Free Hit is planned for gameweek 20) MUST be rejected with an explanation naming the conflicting gameweek, and MUST NOT change the plan or silently clear another decision. `[R-01, R-04, Q-1]`
- **FR-008**: Existing plans MUST remain usable after this feature: retain their free-transfer starting value and start with no chips marked used before the plan. Establish starting purchase-price provenance under FR-032, using authoritative information where already available or visibly assumed current market prices otherwise, without a confirmation gate. Establish missing transaction-price assumptions under FR-035 and identify financial results depending on estimates as provisional; subsequent ordinary refreshes MUST NOT reprice them.

**Chips**

- **FR-009**: The Planner MUST support exactly four chips (Wildcard, Free Hit, Bench Boost, Triple Captain). Each chip MUST be playable at most once in each of the two chip periods (gameweeks 1-19 and 20-38), counting both chips already used before the plan (FR-002) and chips planned in the plan; a first-period chip not used by the end of gameweek 19 lapses and does not carry into the second period. `[R-01]`
- **FR-010**: At most one chip MUST be playable in any single gameweek. `[R-02]`
- **FR-011**: Wildcard and Free Hit MUST NOT be plannable in gameweek 1; Bench Boost and Triple Captain MAY be. `[R-03]`
- **FR-012**: Free Hit MUST NOT be plannable in both gameweek 19 and gameweek 20, including when Free Hit in gameweek 19 was stated under FR-003. `[R-04]`
- **FR-013**: A chip already used before the plan MUST NOT be plannable in any gameweek of that chip period, and MUST be presented as unavailable with the reason "used before this plan". `[R-01]`
- **FR-014**: A chip planned in a gameweek MUST be presented as unavailable in every other gameweek of the same chip period with the reason naming the gameweek it is planned for, and MUST become available again as soon as it is removed or moved. `[R-01, R-02]`
- **FR-015**: Availability in one chip period MUST NOT be affected by use or planning in the other chip period, except for the Free Hit restriction in FR-012. `[R-01, R-04]`
- **FR-016**: The screen MUST present "used before this plan" and "planned for gameweek N" as visibly different states, and MUST show, for any gameweek, which chips are available, planned there, planned elsewhere, used before the plan, or unavailable for a rule reason (for example Wildcard in gameweek 1).
- **FR-017**: Chip rules (once per period, one per gameweek, gameweek 1 restriction, the gameweek 19/20 Free Hit restriction, used-before-plan) MUST be enforced authoritatively by the application's rules, so that a request which bypasses the screen is rejected with the same explanation. `[R-01, R-02, R-03, R-04]`
- **FR-018**: Wildcard and Free Hit gameweeks MUST be unlimited-transfer gameweeks (FR-023). Activating Bench Boost or Triple Captain alone MUST NOT change transfer allowance, hits or bank; transfers made during those gameweeks follow ordinary accounting. Their projected-points effects remain as already computed; this feature does not change the points model. `[R-07]`

**Free transfers, transfers, hits and squad flow**

- **FR-019**: For each gameweek the Planner MUST compute and show: free transfers available, transfers made, points hit, free transfers carried into the next gameweek, and bank; and, for the plan, the total points hit.
- **FR-020**: After an ordinary gameweek, including one with Bench Boost or Triple Captain, the following gameweek's free transfers MUST equal the unused remainder plus one, capped at five, or exactly one if transfers exceeded the allowance. Bench Boost and Triple Captain activation MUST NOT consume the arising free transfer or grant unlimited transfers. Transitions after Wildcard or Free Hit follow FR-021, and after gameweek 1 follow FR-022. `[R-05, R-07, R-08]`
- **FR-021**: For the gameweek after a Wildcard or Free Hit gameweek, the free transfers available MUST equal the transfers already banked before the chip gameweek (the chip gameweek's available free transfers less the one that arose for it, never below zero) plus the one arising for that next gameweek, capped at five. Activating the chip consumes the free transfer that arose for the chip gameweek; it MUST NOT create an additional banked transfer. `[R-07, R-08]`
- **FR-022**: Gameweek 1 MUST be treated as unlimited and hit-free, and gameweek 2 MUST begin with exactly one free transfer regardless of gameweek-1 activity, including Bench Boost or Triple Captain. `[R-05; formerly U-01]`
- **FR-023**: A gameweek with Wildcard or Free Hit, and gameweek 1, MUST be shown as unlimited transfers with no points hit.
- **FR-024**: In any other gameweek, the points hit MUST equal 4 points multiplied by the number of transfers made beyond the free transfers available. `[R-06]`
- **FR-025**: Transfers made in a gameweek MUST be derived from the meaningful planned changes between that gameweek's squad and the squad it follows: the starting squad for the plan's first gameweek, the previous gameweek's squad otherwise, and the restored pre-Free-Hit squad for the gameweek after a Free Hit. The Planner is NOT required to model transaction sequences in which a player is transferred out and bought back within the same gameweek. `[PC-01, R-10; formerly U-02]`
- **FR-026**: Squad membership, bank, ownership cost basis and transfer state MUST flow forward. A transfer carries into later gameweeks that still contain the outgoing player, with the incoming player taking that slot. Wildcard acquisitions and their saved purchase-price bases are permanent. At the deadline following a Free Hit, the underlying pre-Free-Hit squad and bank MUST be restored with its original ownership/purchase-price provenance, including any assumed-price status; temporary acquisitions and sales MUST NOT replace it. Original players' genuine market-price changes MUST still apply to latest market-price information and newly created or edited decisions, subject to FR-035's stable saved transaction prices. `[R-10, R-11, R-12, Q-3; formerly U-02, U-03, U-04]`
- **FR-027**: Earlier-gameweek changes MUST recalculate affected later values consistently under FR-035 and be validated across affected gameweeks. Reject new planning edits that introduce illegal squads, lineups or unaffordable decisions under FR-040, retaining the previous accepted plan. Provenance corrections follow FR-048/FR-049 instead: preserve decisions and surface dependent financial invalidity. Existing unresolved issues MUST NOT be treated as newly introduced by an otherwise legal repair. Lineup-only edits MUST preserve later choices under FR-047. `[Q-2, Q-3, Q-7]`
- **FR-028**: FPL squad rules (squad size and position counts, per-club limit, formation, bench order, captaincy) MUST be enforced authoritatively by the application's rules for every gameweek's squad, regardless of how the squad was changed (rearrangement, inline planned transfer, or any direct request).
- **FR-029**: These rules MUST apply identically to transfers however they are made in the Planner, including the Planner's existing inline planned-transfer interaction, which is not redesigned here.

**Purchase price, selling price and bank**

- **FR-030**: The Planner MUST distinguish latest known current market price, purchase-price basis and its provenance (authoritative, user-confirmed or assumed), and official calculated selling price. For a saved transaction it MUST also distinguish the market-price assumption and resulting transaction prices fixed for that decision from any newer live prices. `[R-09, Q-4, Q-6]`
- **FR-031**: The selling price MUST follow the official rule: if the market price used for the decision is at or below purchase price, sell at that market price; otherwise sell at purchase price plus £0.1m for each complete £0.2m rise above it. New or edited transactions use latest known market prices under FR-035; saved transaction prices remain based on their recorded assumptions rather than being silently recalculated on refresh. The same rule applies to ordinary, Wildcard and temporary Free Hit sales. `[R-09, Q-4]`
- **FR-032**: Every starting-squad player MUST have a plan-specific purchase-price basis visible and editable from the plan. Use an authoritative purchase price where already available; otherwise pre-fill current market price as an explicit assumption, not historical fact. Assumed prices MUST NOT block plan creation or use or require confirmation of all 15 players. Show a small per-player "Estimated" indicator and a concise plan-level indication, not prominent repeated warnings. Financial results depending on assumed cost basis MUST be identified as provisional. Correcting or confirming a price MUST remove that player's assumption warning and update dependent provisional status; confirmation of an estimate MUST NOT misrepresent its source as authoritative history. A value correction MUST follow FR-048/FR-049, not be rejected because existing planned transfers become unaffordable. Historical My Team reconstruction and changes to My Team are not required. `[Q-6, Q-7]`
- **FR-033**: A planned acquisition's saved price MUST become that player's new cost basis until sold, including a later-gameweek buy-back and Wildcard acquisition. It MUST carry forward under FR-026; a Free Hit acquisition is temporary and MUST NOT replace underlying cost basis after reversion. If explicitly editing an upstream acquisition changes a later sale's cost basis, recalculate that dependent sale using its own saved market assumption, leaving its incoming acquisition price unchanged. Only the explicitly edited transfer uses latest market prices. This planning edit remains subject to Q-2 validation, not Q-7's provenance-correction acceptance exception. `[R-11, R-12, Q-4, Q-7]`
- **FR-034**: Each gameweek's bank MUST equal its starting bank plus saved outgoing selling prices minus saved incoming acquisition prices under FR-035; after Free Hit use the restored pre-Free-Hit bank before applying that next gameweek's own transfers. Affordability MUST use those transaction prices: reject new unaffordable planning edits, but preserve and flag existing decisions rendered unaffordable by provenance correction under FR-049. Ordinary market-data refresh MUST NOT change saved transactions or downstream bank. Results depending on assumed starting bases MUST remain provisional without blocking otherwise legal planning. A negative bank resulting from provenance correction MUST be shown as a shortfall, never clamped to zero or hidden. `[R-09, R-10, Q-4, Q-6, Q-7]`
- **FR-035**: A new planned transfer MUST use latest known market prices to calculate its outgoing selling price under FR-031 with the carried-forward purchase-price basis and its incoming acquisition price. Save both transaction prices AND the market-price assumptions used, including the outgoing market price needed for later cost-basis corrections. They determine carried-forward bank and MUST NOT change on ordinary FPL refresh. Explicitly editing or replacing the transfer uses latest known prices and saves new assumptions. A provenance correction is NOT such a transfer edit: FR-048 recalculates only dependent selling prices from saved market assumptions and corrected cost basis, without repricing incoming acquisitions. Lineup edits, navigation and automatic persistence alone MUST NOT reprice transfers. The policy MUST be visible and consistent across plans; predictions and user-entered speculative future prices are out of scope. `[Q-4, Q-7]`
- **FR-036**: Wherever a planned sale or bank figure is shown, the user MUST be able to inspect the purchase-price basis, saved transaction prices and market assumptions that produced it, distinguish them from newer live prices, and identify provisional results depending on assumed cost bases. Assumption indicators MUST be lightweight and non-blocking under FR-032; actual financial invalidity MUST separately identify its earliest gameweek, reason and shortfall amount under FR-049.

**Automatic persistence**

- **FR-037**: Every accepted gameweek or starting-state change MUST be saved automatically without an explicit save action, including provenance corrections and their resulting financial-resolution state under FR-048/FR-049. A plan requiring resolution MUST remain persistable and reopenable, not lose corrected information or existing decisions. The "Save Gameweek" control MUST NOT exist. `[Q-2, Q-7]`
- **FR-038**: Selecting another gameweek, navigating away, or reloading MUST NOT silently discard an accepted edit, including corrected provenance: pending persistence or failure MUST be surfaced before a departure that would lose work, with an opportunity to retain or retry it. Only successfully persisted changes may be represented as saved or guaranteed available on reopening. `[Q-2, Q-7]`
- **FR-039**: When several edits are made in quick succession, the saved state MUST be the final state, and earlier saves MUST NOT overwrite later edits.
- **FR-040**: A new planning edit introducing a rule violation MUST be rejected without persistence or a visible invalid draft, with the reason and affected gameweek shown. Retain the previous accepted plan, preserving any valid-but-unsaved retry state or pre-existing Q-7 resolution status. This MUST NOT reject a starting purchase-price provenance correction solely because it exposes financial invalidity in saved decisions; that correction and dependent resolution state follow FR-048/FR-049. Existing unresolved issues MUST NOT block otherwise legal repairs or unrelated legal edits; newly introduced violations remain rejected. `[Q-2, Q-7]`
- **FR-041**: An accepted edit that cannot be saved for a technical reason MUST remain visible, clearly not saved and retryable, and MUST never fail silently. This includes accepted provenance corrections even when the plan requires financial resolution. Technical persistence failure MUST remain distinct from rejection of a new invalid planning edit and from a saved plan's financial invalidity. `[Q-2, Q-7]`
- **FR-042**: The Planner MUST show persistence status (saving, saved, not saved) unobtrusively and separately from financial status (provisional assumptions or requiring resolution). "Saved" MUST NOT imply financial validity. `[Q-6, Q-7]`

**Lineup rearrangement**

- **FR-043**: The Planner MUST let the user select any player in a planned gameweek's squad, clearly indicate the selection, and mark as valid targets only those players who could legally swap into that spot, matching the behaviour established on My Team (selection from either side, substitute-priority reordering between outfield bench players, the bench goalkeeper excluded from outfield reordering, cancel or replace selection, swap on selecting a target, and a confirmation announcing the swap).
- **FR-044**: Selecting a valid target MUST perform the swap immediately and save it automatically (FR-037); captaincy and vice-captaincy MUST follow the same behaviour as My Team.
- **FR-045**: Lineup and formation legality MUST be decided by the same authoritative rules as My Team (FR-028). The Planner MUST NOT hold a separate, divergent definition of legal formations; any screen-side filtering of targets is a convenience only.
- **FR-046**: The Planner's earlier dropdown-and-button swap interaction MUST be replaced by the interaction in FR-043.
- **FR-047**: Starting XI, bench order, captain and vice-captain MUST be gameweek-specific planning decisions: editing them in one gameweek MUST NOT silently rewrite the corresponding choices in later gameweeks. Squad membership changes flowing forward (FR-026) place the incoming player in the outgoing player's lineup slot and change nothing else. `[Q-3]`

**Provenance correction and financial resolution**

- **FR-048**: A corrected starting purchase-price basis MUST recalculate each dependent saved selling price using that decision's already-saved market-price assumption and the corrected carried-forward cost basis. Keep incoming acquisition prices, market-price assumptions and planned transfer identities unchanged; do not pull latest market prices into existing decisions. Recalculate bank and dependent financial state forward, following ordinary ownership, Wildcard permanence and Free Hit reversion under FR-026. Confirmation without a value change only updates provenance and dependent provisional status. Accept and automatically persist the correction even if financial invalidity is exposed; it is distinct from explicitly editing a transfer under FR-035. `[Q-4, Q-6, Q-7]`
- **FR-049**: When provenance correction makes existing saved decisions financially invalid, preserve those decisions and corrected information. Identify the earliest invalid gameweek and show its reason and shortfall amount; mark the dependent financial chain from that point as requiring resolution, not financially valid. A later non-negative projected bank alone MUST NOT erase an earlier unresolved invalidity. Respect Free Hit's bank reversion when determining financial dependencies, while keeping any unresolved temporary-gameweek issue visible at plan level. Permit legal repairs without requiring separate pre-existing downstream issues to disappear first; reject new invalid planning decisions under FR-040. After each accepted repair, recalculate forward, clear resolved invalidity and retain or relocate the earliest remaining issue as appropriate. Persistence and reopening MUST preserve the correction, decisions and resolution state. `[Q-2, Q-7]`

### Key Entities

- **Plan**: A manager's multi-gameweek planning workspace with a horizon (first and last gameweek) and a starting state.
- **Plan Starting State**: What the plan cannot infer: free transfers remaining at the point the plan begins, chips already used before the plan within the chip period containing the first gameweek, whether Free Hit was played in gameweek 19 (for a gameweek-20 start), the starting squad and bank taken from My Team, and the starting squad's purchase prices.
- **Chip Period**: One of the two parts of the season (gameweeks 1-19 and 20-38) in each of which each chip may be played once.
- **Chip**: Wildcard, Free Hit, Bench Boost or Triple Captain.
- **Used-Before-Plan Chip**: A chip the manager declares as already played, in the chip period of the plan's first gameweek, before the plan begins. Fixed by the starting state; cannot be planned.
- **Planned Chip**: A chip placed on a specific plan gameweek. Can be moved or removed.
- **Plan Gameweek**: The squad, lineup, captaincy and optional planned chip for one gameweek, with its derived accounting.
- **Gameweek Accounting**: For a plan gameweek, the free transfers available, transfers made, points hit, free transfers carried forward and bank.
- **Squad State**: The 15 players held in a gameweek, which flows from gameweek to gameweek subject to Free Hit reversion.
- **Owned-Player Price Basis**: A player's purchase price and provenance (authoritative, user-confirmed or assumed). For starting players it is established per plan under FR-032; for acquisitions it is the saved acquisition price. It lasts until sale, is permanent through Wildcard and is preserved underneath a temporary Free Hit squad. Current market information is separate from this cost basis.
- **Assumed Future Market Price**: The latest known market price recorded as the assumption when a planned transfer is created or edited, not a prediction of the price in that future gameweek.
- **Planned Transaction Prices**: The outgoing selling price calculated from the applicable cost basis and assumed market price, and incoming acquisition price, saved for a planned transfer. They determine bank flow and remain stable across ordinary data refreshes. An assumed starting basis makes dependent financial results provisional without blocking planning.
- **Financial Resolution State**: The earliest gameweek rendered unaffordable by corrected purchase provenance, its reason and shortfall amount, and the financial chain depending on it. These preserved decisions are not financially valid until repaired. This state is independent of estimated-price provenance and of technical saving/saved/not-saved status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can state a plan's free transfers remaining, already-used chips and starting-squad purchase prices from the plan itself and see every gameweek update, without leaving the plan and without any separate save action.
- **SC-002**: For reference scenarios covering accumulation, use, the five-transfer cap, hits, Wildcard/Free Hit consumption of the arising free transfer, Bench Boost/Triple Captain retaining ordinary transfer accounting, Free Hit reversion, gameweek 1/2 handling and a starting value of 0, the Planner's free transfers, transfers made and points hits match independently hand-calculated values in 100% of cases.
- **SC-003**: In 100% of attempts, a chip cannot be planned more than once per chip period, cannot be planned when declared used before the plan, cannot share a gameweek with another chip, cannot be Wildcard or Free Hit in gameweek 1, and cannot be Free Hit in both gameweek 19 and gameweek 20; each refusal explains why.
- **SC-004**: For any plan, a user can tell for every chip, at a glance and without opening other screens, whether it is available, planned (and for which gameweek), used before the plan, or unavailable for a rule reason.
- **SC-005**: For reference cases covering price fall, no change, rises of £0.1m/£0.2m/£0.3m/£0.4m, estimated starting bases, confirmation/correction, planned acquisitions, later buy-backs, Wildcard permanence and Free Hit reversion with genuine market changes, selling prices and bank match hand calculations in 100% of cases. Refresh changes no saved transaction or downstream bank; explicit transfer edits use latest prices; provenance corrections use saved market assumptions and leave incoming prices unchanged. Estimates never require confirmation to plan. Corrections exposing deficits remain saved with decisions intact, the earliest shortfall and dependent chain flagged, and resolved flags clear after legal repairs, including after reopening.
- **SC-006**: After accepted edits are successfully persisted, moving between gameweeks and reloading retains 100% of the latest saved edits and any financial-resolution status with no explicit save action required. Pending or failed persistence is surfaced before a departure that would lose work, with an opportunity to retain or retry it.
- **SC-007**: Every technical save failure is surfaced and retryable, with zero silent failures. New rule-breaking planning edits are rejected. Provenance corrections exposing financial invalidity are retained with existing decisions and explicit resolution status, never falsely represented as financially valid merely because they are saved.
- **SC-008**: Rearranging a lineup in a planned gameweek takes two selections, never offers an illegal target, and offers the same targets and yields the same lineup as My Team for the same squad.
- **SC-009**: A lineup, squad or chip request that breaks a rule is rejected with an explanation in 100% of cases, whether it comes from the screen or directly.

## FPL Rules and Product Constraints

### Confirmed FPL rules

These rules have been confirmed for 2026/27 by the product owner and are no longer assumptions. The earlier assumption IDs (the previous draft's `A-nn`) are shown in the "Formerly" column for traceability.

| ID | Confirmed rule | Formerly | Where it matters |
|----|----------------|----------|------------------|
| R-01 | There are two sets of Wildcard, Free Hit, Bench Boost and Triple Captain chips. The first set must be used by the gameweek 19 deadline; the second set is available from gameweek 20 onward. Unused first-period chips do not carry over. | A-01 | FR-002, FR-009, FR-013-FR-015; US1, US2 |
| R-02 | Only one chip can be active in a gameweek. | A-02 | FR-010, FR-017; US2 |
| R-03 | Wildcard and Free Hit cannot be played in gameweek 1. Bench Boost and Triple Captain may be. | A-03 | FR-011, FR-017; US2; Edge Cases |
| R-04 | Free Hit cannot be played in both gameweek 19 and gameweek 20. | New | FR-003, FR-007, FR-012, FR-015; US1, US2 |
| R-05 | Gameweek 1 is unlimited (squad selection before the first deadline). After the first deadline, managers receive one free transfer per gameweek and can bank up to five; therefore a normal continuing team's gameweek 2 begins with one free transfer regardless of gameweek-1 activity. | A-04, part of A-05; U-01 confirmed | FR-001, FR-020, FR-022; US3 |
| R-06 | Each transfer beyond the free transfers available costs 4 points. | A-06 | FR-024; US3 |
| R-07 | Specifically Wildcard and Free Hit preserve free transfers already banked before their gameweek and consume the one arising for it, rather than adding an extra banked transfer. With N available, the next gameweek has min(5, max(N - 1, 0) + 1). This consumption rule does NOT apply to Bench Boost or Triple Captain, which retain ordinary transfer use, accumulation and hits. | A-07 (corrected and narrowed) | FR-018, FR-020, FR-021, FR-023, FR-024; US3; SC-002 |
| R-08 | There is no one-off free-transfer top-up in 2026/27; the top-up used in 2025/26 does not apply this season. | A-11 | FR-020, FR-021; Assumptions |
| R-09 | A player's selling price depends on purchase price as well as current market price. If the market price is at or below the purchase price, the player sells at the market price. If it is above, the selling price rises by £0.1m for each £0.2m of rise above the purchase price. | A-12 (reversed) | FR-030, FR-031, FR-034; US4 |
| R-10 | Free Hit is temporary: at the following deadline the pre-Free-Hit squad and bank are restored. Transfers in the following gameweek are counted against that restored squad. | U-02 confirmed; former A-08 | FR-025, FR-026, FR-034; US3, US4 |
| R-11 | Wildcard transfers are permanent, including the purchase-price basis of genuine new acquisitions. | U-03 confirmed; former A-09 | FR-026, FR-033; US3, US4 |
| R-12 | A Free Hit's temporary squad MUST NOT replace the underlying squad's ownership or purchase-price provenance. Afterwards the original ownership cost basis continues, while genuine market-price changes affecting those original players still apply. Temporary sales follow R-09, but their bank and cost-basis effects do not survive reversion. For saved planning decisions, Q-4 fixes the transaction-price assumptions; a new or edited sale uses latest known market information with the preserved original cost basis. | U-04 confirmed and refined | FR-026, FR-030-FR-036; US4; SC-005 |

### Product constraints

| ID | Constraint | Where it matters |
|----|------------|------------------|
| PC-01 | Same-gameweek transfer round trips are deliberately unsupported: the Planner does not model transferring a player out and later buying the same player back within the same gameweek. The Planner models sensible planned squad decisions and optimisation, not every technically possible transaction sequence; such a sequence has no planning value and wastes transfers. Transfer accounting may therefore operate on the meaningful planned changes between relevant squad states instead of keeping a complete transaction ledger. This is a scope decision, not an unresolved FPL-rule assumption (formerly assumption A-10, which asked how round trips are counted). | FR-025; Edge Cases |
| PC-02 | The plan's starting free-transfer value means the number of free transfers remaining at the point the user begins the plan. It is therefore valid for it to be 0 to 5 (for example after transfers have already been used in the current gameweek), and it defaults conceptually to 1. It is not "the free transfers available at the opening of a fresh gameweek". | FR-001; US1 |
| PC-03 | Official purchase and selling-price accounting is in scope. Distinguish live market prices, cost basis/provenance, calculated selling prices and saved transaction prices. Q-4 keeps market assumptions fixed across refresh; Q-6 allows assumed starting bases with lightweight warnings and provisional finances; Q-7 recalculates dependent sales from saved market assumptions after provenance correction and retains any resulting financial-resolution state. Acquisitions establish a new cost basis, permanent except for Free Hit reversion. Predictions and speculative future-price inputs are out of scope. | FR-030-FR-036, FR-048/FR-049; US4 |

### Former Unverified Assumptions

None of U-01 to U-04 remains unverified. They are retained below only to trace their conversion into confirmed rules.

| ID | Resolution | Formerly | Where it matters |
|----|------------|----------|------------------|
| U-01 | Confirmed in R-05: GW2 begins with one free transfer for a normal continuing team. | Part of former A-05 | FR-022; US3 |
| U-02 | Confirmed in R-10: restore the pre-Free-Hit squad and bank at the following deadline. | Former A-08 | FR-025, FR-026, FR-034; US3 |
| U-03 | Confirmed in R-11: Wildcard acquisitions are permanent. | Former A-09 | FR-026, FR-033; US3, US4 |
| U-04 | Confirmed and refined in R-09/R-12: temporary Free Hit transactions do not overwrite underlying ownership cost basis; genuine market changes still affect original players, separately from Q-4's frozen saved transaction prices. | New in previous draft | FR-026, FR-030-FR-036; US4; Edge Cases |

## Open Clarifications

Q-1 to Q-7 are resolved product decisions, retained under this original heading for traceability. No clarification remains open; the Q-7 provenance-correction exception is distinct from Q-2's rejection of new invalid planning edits.

- **Q-1 (resolved: contradictory chip decisions)**: Reject contradictory changes in either direction with an explanation naming the conflicting gameweek; never silently clear another decision. This includes Free Hit declared in gameweek 19 while planned in gameweek 20.
- **Q-2 (resolved: invalid edits)**: Reject new planning edits introducing rule violations without persisting or retaining an invalid draft. Preserve the prior accepted state and any existing unresolved status. Accepted changes failing technical persistence remain visible, clearly not saved and retryable. Provenance corrections exposing financial invalidity are retained under Q-7, not rejected as new invalid planning decisions.
- **Q-3 (resolved: what flows forward)**: Squad membership, bank, financial ownership/cost basis and transfer state flow forward subject to Free Hit reversion. Starting XI, bench order, captain and vice-captain are gameweek-specific and are not silently rewritten by lineup-only edits elsewhere. A squad substitution flowing forward places the incoming player in the outgoing player's slot only and must still satisfy every affected gameweek's legality.
- **Q-4 (resolved: price basis for future planned transfers)**: Save outgoing selling price and incoming acquisition price at transfer creation using the latest known market prices and carried-forward cost basis. Refreshes do not reprice saved transactions or downstream bank. Editing or replacing that transfer establishes new transaction-price assumptions under FR-035. The policy applies to all plans, with assumptions belonging to each decision; no prediction or speculative user-entered future prices.
- **Q-5 (resolved: completed gameweeks)**: Completed gameweeks remain editable. Historical immutability, versioning and "what was planned at the time" behaviour are deferred to Historical Plan Evaluation; editing transfers follows Q-4 rather than reconstructing historical prices.
- **Q-6 (resolved: starting-squad purchase prices)**: Establish a plan-specific cost basis for all 15 players from authoritative prices where available, otherwise current market prices marked assumed. Allow planning with lightweight warnings and provisional dependent finances; no all-player confirmation gate. Later correction or confirmation removes the player's warning. No historical reconstruction or My Team changes are required. See FR-032.
- **Q-7 (resolved: corrected provenance and dependent saved plans)**: Recalculate dependent sales from saved market assumptions and corrected cost basis without changing incoming prices or fetching latest prices. Preserve and persist the correction and existing decisions even if a shortfall appears. Identify the earliest invalid gameweek, reason and amount and mark its dependent chain as requiring resolution. Allow legal repairs and clear resolved downstream invalidity after recalculation. See FR-048/FR-049; this is not an ordinary refresh or a new invalid planning edit.

## Out of Scope

- Navigating from the Planner to the Transfer Explorer to make planned transfers (the next planned feature), and any redesign of the Planner's existing inline planned-transfer interaction beyond applying the rules in this specification to it.
- Transfer Explorer filtering and sorting redesign.
- Actual-points-versus-xPts analysis and full historical plan evaluation.
- Immutable plan versioning and "what was planned at the time" behaviour.
- Changes to the xPts projection model.
- Historical My Team reconstruction.
- Prediction of future player-price changes and user-entered speculative future prices (saved transaction-price assumptions follow Q-4).
- Optimal multi-gameweek planning or automatic chip and transfer suggestions.
- General visual redesign of the Planner page.
- Support for same-gameweek out-and-back transfer sequences (PC-01).
- Correcting the My Team and Transfer Explorer approximation of selling price at current market price; neither screen is changed by this feature. Starting purchase-price review and correction occur in the plan, without requiring historical My Team reconstruction.

## Assumptions

- Plans continue to be created from the saved My Team squad and bank; the starting squad and bank are not otherwise edited in the Planner by this feature, but the starting squad's purchase prices are part of the starting state (FR-004, Q-6). Capturing the My Team bank (and a legacy plan's initial bank) is the only boundary that tolerates float representation noise; it normalises to exact whole tenths and rejects every other non-tenth value with a readable `invalid_money` error, while all Planner replay and mutation money stays strictly integer tenths.
- Chip rules, free-transfer rules, hit size, chip effects, Free Hit reversion and selling-price rules are confirmed as R-01 to R-12. U-01 to U-04 no longer represent unresolved assumptions.
- The single-user, single-manager context remains: one manager's team owns the plans. Concurrent editing from two places is not specially protected; the latest accepted save wins, including provenance corrections with an explicit financial-resolution state.
- The Planner keeps whole-squad-per-gameweek planning, with transfers derived by comparing relevant squad states. Each saved planned transfer also retains its transaction-price assumptions and acquisition cost basis under Q-4; no full transaction ledger or same-gameweek round trips are required.
- The existing projection and points calculation for plan gameweeks, including chip effects on projected points, is unchanged.
- Existing plans remain usable with their free-transfer starting value retained and no chips declared used before them. Missing price provenance is established under FR-008/FR-032 with non-blocking estimates; this does not certify any pre-existing illegal squad or chip decision as valid under the corrected rules.
- Plans are independent starting-state snapshots: later My Team changes or ordinary market-data refreshes do not silently replace their starting squad, bank, purchase-price assumptions or saved transaction prices.
- Latest market prices already known to the application are the source for new or edited planned decisions, never predictions. Assumed starting purchase prices are not silently updated on refresh. Saved transaction prices remain distinct from live market values.
- Success criteria assume the reference scenarios in SC-002 and SC-005 are agreed as part of planning and cover FR-019 to FR-036 and FR-048/FR-049, including financial resolution after provenance correction.
