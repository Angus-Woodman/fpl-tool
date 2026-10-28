# Feature Specification: Planner Transfer Workflow

**Feature Branch**: `feature/planner-transfer-workflow`

**Created**: 2026-10-28

**Status**: Draft (all clarifications Q-1 to Q-8 resolved; ready for `/speckit-plan`)

**Input**: User description: "Phase 003 connects the Transfer Explorer and the Planner, and adds plan duplication. (A) Let a manager explore, compare and select transfers for a particular gameweek within an existing plan, using that plan's hypothetical squad, bank, selling prices, free transfers, chips and future-gameweek projections instead of their actual My Team, then confirm the transfer into that Planner gameweek through the established Planner mutation system and return to the plan with the consequences for later gameweeks recalculated. My Team's Transfer Explorer must keep working unchanged. (B) Add a Duplicate Plan action on the individual Plan page that creates an independent, fully saved copy of the plan's canonical state, named with an `(option N)` convention, so alternative transfer strategies can be compared. Out of scope: broader UI/UX redesign (Phase 004), historical plan evaluation against actual results (Phase 005), projection-model changes, multi-gameweek optimisation or automated replanning, and historical My Team reconstruction."

Supporting evidence for every statement in **Background** is in [current-state-assessment.md](current-state-assessment.md). That file also holds the risk register and the suggested implementation slices; this specification stays at the level of user-visible behaviour and domain rules.

## Background: what exists today

This section is context, not a requirement.

- **Transfer Explorer** serves only the saved My Team squad. Its squad, bank and free transfers come from My Team; replacements are ranked by projected team gain over 1, 3 and 5 gameweeks using the latest `component_v3` projection run; the horizon starts at the first gameweek that has projections, not at a chosen gameweek; selling price is approximated as current market price and labelled as such; applying a transfer rewrites the saved My Team squad.
- **Planner** (Phase 002) holds one independent, revisioned canonical state per plan (starting boundary, per-gameweek decisions, saved price assumptions). Squads, banks, free transfers, hits, chip availability and financial status are derived by replay. All changes to an existing plan go through one guarded mutation operation with revisions, retry identity, and a plan-scoped autosave coordinator.
- **Planner transfers today** are made through a small inline picker on a squad card. It lists at most 50 available players per position by descending price, has no search, no projections and no fixtures, and the choice of gameweek lives only in the Planner page's local state.
- **Plan lifecycle**: plans are created from My Team, listed, renamed, resized and deleted. There is no way to copy one. Plan names are not unique and are limited to 100 characters.
- Plans created before Planner Foundations that have not been initialised are visible but read-only.

The two workflows are not connected: the Explorer cannot be told about a plan, and the Planner cannot hand a player or gameweek to the Explorer.

## Clarifications

### Session 2026-10-28

Resolved by the product owner:

- Q: What does "projected gain" mean in Planner mode? (Q-1) → A: Rank by the existing best-XI projected gain, and separately display the actual impact on the plan's current lineup. See FR-023, FR-029.
- Q: When a candidate clashes with a later planned decision in the same plan, what does the Explorer do? (Q-2) → A: The candidate stays visible and available for exploration and preview; the affected gameweek is identified and the reason it cannot currently be committed is explained; Confirm is disabled. No automatic or guided repair is built into the Explorer. See FR-016, FR-030.
- Q: Is incoming-player selectability enforced only when filtering the Explorer, or authoritatively? (Q-3) → A: Authoritatively, through the shared Planner mutation path, for new or edited transfers, without retroactively invalidating saved decisions. See FR-012.
- Q: Must a lost-response retry of Duplicate Plan be exactly-once? (Q-4) → A: No. No database migration solely for duplication idempotency; uncertain outcomes are handled explicitly and accidental repeated requests are prevented. See FR-056.
- Q: After copies are deleted, which option number is used next? (Q-5) → A: The highest option number among currently existing plans in the same family, plus one; numbers freed by deletion may be reused; no numbering history is persisted. See FR-049, naming rule 3.
- Accepted defaults: duplication is blocked while saves are pending or failed; legacy plans awaiting initialisation are refused and not initialised; the Duplicate Plan control appears only on the individual plan page; no projection model selector is introduced.

- Q: For which gameweeks is the plan impact measured when a horizon spans several gameweeks? (Q-6) → A: Option B. Each gameweek of the horizon that the saved plan covers uses the plan's actual saved squad, lineup, bench and captaincy decisions for that gameweek. Horizon gameweeks beyond the plan's end use a hypothetical continuation of the plan's final state (the final gameweek's squad and lineup roles after the transfer and all later planned decisions, with Free Hit restoration), visibly distinguished as assumed and never implying the plan has decisions beyond its horizon. Plan impact reflects the transfer's valid consequences, not a raw comparison of two players' projections, and the best-XI gain ranking is preserved separately. See FR-023, FR-025.
- Q: If relevant market prices change between preview and confirmation, what happens? (Q-7) → A: Option A. The confirmation is rejected and a refreshed preview is required; different financial assumptions are never accepted silently. See FR-033.
- Q: What response times are acceptable for the candidate list and preview? (Q-8) → A: Option A. Candidate list within 3 seconds and an individual preview within 2 seconds on the representative local dataset, with loading states; these are measurable targets, not a licence for premature optimisation. See SC-014.
- Confirmed: the plan-impact column appears in the candidate list as well as the preview; for blocked candidates, valid information is shown up to the first downstream conflict, the affected gameweek and decision are identified, and dependent later values are not presented as valid; later planned decisions are never altered or repaired automatically.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Explore replacements in the context of a plan (Priority: P1)

A manager viewing gameweek 7 of a plan chooses a player in that gameweek's squad and opens the Transfer Explorer for that player. The Explorer shows it is working inside that plan and gameweek, lists suitable replacements ranked with the existing logic, and calculates affordability, selling price and projections from the plan's squad and finances at gameweek 7, not from My Team.

**Why this priority**: Everything else in Feature A depends on a trustworthy, plan-aware candidate list. It is also the smallest piece that is useful on its own: a manager can see which replacements make sense for a future gameweek, even before committing anything.

**Independent Test**: In a plan whose gameweek 7 squad differs from My Team (different players, different bank), open the Explorer from a gameweek 7 player. Confirm the outgoing player, bank, owned-player exclusions, selling price and affordability all reflect the plan, the horizon labels read GW7, GW7-9 and GW7-11, and My Team is untouched.

**Acceptance Scenarios**:

1. **Given** a plan with gameweek 7 selected, **When** the user chooses "Explore transfers" on a player, **Then** the Explorer opens in Planner mode showing the plan name, gameweek 7 and that player as the outgoing player, with no re-selection needed.
2. **Given** the Planner with gameweek 7 selected, **When** the user starts exploration for the gameweek without choosing a player, **Then** the Explorer opens in Planner mode and offers that gameweek's squad players to choose from.
3. **Given** a plan squad that differs from My Team, **When** candidates are listed, **Then** players owned in the plan's gameweek 7 squad are excluded, players owned only in My Team are not, and no figure is taken from My Team.
4. **Given** a candidate list, **When** the user reads a candidate's money figures, **Then** the outgoing player's selling price is the official selling price for the plan's purchase-price basis, the incoming price is the latest known market price, and the resulting bank is the plan's gameweek-7 bank after the transfer; the My Team "approximated as current price" note does not appear.
5. **Given** a plan player whose purchase price is an estimate, **When** its selling price or any figure that depends on it is shown, **Then** it carries the concise "Estimated" indication and is described as provisional.
6. **Given** horizons of 1, 3 and 5 gameweeks and gameweek 7 selected, **When** gains are shown, **Then** they cover GW7, GW7-9 and GW7-11 respectively, and the Explorer states which gameweeks were actually evaluated.
7. **Given** projections cover only some of the horizon, **When** gains are shown, **Then** the Explorer says so (for example "3 of 5 gameweeks available") and never fills missing gameweeks with zero.
8. **Given** the selected gameweek has no projections, no projection run exists, or required squad projections are missing, **When** the Explorer opens, **Then** it shows an explicit unavailable state naming the cause and offers no ranking; it never substitutes another model, an older run or invented values.
9. **Given** the Explorer is showing results, **When** the user looks at the header, **Then** the projection model, run identifier and generation time are visible, and the same run is used for ranking and every preview in the session.
10. **Given** a candidate that is not affordable or breaks the club limit in that gameweek, **When** the list is shown, **Then** it remains visible, marked unavailable with the reason (for example the shortfall amount), and can still be previewed but not confirmed.
11. **Given** a candidate that clashes with a later planned decision in the same plan (the plan later sells the outgoing player or buys the candidate), **When** the list is shown, **Then** it remains visible and available to explore and preview, is marked "blocked by a later planned decision" naming the affected gameweek, and is not hidden or demoted from the ranking because of the clash.
12. **Given** the plan, gameweek or outgoing player in the address is invalid (plan missing, gameweek outside the plan, player not in that gameweek's squad, plan awaiting initialisation, plan evaluation blocked), **When** the Explorer loads, **Then** it shows an explicit state for that cause rather than falling back to My Team.
13. **Given** the Explorer is opened without plan context (from My Team), **When** the user uses it, **Then** it behaves exactly as before this phase.
14. **Given** a plan in which the outgoing player is starting in GW7, benched in GW8 and captain in GW9 according to the saved lineups, **When** plan impact is shown for a 3-gameweek horizon from GW7, **Then** each gameweek's impact reflects the replacement in that gameweek's role (starting in GW7, bench in GW8, captain in GW9) as the Planner scores that gameweek, not a raw difference between the two players' projected points.
15. **Given** a plan ending at GW8 and a 5-gameweek horizon from GW7, **When** plan impact is shown, **Then** GW7-8 are labelled as the saved plan and GW9-11 are separately labelled as an assumed continuation (the plan's final squad and final-gameweek lineup roles, no further decisions), totals for the two parts are shown separately, and nothing implies the plan contains decisions beyond GW8.
16. **Given** the candidate list, **When** the user reads it, **Then** a plan-impact column is shown next to the best-XI gain columns, the two are labelled distinctly, and the ranking order remains the best-XI gain.

---

### User Story 2 - Preview and commit a planned transfer (Priority: P1)

After comparing options, the manager previews one replacement and sees exactly how it would change the plan: bank, squad, transfers made, points hit and projected performance. Previewing changes nothing. Confirming writes the transfer into that plan gameweek through the Planner's established saving path.

**Why this priority**: This closes the loop that makes Feature A worth having, and it is where Planner correctness (finances, free transfers, chips, concurrency) is most at risk.

**Independent Test**: Preview a transfer in a plan gameweek, confirm nothing is saved, then confirm it. Reopen the plan and verify the new squad, bank, free transfers, hit and later gameweeks match an independent hand calculation, and My Team's saved squad, bank and free transfers are byte-for-byte unchanged.

**Acceptance Scenarios**:

1. **Given** a candidate, **When** the user opens its preview, **Then** it shows, for the selected gameweek, the resulting bank, free transfers available, transfers made before and after, points hit before and after (and the hit added by this transfer), the plan impact per gameweek and in total, the best-XI gain, and whether the gameweek is a Wildcard, Free Hit, Bench Boost or Triple Captain gameweek where that changes how the transfer is treated.
2. **Given** a preview, **When** the user closes it or leaves, **Then** the plan is unchanged and no save activity occurred.
3. **Given** a gameweek with a Free Hit, **When** a transfer is previewed, **Then** the preview states the transfer is temporary, that the squad reverts afterwards, and that the later gameweeks are unaffected.
4. **Given** a gameweek with a Wildcard, **When** a transfer is previewed, **Then** the preview states there is no points hit and that the transfer is permanent, and shows its effect on later gameweeks.
5. **Given** an ordinary gameweek where the transfer exceeds the free transfers, **When** it is previewed, **Then** the 4-point hit it adds is shown and reflected in the net effect.
6. **Given** a transfer in an ordinary or Wildcard gameweek, **When** the preview lists consequences for later gameweeks, **Then** it shows which later gameweeks change squad membership, bank or free transfers, and any later planned decision that would no longer be valid.
7. **Given** a valid preview, **When** the user confirms, **Then** the transfer is submitted through the Planner mutation operation against the plan revision the user previewed, the Explorer shows "saving", and the transfer is described as saved only after the save is acknowledged.
8. **Given** a confirmation in progress, **When** the user clicks Confirm again or retries, **Then** only one transfer is ever created.
9. **Given** the outgoing player was acquired by a transfer already planned in this same gameweek, **When** the user confirms a replacement, **Then** that planned acquisition is replaced, not stacked into a same-gameweek round trip, exactly as the Planner's own picker behaves.
10. **Given** a candidate the plan cannot legally accept (squad rules, club limit, unaffordable, sold in this gameweek, not selectable), **When** it is previewed, **Then** the reason and affected gameweek are shown and Confirm is disabled; a request that bypasses the screen is rejected with the same reason and nothing is saved.
11. **Given** a save that cannot complete for a technical reason, **When** it fails, **Then** the Explorer says the transfer is not saved, keeps the preview, and offers retry of the same edit and a check of the save status; it never claims success.
12. **Given** the plan changed in the meantime (revision advanced elsewhere), **When** the user confirms, **Then** the Explorer reports a conflict, keeps the user's context, refreshes the plan and requires a new preview before another confirmation; it never overwrites silently.
13. **Given** a confirmed transfer, **When** My Team is opened, **Then** its squad, bank and free transfers are exactly as before.
14. **Given** a candidate that clashes with a later planned decision (for example GW10 already sells the outgoing player, or buys the candidate), **When** the user previews it, **Then** the preview opens normally, shows the valid information up to the first downstream conflict (the selected gameweek's figures and those of any later gameweeks before the conflict, including plan impact for those gameweeks), names the affected gameweek and the clashing planned transfer, explains why the transfer cannot currently be committed, shows no later value that depends on the clash as valid, and keeps Confirm disabled.
15. **Given** a blocked candidate, **When** the user looks for a way to fix the clash, **Then** the Explorer offers no automatic or guided repair and changes no later decision; it only identifies the gameweek, so the user can adjust the plan in the Planner and return.
16. **Given** the outgoing or incoming player's latest known market price at confirmation differs from the one previewed, **When** the user confirms, **Then** nothing is saved, the Explorer says prices changed, shows the new figures and requires a fresh preview; different financial assumptions are never accepted silently.

---

### User Story 3 - Return to the plan with context and consequences (Priority: P2)

After confirming (or backing out), the manager lands back on the same plan and gameweek, sees the updated squad with the changed slot easy to spot, and can see how later gameweeks were affected. Reloading or following a shared address inside the Explorer keeps the same plan, gameweek and player.

**Why this priority**: Without it the integration works but feels lost; context loss is the main usability risk named for this journey. It builds on Stories 1 and 2.

**Independent Test**: Confirm a transfer in gameweek 9 of a multi-gameweek plan, and verify the Planner reopens on gameweek 9 with the incoming player visibly marked and in view, later gameweeks recalculated, and a confirmation shown; repeat with Back instead of Confirm and verify the plan and selected gameweek are unchanged.

**Acceptance Scenarios**:

1. **Given** a saved confirmation, **When** the user returns to the Planner, **Then** the same plan and gameweek are selected, the updated squad is shown, the incoming player is highlighted and scrolled into view, and a message names the transfer.
2. **Given** the user leaves the Explorer without confirming, **When** they return to the Planner, **Then** the same gameweek is selected and the plan is unchanged.
3. **Given** a transfer saved in gameweek 9, **When** the user views later gameweeks, **Then** their squad, bank, free transfers, hits and chip availability are recalculated consistently with the Planner's rules, with no stale values.
4. **Given** the Explorer is open in Planner mode, **When** the page is reloaded or the address is opened in a new tab, **Then** the same mode, plan, gameweek and (if chosen) outgoing player are restored.
5. **Given** the user changes horizon, previews candidates, closes a preview or uses browser Back and Forward within the Explorer, **When** they do so, **Then** plan and gameweek context is never lost or reset to My Team.
6. **Given** a save is pending or not saved, **When** the user tries to leave the Explorer, **Then** they are warned as the Planner warns today, and work is not silently lost.
7. **Given** the Planner is opened normally (without coming from the Explorer), **When** it loads, **Then** its behaviour is unchanged, including the default gameweek.

---

### User Story 4 - Compare replacement options efficiently (Priority: P3)

While deciding, the manager narrows and reorders replacements: searching by name, filtering by club, price, affordability and playing status, sorting by projected gain over each horizon, price, resulting bank and upcoming fixture difficulty, and seeing each candidate's fixtures over the horizon.

**Why this priority**: It makes Stories 1 and 2 pleasant on a pool of hundreds of players but is not required for the journey to be correct. It is deliberately limited and is not the Phase 004 redesign.

**Independent Test**: In Planner mode with a realistic pool, search for a player, filter to affordable candidates from one club, sort by price and by 3-gameweek gain, and confirm results, order and fixture columns are correct and that the browser performs no domain recalculation.

**Acceptance Scenarios**:

1. **Given** a candidate list, **When** the user searches by name, **Then** only matching candidates remain.
2. **Given** a candidate list, **When** the user filters by club, by maximum price, by "available to apply only" or by playing status, **Then** only matching candidates remain and the active filters are visible and clearable.
3. **Given** a candidate list, **When** the user sorts by gain at 1, 3 or 5 gameweeks, price, resulting bank or fixture difficulty, **Then** the order changes deterministically with a stable tie-break and the sort is indicated.
4. **Given** a candidate, **When** it is shown, **Then** its fixtures over the selected horizon (opponent, home or away, difficulty rating) are visible, starting at the selected gameweek.
5. **Given** filters or search that match nothing, **When** the list is shown, **Then** an explicit empty state says so and how to clear the filters.
6. **Given** the My Team Explorer, **When** it is used, **Then** it is unchanged unless a shared control is deliberately reused without altering its behaviour.

---

### User Story 5 - Duplicate a plan to compare alternative strategies (Priority: P2)

A manager on a plan's page chooses Duplicate Plan and, once everything is saved, immediately lands on a new, independent plan that is an exact saved copy of the original, named with the next "(option N)". They can then change the copy freely without affecting the original.

**Why this priority**: It is independent of Feature A, is small, and unlocks strategy comparison immediately. It carries the strongest data-integrity requirements (exact copy, atomicity, no shared identity), so it is specified in full under **Duplicate Plan Specification**.

**Independent Test**: Duplicate a plan with transfers, a Wildcard, estimated starting prices and a financially unresolved gameweek. Verify the copy's saved inputs match the original, its derived results match exactly, the original's revision and update time are unchanged, and edits to either plan never appear in the other.

**Acceptance Scenarios**:

1. **Given** a plan page where everything is saved, **When** the user chooses Duplicate Plan, **Then** a new plan is created, the user is taken to it, and a message names the new plan and its source.
2. **Given** the original is named "My Plan", **When** it is duplicated, **Then** the copy is "My Plan (option 2)"; duplicating the original again, or the copy, gives "My Plan (option 3)", then "My Plan (option 4)", never "My Plan (option 2) (option 2)".
3. **Given** the original has unsaved or failed edits, **When** the user views the Duplicate Plan control, **Then** it is disabled with an explanation, and no copy can be made that omits those edits.
4. **Given** the original is awaiting Planner initialisation, **When** the user views the control or the request is made directly, **Then** duplication is refused with an explicit reason and the plan is not modified or initialised.
5. **Given** a successful duplication, **When** either plan is edited, **Then** the other is unaffected, in saved state and in everything derived from it.
6. **Given** duplication fails, **When** the user sees the result, **Then** they stay on the original with a clear error, no new plan exists, and the original is unchanged.
7. **Given** repeated clicks while a request is running, **When** the request finishes, **Then** exactly one new plan exists for that action, because the control is disabled from the first click until the outcome is known.
8. **Given** the response to a duplication is lost or times out, **When** the user sees the result, **Then** the message says the outcome is unknown, that a copy may already exist, and links to the Plans list; no automatic retry occurs; the control becomes available again so a deliberate retry is possible.
9. **Given** "My Plan", "My Plan (option 2)" and "My Plan (option 3)" exist and "(option 3)" is deleted, **When** "My Plan" is duplicated, **Then** the copy is "My Plan (option 3)"; **Given** instead "(option 2)" is deleted and "(option 3)" remains, **Then** the copy is "My Plan (option 4)".

---

### Edge Cases

**Feature A**

- The outgoing player was bought earlier in the same plan: the transfer carries that acquisition's saved price as its cost basis, and replacing it in the same gameweek replaces the acquisition (US2-9).
- A later planned transfer sells the outgoing player, or buys the candidate: the candidate stays visible, explorable and previewable, is flagged with the clashing gameweek and cannot be confirmed (FR-016); nothing is silently retargeted, dropped or repriced, and no repair is offered in the Explorer.
- The explored gameweek is the plan's first gameweek: the transfer is counted against the plan's starting squad and starting free transfers, as in Planner Foundations.
- The explored gameweek is a Free Hit gameweek: the gain horizon is that single gameweek, because the transfer does not carry forward; this is stated in the interface (FR-026).
- The horizon extends past the plan's last gameweek: it is not clipped (a 5-gameweek horizon from GW7 is GW7-11 even in a plan ending GW8). Plan impact for gameweeks after the plan's end is an assumed continuation, labelled as such and kept separate from the saved plan (FR-023); the best-XI gain holds the selected gameweek's squad constant (FR-025).
- The selected gameweek is already completed or has no projections: explicit unavailable state (US1-8). Planned transfers remain possible through the Planner's own picker.
- The plan is already in financial shortfall: a candidate is acceptable if it introduces no new or worsened shortfall in any gameweek, per Planner Foundations Q-2; unchanged older shortfalls do not block it.
- The plan's outgoing player has an estimated purchase price: figures are provisional and say so; confirming the transfer does not confirm the estimate.
- A newer projection run appears while the Explorer is open: the session stays on its original run and tells the user a newer run exists; it does not silently mix runs.
- Player availability data (selectability) is unknown for any relevant candidate: the existing explicit refresh-required state is shown; playing status never decides eligibility (My Team UX FR-013, FR-013b).
- The plan is deleted or becomes unavailable while the Explorer is open: explicit "plan no longer exists" state; nothing is saved.
- Two browser tabs: latest accepted save wins as in Planner Foundations; a stale confirmation is reported as a conflict, not applied.

**Feature B**

- The original is renamed or deleted after the copy exists: the plans stay independent; the family naming of later duplicates uses current names only.
- Names near the 100-character limit: the base is shortened so the result fits (FR-050).
- The original has a financially unresolved gameweek or provisional prices: the copy carries the same saved inputs and shows the same derived status (FR-059).
- A save on the original is accepted by the server but not yet written (accepted-not-saved), including from another tab: duplication is blocked until it is resolved (FR-053).
- Two duplications of the same family run at once: both succeed with different names, or one fails with a retryable error; two plans never receive the same name (FR-055).
- An unsubmitted rename in progress is not part of the plan's saved state and is not copied.
- Duplicating from the Plans list is not offered in this phase.

## Requirements *(mandatory)*

Rule references reuse the registers in [Planner Foundations](../002-planner-foundations/spec.md) (`R-nn` FPL rules, `PC-nn` product constraints, `Q-n` decisions) and [My Team UX](../001-my-team-ux/spec.md). This specification does not restate or alter them.

### Functional Requirements

**Mode and context**

- **FR-001**: The Transfer Explorer MUST operate in exactly one of two explicit modes: My Team mode or Planner mode. Planner mode is identified by the plan and gameweek (and the outgoing player once chosen) being carried in the page address, so that reload, a new tab, and browser Back and Forward all restore the same mode and context.
- **FR-002**: The user MUST be able to tell which mode they are in at all times: Planner mode shows the plan name and gameweek; My Team mode shows no plan context.
- **FR-003**: In Planner mode, every squad, bank, free-transfer, chip, price and selling-price figure MUST come from the selected plan's evaluated state at the selected gameweek. Planner mode MUST NOT read or write the saved My Team squad, bank or free transfers.
- **FR-004**: My Team mode, its entry points from My Team, its endpoints and its behaviour MUST remain unchanged. Opening the Explorer without plan context MUST behave exactly as before this phase.
- **FR-005**: The Planner MUST let the user start exploration (a) from a specific player in the selected gameweek's squad, and (b) from the gameweek itself, in which case the Explorer offers that gameweek's squad players to choose from.
- **FR-006**: Plan and gameweek context MUST be preserved across exploring, changing horizon, previewing, closing a preview, confirming and returning to the Planner.
- **FR-007**: The Explorer MUST validate the plan, gameweek and outgoing player and show an explicit state for each failure: plan not found, plan awaiting initialisation, gameweek outside the plan, evaluation blocked for that gameweek, and outgoing player not in that gameweek's squad. It MUST NOT fall back to My Team.

**Squad state and candidate pool**

- **FR-008**: The squad used in Planner mode MUST be the squad the Planner shows for the selected gameweek, including that gameweek's other planned transfers. For a Free Hit gameweek this is the temporary squad.
- **FR-009**: The candidate pool MUST follow the same rules as My Team mode: same position as the outgoing player, not already in that gameweek's squad, and incoming selection permitted by authoritative FPL selectability data; playing status is advisory only; unknown selectability yields the explicit refresh-required state. The existing pool logic MUST be reused, not reimplemented. `[My Team UX FR-013, FR-013a, FR-013b]`
- **FR-010**: A player the plan sells in the same gameweek MUST appear as unavailable with that reason, because same-gameweek round trips are unsupported. `[PC-01]`
- **FR-011**: A candidate that fails a legality or affordability rule MUST stay visible, be marked unavailable with its reason(s), and remain previewable but not confirmable. `[My Team UX FR-014 to FR-016]`
- **FR-012**: The incoming-player selectability rule MUST be enforced authoritatively for every new or edited planned transfer in the shared Planner mutation path, not only when filtering the Explorer. Saved decisions MUST NOT be re-checked on replay, so a saved transfer is never invalidated because its incoming player later becomes non-selectable. A rejection MUST name the reason (non-selectable, or refresh required when selectability is unknown). `[Q-3; constitution principle I]`

**Finance and transfer accounting**

- **FR-013**: Planner-mode money MUST use the Planner's exact integer-tenths accounting, displayed in £m, with no floating-point financial arithmetic. `[Planner Foundations money rules]`
- **FR-014**: The outgoing player's sale value MUST be the official selling price derived from the plan's carried-forward purchase-price basis and the latest known market price, and the incoming cost MUST be the latest known market price, as for any new Planner transfer. `[002 FR-031, FR-033, FR-035, R-09]`
- **FR-015**: Each candidate and preview MUST show enough to audit the figures: purchase basis (with "Estimated" where assumed), market price used, selling price, incoming price, net bank change, resulting bank at the gameweek, and any shortfall.
- **FR-016**: Affordability and legality in Planner mode MUST be decided by the Planner's authoritative rules: squad validity for the gameweek, club limit, and no new or worsened financial shortfall in any gameweek of the plan, so that the Explorer can never offer as confirmable what the Planner would reject.
  A candidate that clashes with a later planned decision in the same plan (for example the plan later sells the outgoing player or buys the candidate) MUST remain visible, explorable and previewable, and MUST NOT be hidden or demoted in the ranking. It MUST be marked as blocked by a later planned decision, naming the affected gameweek and the clashing decision, and explaining why the transfer cannot currently be committed. Confirm MUST be disabled. The Explorer MUST NOT offer, build or run any automatic or guided repair (removing, replacing or retargeting the later decision), and no later decision is altered. `[002 Q-2, FR-040; Q-2]`
- **FR-017**: Free transfers, transfers made and points hit MUST come from the Planner's accounting. The Explorer MUST show the free transfers available, transfers made and hit before and after the transfer. Wildcard and Free Hit gameweeks MUST show unlimited, hit-free transfers; Bench Boost and Triple Captain gameweeks follow ordinary accounting. `[002 FR-018 to FR-024, R-06, R-07]`
- **FR-018**: Free Hit transfers MUST be shown as temporary (no effect after that gameweek); Wildcard and ordinary transfers MUST be shown as carried forward. `[R-10, R-11, R-12]`
- **FR-019**: Planner mode MUST NOT show the My Team "selling value approximated as current price" note, because it does not use that approximation.

**Projections and ranking**

- **FR-020**: Horizons MUST be anchored at the selected gameweek N: a 1-gameweek horizon is GW N, a 3-gameweek horizon GW N to N+2, a 5-gameweek horizon GW N to N+4. They MUST NOT be clipped to the plan's last gameweek.
- **FR-021**: The Explorer MUST state which gameweeks were actually evaluated for each horizon, MUST show partial coverage explicitly, and MUST NOT fabricate or zero-fill unavailable projections.
- **FR-022**: Replacement ranking MUST reuse the existing replacement-ranking logic (ordering by team gain over the primary horizon, stable tie-break, legality flags) fed with the plan's squad and money, rather than a separate ranking implementation. Any change to shared ranking behaviour MUST leave My Team mode's results identical.
- **FR-023**: Ranking in Planner mode MUST use the existing best-XI projected team gain over the horizon (the same measure My Team mode uses), MUST label it as such, and MUST remain the sole ranking measure. Separately, the Explorer MUST display the plan impact of each candidate: the difference between the plan's projected points with the transfer and without it, for each gameweek of the horizon, obtained by evaluating the plan with the transfer applied. Plan impact MUST reflect the transfer's valid consequences as the Planner would evaluate them, not a comparison of two players' raw projections: the incoming player takes the outgoing player's squad slot and so takes whatever role that slot has in each gameweek's saved lineup (starting, bench position, captain, vice-captain); planned chips and their effects, later planned decisions, and Wildcard and Free Hit carry-forward and reversion all apply. Plan impact is shown before points hit; the hit is shown separately (FR-029).
  For each horizon gameweek inside the saved plan, plan impact uses the plan's actual saved squad, lineup, bench and captaincy decisions for that gameweek. For horizon gameweeks after the plan's last gameweek, plan impact uses a hypothetical continuation built from the plan's final state after the transfer: the plan's permanent squad after its last gameweek (with the transfer applied wherever it carries forward, all later planned decisions applied, and a Free Hit in the final gameweek restored to the pre-Free-Hit squad) and the lineup roles saved for the plan's final gameweek, by slot, with no further transfers or chips. These gameweeks MUST be visibly labelled as an assumed continuation, MUST be totalled separately from the saved-plan gameweeks, and the interface MUST NOT imply the plan contains decisions beyond its horizon.
  Plan impact is shown in each preview and as a column in the candidate list; it is not a ranking key. The two figures MUST be labelled distinctly and MUST NOT be combined or substituted for one another. `[Q-1, Q-6]`
- **FR-024**: The projection model, run identifier and generation time MUST be visible. The model defaults to the same one My Team mode uses today (`component_v3`, latest run). The Explorer MUST NOT silently substitute another model, an older run or invented values, and MUST use one run for the ranking and every preview in a session. If a newer run appears, it MUST say so without switching silently. No model selector is introduced in this phase.
- **FR-025**: The best-XI ranking gain MUST hold the plan's squad at the selected gameweek constant across the horizon, independent of later planned decisions, and MUST be labelled as a static-squad measure. The plan impact (FR-023) is the measure that reflects later planned decisions, chips and Free Hit gameweeks.
- **FR-026**: For a Free Hit gameweek the horizon MUST be limited to that gameweek and the interface MUST say why.
- **FR-027**: If projections are unavailable for the selected gameweek, for the model, or for required squad players, the Explorer MUST show an explicit unavailable state that names the cause and offers no ranking.

**Preview**

- **FR-028**: Previewing a transfer MUST be read-only: it MUST NOT change any plan, My Team data or save-tracking state, and MUST NOT create mutation records.
- **FR-029**: A preview MUST show, for the selected gameweek: resulting bank, free transfers available, transfers made before and after, points hit before and after and the hit this transfer adds, the plan impact per gameweek and in total (before hit), the hit this transfer adds and the resulting net (plan impact minus the added hit), each clearly labelled, the best-XI ranking gain (FR-023), captain and vice-captain consequences, and any playing-status advisory.
- **FR-030**: A preview MUST show consequences for later gameweeks: which gameweeks change squad membership, bank, free transfers or hit, and any later planned decision that would become invalid. For a candidate blocked by a later planned decision the preview MUST show the valid information up to the first downstream conflict (the selected gameweek and any later gameweeks before the conflict, including their plan impact), MUST identify the affected gameweek and clashing decision, and MUST NOT present any later value that depends on the clash as if it were valid. The best-XI gain, being a static-squad measure, is unaffected. Later planned decisions MUST NOT be altered or repaired automatically.
- **FR-031**: The Explorer MUST visibly distinguish exploring or previewing an option from committing a planned transfer, using different wording and controls, and MUST describe the result of confirming in terms of the plan and gameweek.

**Commit**

- **FR-032**: Confirming a transfer MUST persist it only through the Planner's established mutation operation, expected-revision rules, retry identity and autosave coordination. No separate writer, no snapshot-based write and no direct persistence by the Explorer is permitted. `[002 contracts/planner-api.md]`
- **FR-033**: Confirmation MUST be authoritatively validated by the Planner domain at confirm time, never trusted from the preview. An invalid transfer MUST be rejected with the reason and affected gameweek, nothing persisted and the previous accepted state retained. Confirming a blocked candidate by any route MUST be rejected the same way. If either the outgoing player's or the incoming player's latest known market price differs from the one the user previewed, the confirmation MUST be rejected with a "prices changed" result, nothing saved, and a refreshed preview required; different financial assumptions MUST never be accepted silently. The previewed prices act only as a guard: the saved transfer always uses the server's own latest prices, never prices supplied by the browser. This guard applies to Explorer confirmations; the Planner's inline picker, which has no preview, is unchanged. `[Q-7; 002 Q-2, FR-040]`
- **FR-034**: A rejected transfer, a not-saved result, an unknown outcome and a revision conflict MUST be distinct states, each with a clear message, and MUST preserve the user's context. A not-saved transfer MUST remain visible and retryable with the same edit. A conflict MUST refresh the plan and require a new preview. `[002 FR-038 to FR-042]`
- **FR-035**: A confirmed transfer MUST be reported as saved only after the save is acknowledged. Repeated clicks and retries MUST create at most one transfer.
- **FR-036**: Confirming a transfer MUST NOT modify My Team's saved squad, bank or free transfers.
- **FR-037**: Confirming a transfer MUST recalculate every affected later gameweek through the Planner's replay, so no later free-transfer, hit, bank, squad or chip-availability value is stale. `[002 FR-027]`
- **FR-038**: When the outgoing player was acquired by a transfer already planned in the same gameweek, confirming a replacement MUST replace that planned acquisition rather than stacking a same-gameweek round trip, matching the Planner's existing behaviour.

**Navigation and highlighting**

- **FR-039**: After a saved confirmation the user MUST be returned to the Planner on the same plan and gameweek, with the incoming player highlighted and in view, and a message naming the transfer. Leaving without confirming MUST return to the same plan and gameweek with the plan unchanged.
- **FR-040**: The Planner MUST remember its selected gameweek when entering the Explorer and when returning from it, and MUST keep today's default gameweek when opened without that context.
- **FR-041**: The Explorer MUST warn before leaving while a confirmation is saving or not saved, consistent with the Planner's departure protection. `[002 FR-038]`
- **FR-042**: The Explorer MUST show loading, empty, unavailable-data, invalid-transfer and save-failure states, each distinct and worded for the plan context.

**Comparison controls**

- **FR-043**: Planner mode MUST let the user search candidates by name; filter by club, maximum price, "available to apply only" and playing status; and sort by gain at each horizon, price, resulting bank and upcoming fixture difficulty, with a stable tie-break. Active filters and the active sort MUST be visible and clearable.
- **FR-044**: Each candidate MUST show its fixtures over the selected horizon (opponent, home or away, difficulty rating) starting at the selected gameweek.
- **FR-045**: Searching, filtering and sorting MUST be re-presentations of server-computed results; the browser MUST NOT recompute legality, money, gains or fixtures. `[Constitution I]`
- **FR-046**: Comparison controls MUST NOT introduce new ranking models, saved filters, side-by-side comparison panels or other work belonging to Phase 004.

**Duplicate Plan**

- **FR-047**: The individual plan page MUST offer a "Duplicate Plan" control at the top right of the header row that holds the existing "Back to plans" link at the left, in the existing visual conventions, without otherwise redesigning the page.
- **FR-048**: Duplicating a plan MUST create a new plan with its own identity whose saved canonical state is a complete, independent copy of the original's, as specified in **Duplicate Plan Specification**. The original MUST NOT be modified (revision, update time, content and receipts unchanged).
- **FR-049**: The copy's name MUST follow the naming rules in **Duplicate Plan Specification**.
- **FR-050**: Names MUST fit the 100-character limit by shortening the base name, never by dropping or altering the "(option N)" suffix.
- **FR-051**: The duplicate MUST represent a consistent, successfully saved snapshot. The control MUST be disabled, with a reason, while the plan is saving, has an unsaved or failed edit, has a revision conflict, is missing, or is still loading. It MUST re-enable automatically when the plan is fully saved. There is no automatic "duplicate after saving" queue.
- **FR-052**: The request MUST identify the plan revision the user has seen saved, and the server MUST refuse to copy a different revision, so a copy can never silently omit committed changes.
- **FR-053**: The server MUST refuse to duplicate a plan that has an accepted-but-not-saved edit still resumable at the current revision, with an explicit reason. Stale, non-resumable receipts MUST NOT block duplication.
- **FR-054**: A plan awaiting Planner initialisation MUST NOT be duplicated and MUST NOT be initialised or modified by the attempt; the refusal MUST say initialisation is required.
- **FR-055**: Duplication MUST be atomic: either the complete new plan exists or nothing was created. Concurrent duplications MUST NOT produce two plans with the same name.
- **FR-056**: Repeated clicks MUST create one plan: the control MUST be disabled from the first click until the outcome is known. No database change is made solely to make retries idempotent. If the outcome is unknown (response lost or timed out), the interface MUST say so explicitly, state that a copy may already exist, link to the Plans list and MUST NOT retry automatically; the control becomes available again so the user can retry deliberately. `[Q-4]`
- **FR-057**: After success the user MUST be navigated to the new plan, with the original still reachable via browser Back, and shown the new plan's name and its source. After failure the user MUST stay on the original with a clear, specific error and no new plan.
- **FR-058**: The two plans MUST be fully independent: edits, renames, horizon changes, deletion or autosave on either MUST NOT affect the other, and they MUST NOT share any identifier that links their saved state.
- **FR-059**: Duplication MUST be available for a plan that is financially unresolved or has provisional prices; the copy MUST show the same derived status.

### Duplicate Plan Specification

**What is copied (saved canonical inputs, verbatim)**

- Horizon (first and last gameweek).
- Starting boundary: the 15 starting players with their stable lineup slots; each player's purchase price, source, original price, basis kind and confirmation status (including "assumed" and "user-confirmed"); starting bank; starting free transfers; chips declared used before the plan; the Free Hit gameweek 19 declaration; the boundary's origin and bank-assumption markers.
- For each gameweek: the planned chip; the starting XI, bench order, captain and vice-captain (the slot-based lineup).
- All planned transfers: outgoing and incoming players, which owned-player episode is being sold, saved market assumption for the outgoing player, saved acquisition price, observation source and time, origin, and the saved selling-price result.

**What is not copied**

- Mutation receipts (pending or committed), mutation identifiers and their digests. The copy starts its own history at revision 0 with no receipts, so nothing can be replayed or collide.
- Derived and quarantined data: evaluated squads, banks, free transfers, hits, chip availability, financial status, projections, and the legacy snapshot and accounting rows kept only for migration.
- Anything from My Team. The copy is never reconstructed from My Team; saved prices are not refreshed, so live market changes after the original was created do not alter the copy.
- Unsubmitted editor text such as a rename not yet submitted.

**What is regenerated**

- Plan identifier, creation and update times, name, revision.
- Every internal identifier that links parts of the plan together (lineup slots, owned-player episodes, transfer decision identifiers, and the bank-assumption markers that reference them), remapped consistently so every reference inside the copy points at the copy's own identifiers and none points at the original's.

**Equivalence guarantee (acceptance test)**: read at the same moment, the copy and the original MUST show identical evaluated results (per-gameweek squad, lineup, bank, free transfers, transfers made, hit, chip availability, financial status and decision errors), differing only in plan identifier, name, revision and internal identifiers.

**Naming rules**

1. The **family base** is the source plan's name with leading and trailing whitespace trimmed and a single trailing " (option N)" removed, where N is a whole number of 2 or more without leading zeros. "My Plan" and "My Plan (option 3)" share the base "My Plan". Only one suffix is removed, so a name that already had two is handled by removing the last.
2. A plan is a **member** of a family if its name equals the base (counted as option 1) or the base followed by " (option N)". Comparison is exact and case-sensitive.
3. The new name is the base followed by " (option N)" where N is one more than the highest option number among the members that currently exist, so the first duplicate of "My Plan" is "(option 2)". Numbers freed by deletion may therefore be reused (if "(option 3)" was the highest and is deleted, the next copy is "(option 3)" again; if only "(option 2)" is deleted while "(option 3)" remains, the next copy is "(option 4)"). No record of deleted names or numbering counters is kept. `[Q-5]`
4. If that name already exists for any reason, N increases until the name is unused, so the result is always unique and deterministic for a given set of existing names.
5. If the base and suffix would exceed 100 characters, the base is shortened (and trailing whitespace trimmed) so the whole name fits; the suffix is never shortened. The family for such a name is then computed from the shortened base.
6. Renamed plans are judged by their current names only: if the original was renamed, it is no longer a family member; its copies keep their names.
7. Names are not required to be unique outside this rule; renaming remains free-form as today. No link between a copy and its source is stored.

**User interaction**

| State of the original plan | Duplicate Plan control |
|---|---|
| Loading, or plan missing | Not offered / disabled |
| Saved, nothing pending | Enabled |
| Saving, queued edits | Disabled: "Waiting for changes to save"; re-enables when saved |
| Not saved (retryable failure), or save outcome unknown | Disabled: "Resolve the unsaved edit before duplicating", with the existing retry and check-status actions beside it |
| Revision conflict | Disabled: "Reconcile with the current plan first" |
| Awaiting Planner initialisation | Disabled: "This plan must be initialised before it can be duplicated" |
| Duplication in progress | Disabled, shows "Duplicating..." |

**Failure behaviour**

| Failure | Result |
|---|---|
| Original changed since the user saw it (revision mismatch) | Refused; message asks the user to reload the plan; nothing created |
| Original has a resumable accepted-but-not-saved edit | Refused with explicit reason; nothing created |
| Original awaiting initialisation | Refused with explicit reason; original untouched |
| Original deleted meanwhile | Refused as plan not found; nothing created |
| Any storage failure during creation | Whole operation rolled back; no new plan; original untouched; user sees a retryable error |
| Response lost / outcome unknown | Message says the outcome is unknown, that a copy may already exist, and links to the Plans list; no automatic retry; the control is available again |

### Key Entities

- **Explorer Context**: the mode (My Team or Planner), and in Planner mode the plan, the gameweek and the outgoing player, carried in the page address.
- **Plan Gameweek Squad State**: the squad, lineup, bank, free transfers, chip and cost bases the Planner shows for one gameweek; the sole financial and squad input in Planner mode.
- **Planner Replacement Candidate**: a pool player evaluated for one outgoing player in one plan gameweek: price, selling-price breakdown, resulting bank, best-XI gains by horizon, plan impact, upcoming fixtures, legality and unavailability reasons, status advisory, and any clash with later planned decisions.
- **Plan Impact**: the difference in the plan's projected points, per horizon gameweek and in total, between the plan with a candidate transfer applied and the plan without it, split into saved-plan gameweeks and assumed-continuation gameweeks, shown before points hit.
- **Planned Transfer Preview**: the read-only account of what confirming a candidate would do to that gameweek and later ones.
- **Projection Source**: model, run identifier, generation time and the gameweeks actually evaluated for the session.
- **Plan Family**: plans sharing a base name; the scope of "(option N)" numbering.
- **Duplicate Request**: one user action to copy one plan revision, with its outcome (created plan, or refusal reason).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A manager can go from a player in a plan gameweek to a preview of a replacement, and from there to a saved transfer, without re-selecting the plan, gameweek or outgoing player.
- **SC-002**: In reference scenarios covering ordinary, Wildcard, Free Hit, Bench Boost and Triple Captain gameweeks, an estimated purchase price, a first-gameweek transfer, a zero-free-transfer start and a transfer that exceeds the free transfers, the Explorer's previewed bank, free transfers, hit and later-gameweek effects match independently hand-calculated values and the Planner's values after confirmation in 100% of cases.
- **SC-003**: In 100% of attempts, anything the Explorer shows as confirmable is accepted by the Planner, and anything the Planner rejects is shown as unavailable or rejected with a reason; none is saved.
- **SC-004**: After confirming a planned transfer, My Team's saved squad, bank and free transfers are unchanged in 100% of cases, and previewing alone changes no saved data.
- **SC-005**: For horizons anchored at gameweek N, the evaluated gameweeks shown equal exactly the available subset of N to N+h-1 in 100% of reference cases, and no unavailable projection is ever shown as a number.
- **SC-006**: A manager can always tell, without leaving the Explorer, which model and projection run produced the figures, which gameweeks were evaluated, and whether any are missing.
- **SC-007**: After confirming or backing out, the manager is back on the same plan and gameweek in 100% of cases, including after a reload inside the Explorer.
- **SC-008**: A not-saved, conflicted or rejected transfer is never presented as saved, and an interrupted confirmation is never lost silently.
- **SC-009**: With a realistic candidate pool, a manager can find a named player, or narrow to affordable candidates from one club, using search and filters, and re-order them, without leaving the list.
- **SC-010**: A duplicate is created in one action once the plan is saved, and the manager lands on it. The copy's saved inputs match the original's, and its derived results match exactly, in 100% of reference plans (with transfers, chips, estimated prices, financial shortfalls and Free Hit gameweeks).
- **SC-011**: Over repeated and concurrent duplication, 0 plans share a name within a family, 0 duplicates are created by repeated clicks, and 0 partial plans exist after any injected failure.
- **SC-012**: Duplicating never modifies the original (revision, update time, content, receipts), and edits to either plan never appear in the other.
- **SC-013**: The My Team Transfer Explorer, My Team and the existing Planner journeys keep passing their existing automated tests, and the main new journeys pass in a real browser at desktop and mobile widths.
- **SC-014**: On the representative local dataset (a full-season player pool with a current projection run and a plan of up to 8 gameweeks), the Planner-mode candidate list is shown within 3 seconds and an individual preview within 2 seconds, with a visible loading state until then. A longer plan (up to 38 gameweeks) is measured and reported but is not a gate. These are measurable verification targets; optimisation beyond what is needed to meet them is not required. `[Q-8]`
- **SC-015**: In reference scenarios in which the outgoing player's role differs between gameweeks (starting, benched, captain), with Bench Boost, Triple Captain, Wildcard and Free Hit gameweeks, with a horizon extending beyond the plan's end, and with a blocked candidate, the displayed plan impact matches independently hand-calculated values in 100% of cases, assumed-continuation gameweeks are always labelled as such, and no value depending on a downstream conflict is shown as valid.

## Assumptions

- **Single-user context.** One manager owns all plans; two browser tabs are not specially protected beyond the Planner's existing conflict handling.
- **Same projection source.** Planner mode uses the model and latest-run policy My Team mode uses today; no model selector is added. The Planner page's own xPts use the same model and policy but the Planner does not currently display the run, so the Explorer's run label is the explicit disclosure for this phase.
- **Static-squad ranking measure.** The best-XI ranking gain describes the selected gameweek's squad held through the horizon (FR-025). The plan impact is the measure that follows the plan's own later decisions; full multi-gameweek replanning and optimisation remain out of scope. For the assumed continuation after the plan's end the squad is the plan's permanent squad after its last gameweek (after the transfer, all later planned decisions and any Free Hit restoration) and the lineup roles are those saved for the plan's final gameweek, applied by slot; the continuation contains no further transfers or chips.
- **Prices are never predicted.** New transfers use the latest known market prices; saved decisions keep their saved prices. `[002 Q-4]`
- **Selectability is latest-known.** Incoming eligibility uses the latest imported data, the same data My Team mode uses, including for future gameweeks.
- **Completed gameweeks.** Completed gameweeks remain editable in the Planner `[002 Q-5]`, but have no projections, so the Explorer shows its unavailable state for them.
- **Hits.** The Explorer shows the marginal hit a transfer causes. Ranking is by best-XI xPts gain and is not hit-adjusted; plan impact is shown before hit, with the hit and the resulting net shown separately (FR-029).
- **Representative dataset.** Performance targets (SC-014) are measured on a full-season import with a current projection run, not on trimmed test fixtures.
- **Accessibility and viewports.** New screens meet the keyboard, tap-target and 1440 and 390 pixel width expectations already verified for Planner Foundations.
- **No new infrastructure.** No new dependencies or services. No database schema change is required or planned; in particular none is made solely for duplication idempotency. Any schema change would require an Alembic migration and the human's agreement first.
- **Tests.** Database-touching tests use the dedicated test database through `TEST_DATABASE_URL` and the existing safeguards; nothing runs against development data. `[Constitution VII]`
- **Duplication placement.** Only the plan page offers Duplicate Plan in this phase; the Plans list does not.
- **Existing inline Planner picker.** It stays as it is, except that new or edited transfers from it are subject to server-side rules added by this phase (FR-012).

## Out of Scope

- Broader UI/UX improvements and redesign (Phase 004), including side-by-side comparison of plans or candidates.
- Historical plan evaluation against actual gameweek results (Phase 005).
- Changes to projection models, new models, or a model selector.
- Optimal multi-gameweek transfer optimisation, automated replanning, or automatic chip or transfer suggestions.
- Historical reconstruction of My Team.
- Redesign of the inline Planner transfer picker beyond the server-side rules in FR-012.
- Duplicate Plan from the Plans list, a stored link between a copy and its source, bulk duplication, and any persisted history of deleted option numbers.
- Changing the My Team Transfer Explorer's selling-price approximation or ranking behaviour.
- Predicting future price changes.
