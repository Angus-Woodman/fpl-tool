# Phase 004 Product Vision: Branching Scenario Planner

**Status**: Product vision. **Not** a Spec Kit feature specification, implementation plan or task list. Written 2026-10-28 while the product decisions were fresh, so formal specification can start later without rediscovering them.

**Relationship to other phases**: Phase 003 (Planner-aware Transfer Explorer, [spec](../003-planner-transfer-workflow/spec.md)) comes first and works on the existing linear Planner. This document describes what Phase 004 will change. Earlier roadmap labels that used "Phase 004" for a broader UI redesign and "Phase 005" for historical plan evaluation are superseded by this numbering; those two ideas remain wanted but are unnumbered for now.

**Spec Kit note**: when Phase 004's formal specification is started, use this directory explicitly (`specs/004-branching-scenario-planner`); sequential feature numbering would otherwise skip it. The active Spec Kit feature remains Phase 003.

**How to read this**: sections 1 to 6 are agreed product direction. Section 7 is high-level implication, not design. Section 8 lists what is still open and must be resolved when Phase 004 is formally specified. Section 9 draws the boundary with Phase 003.

---

## 1. The problem and who benefits

The current Planner is a single straight line: one squad, one set of decisions per gameweek, one future. Planning one fixed sequence of transfers many gameweeks ahead has limited value, because injuries, results, availability, prices and other developments routinely invalidate earlier assumptions. When something changes, the manager needs to ask "what if I did this instead, and what then?" about several possible futures, and keep them side by side.

Today the only way to compare strategies is to create entirely independent plans, which loses how each scenario was reached and forces the manager to rebuild shared history again and again.

**Intended benefits**

- Explore several possible futures inside one plan, each reachable from a common starting point.
- Always see how a scenario was reached, not just where it ended up.
- Keep scenarios independent, so working on one never disturbs another.
- Make a commitment explicit: a saved option is a firm statement of one possible set of decisions.
- Plan the way FPL is actually played: decide this gameweek, keep alternatives for the next, revisit when news arrives.

## 2. Fundamental concepts

| Term | Meaning |
|---|---|
| **Plan** | The whole planning workspace: a common starting state (squad, bank, free transfers, chip state) and a tree of options over a range of gameweeks. |
| **Option** | One possible set of decisions for one gameweek, in one specific line of play: transfers, lineup (starting XI and bench order), captain, vice-captain and chip use. |
| **Parent** | The option in the preceding gameweek that an option follows. Every option has exactly one parent. Options in the first gameweek follow the plan's starting state. |
| **Child** | An option that follows a given parent. An option may have many children, which is how branching happens. Options sharing a parent are **siblings**. |
| **Draft** | An option that is still being edited. Drafts autosave reliably. |
| **Saved option** | A draft that has been committed. It is immutable: it can never be edited in place. |
| **Selected path** | The chain of options from the first gameweek down to the option currently being viewed. It determines the one squad on screen. |
| **Scenario** | One complete line of play, i.e. a path. "Scenario" always means a path; "option" always means a single node. |
| **Scenario tree** | All options in a plan with their parent and child relationships: the set of possible futures. |

**State is a consequence, not stored authorship.** An option records decisions only. The squad, bank, free transfers, hits and chip availability at that option are consequences of those decisions together with the starting state and the decisions of its ancestors. Nobody authors a complete squad per option.

## 3. The agreed UX model

One Planner page offers two complementary views. Switching between them is easy and always restores exactly where the user was (same gameweek, same option).

### 3.1 Selected scenario view (primary working interface)

- Shows **one gameweek, one selected option and one squad**. It never shows two squads at once.
- A lightweight **scenario path** shows compact summaries of the decisions that led to the current option (for example "GW7: Salah to Palmer; GW8: no changes; GW9: Wildcard").
- The **other options at the current gameweek** (siblings) appear as concise action summaries ("Haaland to Isak; captain Palmer"), never as squads. The user can switch to a sibling.
- All editing happens here, on a draft.
- The Transfer Explorer is reached from here and operates on exactly this option (section 3.5).

### 3.2 Tree overview

- Shows the broader branching structure so the user can understand how scenarios relate: which options share which ancestors, where branches split, where drafts exist.
- Supports expanding and collapsing branches.
- Supports comparing possible paths. What is compared (see section 8) must be per path; values from different branches are never merged, averaged or otherwise blended.
- Selecting a node here is an explicit navigation action (open question 8.2 confirms the exact rule).

### 3.3 Sequential navigation

Arbitrary gameweek jumping is replaced by **Previous GW** and **Next GW**.

- **Previous GW** moves to the current option's parent.
- **Next GW** continues along the descendants of the selected option.
- **At a gameweek, switch among siblings** (options with the same parent).
- To explore a branch that descends from a *different earlier* option, the user navigates **backwards** to the relevant branching point and follows the alternative forwards. The selected scenario view never silently switches between incompatible branches.
- **No children yet:** Next GW offers to continue into the next gameweek. Continuing must not require a transfer or any other change; the user can simply carry on, which creates a new draft for the next gameweek with no decisions.
- **Several children:** Next GW follows the child the user last viewed along this path (remembered), or if none has been viewed, a clearly defined default; the view always shows how many sibling options exist at the next gameweek, so the user is never unaware that alternatives exist.
- Going Previous then Next returns to where the user came from (the remembered child).

### 3.4 Draft to saved lifecycle (accepted product decision)

- A **draft** is editable and autosaves with the same reliability expectations as Planner Foundations (clear saved, saving and not-saved states; failures never silent).
- **Saving** a draft commits it as an **immutable saved option**.
- A saved option **cannot be edited in place**.
- To revise a saved option, the user creates a **new draft alternative** pre-populated with that option's decisions. Existing saved options and all their descendants remain exactly as they were.
- **Deleting** an option deletes all of its descendants, after a clear confirmation that states what will be removed (for example "This removes this option and 6 later options").
- Changes to one branch never silently modify any unrelated branch.

**UX implications, documented and accepted, not to be reopened without a substantial problem:**

- Revising a mid-path option means creating an alternative; the original descendants stay with the original. The user must rebuild later gameweeks on the new alternative if they want them. This is the price of guaranteeing that saved scenarios never change underneath the user.
- Small corrections to a saved option (a wrong captain) also require an alternative. The tree can accumulate near-duplicate options; the tree overview and deletion are the tools for keeping it tidy.
- Immutability makes every saved scenario trustworthy as a record of what was decided, which is the property the product is choosing over editing convenience.
- Drafts are the safe space: nothing a user does in a draft affects other options until it is saved.

### 3.5 Scenario-aware Transfer Explorer

- Transfer exploration targets an **exact option** and the state inherited along its path.
- Hypothetical evaluation, rankings, previews and projections operate on that selected path only. Different downstream branches are never accidentally combined or averaged.
- **Applying a transfer** modifies a draft, or explicitly creates a draft alternative; it never silently edits an immutable saved option. When the viewed option is saved, the user is told that applying will create a draft alternative and confirms it.
- The existing authoritative Planner rules (squad legality, chips, free transfers, selling prices, price assumptions) remain the rules, reused as they are.

## 4. Example user journeys

**J1. Building a first path.** The manager creates a plan from GW7 to GW12 from their current team. In GW7 they transfer Salah for Palmer and set Haaland as captain; the draft autosaves; they save it. Next GW offers to continue; they choose to carry on with no changes into GW8, save, and so on to GW12. The scenario path now reads as a short line of summaries.

**J2. Branching at a gameweek.** At GW9 the manager is unsure whether to use the Wildcard now or later. On the GW9 option they create a sibling draft with the Wildcard and a rebuilt squad, and save it. The page shows "2 options at GW9". Switching between them swaps the single squad on screen; the other option appears only as a summary.

**J3. Exploring an alternative from an earlier branching point.** Midway through GW11 on the Wildcard scenario, news breaks that a GW8 transfer target is injured. The manager presses Previous GW back to GW8 (the branching point), creates a sibling draft there with a different transfer, saves, then follows Next GW forwards on this new alternative. The original path and its GW9 to GW11 options are untouched. They cannot reach the new branch by jumping from GW11; they must go back to GW8.

**J4. Editing a draft.** The manager changes captaincy in a draft and swaps two bench players. Each change autosaves; if a save fails, the draft shows "not saved" with a retry, and leaving warns them. When happy they save; the option becomes immutable.

**J5. Revising a saved option.** On a saved GW9 option the manager wants a different captain. The captain control explains that this option is saved and offers "Create draft alternative". They confirm; a draft sibling appears pre-populated with the original's decisions; they change the captain and save. The original GW9 option and its GW10 to GW12 descendants are unchanged; the new option has no descendants yet.

**J6. Deleting an option.** The manager no longer wants the Wildcard branch. They delete the GW9 Wildcard option; a confirmation states that the option and its 3 descendants will be removed. After confirming, the sibling remains selected and the tree shows no trace of the deleted branch; other branches are untouched.

**J7. Switching views.** From GW10 on a particular option, the manager opens the tree overview, collapses the branches they do not care about, compares two paths, then returns to the selected scenario view and lands on GW10 and the same option.

**J8. Using the Transfer Explorer.** On a draft GW10 option, the manager opens the Explorer; candidates, selling prices, free transfers and projections reflect that option's inherited path. They add a transfer; it goes into the draft. On a saved option, the Explorer's apply step first offers "Create draft alternative", and only then adds the transfer to that new draft.

## 5. Interaction principles

1. **One squad at a time.** The working view shows exactly one squad. Comparison across options happens through summaries and the tree overview, never by showing multiple squads in the working view.
2. **Branches are explicit.** Moving between branches is always a visible, deliberate action. The view never changes branch as a side effect of another action.
3. **Decisions in, consequences out.** Users author decisions; the system derives squads and finances.
4. **Saved means firm.** Saved options are a record; drafts are working space. The state of an option (draft or saved) is always visible.
5. **Never lose or hide work.** Save status is clear; destructive actions state their consequences; leaving with unsaved work warns.
6. **Never blend branches.** No averaging, summing or merging across scenarios.
7. **Reasonable defaults, explicit alternatives.** Carrying on with no changes is the easy path; creating alternatives is a deliberate act.
8. **Rules are the Planner's rules.** The existing authoritative FPL rules and money handling apply unchanged.

## 6. Invariants (must hold at all times)

1. Every option has exactly one parent: the plan's starting state for the first gameweek, otherwise an option in the preceding gameweek.
2. An option's squad, bank, free transfers, hits and chip availability are fully determined by the starting state and the decisions on its path; they are never separately authored or stored as independent truth.
3. Saved options are immutable. Only drafts are editable.
4. Editing, saving, creating alternatives or deleting in one branch never changes the decisions or derived state of any option that is not its descendant. Descendants are only ever removed by deleting an ancestor.
5. The selected scenario view shows exactly one squad and never switches branches silently.
6. Deleting an option deletes all of its descendants and requires a confirmation that states the consequences.
7. Navigation is restorable: leaving and returning (including switching views) restores the same gameweek and option.
8. Validity is enforced by the authoritative Planner rules, not by the interface alone.
9. Saved decisions keep the price assumptions they were saved with; refreshes of market data never reprice them (carried forward from Planner Foundations).
10. Autosave never fails silently, and a failed or pending draft is never presented as saved.

## 7. High-level implications (not design)

**For the data model and architecture**

- Planner Foundations stores one linear sequence of per-gameweek decisions per plan. Phase 004 attaches decisions to options with a parent relationship instead. Derived state moves from "per plan" to "per path".
- Evaluation continues to be a replay of decisions from the common start; it now replays along a selected path. The existing authoritative evaluation and rule code is expected to be reused by presenting a selected path as a linear sequence.
- Immutability is a domain rule that must be enforced in the authoritative layer, not by the interface alone. Revisions, retry identity and conflict handling (today per plan) need a new home that fits drafts and saved options.
- Chips, free transfers and financial status become per-path facts: the same chip can be used on different paths, but at most once per period along any one path.
- Deletion is a subtree operation.
- Existing linear plans must have a defined future (section 8.6).
- Projection-based figures (plan impact, assumed continuation) are computed per selected path.

**For the existing Planner and the Phase 003 Transfer Explorer**

Phase 003 deliberately separates resolving the planning context from analysing it, keeps analysis read-only, and hands confirmations to the Planner's own writer as a descriptor. In Phase 004 that means: replace the context resolver (an option and its path instead of a plan gameweek), extend the context identity returned by the Explorer with the option, point the commit adapter at drafts (creating a draft alternative from saved options), redefine "later planned decisions" and "plan end" for continuation as "descendants on the selected path" and "end of the selected path", and replace Phase 003's gameweek-based return navigation with option-aware navigation. The candidate pool, selectability, price guard, ranking, hypothetical evaluation and plan-impact logic are expected to carry over. The full adaptation list is in the Phase 003 plan.

## 8. Risks, trade-offs and questions for Phase 004's specification

**Risks and trade-offs**

- **Immutability friction** (accepted): near-duplicate options, rebuilding descendants after revisions. Mitigated by clear drafts, summaries, and tidy-up through deletion. A later "carry descendants forward" aid may be worth considering; it is not part of this vision.
- **Tree growth and legibility:** without limits or good collapsing, the tree can become unmanageable.
- **Cognitive load of branching:** users must always know where they are (gameweek, option, path) and that siblings exist.
- **Comparison without blending:** deciding what can be compared across paths without implying a single "best" or an average.
- **Migration risk:** existing linear plans and Planner Foundations guarantees must survive the change.
- **Performance:** replaying along a path, and ranking candidates, must remain responsive as trees grow.
- **Complexity of autosave** across many drafts and one immutable history.

**Product questions to resolve in the formal specification** (each with a leaning, not a decision)

1. **Can a draft have children?** Leaning: no. Only saved options can be parents, because a parent that can still change would invalidate its descendants, contradicting the invariants. Consequence: continuing past a draft means saving it first ("Save and continue").
2. **Can the tree overview jump directly to any option?** Leaning: yes. Selecting a node is an explicit action that sets the whole selected path, so it is not a silent branch switch; the selected scenario view itself still only moves with Previous, Next and sibling switching.
3. **Default child for Next GW** when several exist and none was viewed: most recently saved, or the first created? Leaning: most recently saved.
4. **How many drafts at once?** One draft per parent, or several? Leaning: several, since drafts are cheap and isolated.
5. **What must a draft satisfy before it can be saved?** Leaning: full authoritative validity (legal squad, affordable); invalid work stays a draft. How this interacts with financial states that Planner Foundations allowed to persist (such as shortfalls exposed by price corrections) needs a decision.
6. **What happens to existing linear plans?** Leaning: each becomes a single saved path. Needs an explicit rule for existing in-place editing, which Phase 003 still uses, and for plans awaiting initialisation.
7. **Option labelling:** automatic summaries only, or optional user names? Leaning: automatic summaries plus optional label.
8. **What can the tree overview compare?** Candidate measures: cumulative projected points, hits taken, bank, free transfers, chips used, along each path. Leaning: per-path measures only, side by side, never aggregated across branches.
9. **Limits:** maximum options per gameweek or depth; how to degrade gracefully.
10. **Chips across branches:** confirm per-path once-per-period semantics and how the interface explains availability on a path.
11. **Revising with descendants:** is there ever an affordance to re-apply a subtree to a new alternative? Leaning: out of Phase 004, revisit after use.
12. **Deleting a parent of a draft** that the user is editing: confirmation wording and behaviour.
13. **Relationship to historical evaluation:** how saved options might later be compared to actual results (a future phase).
14. **Name of the page and navigation** (scenario tree versus plan), left to design.

## 9. Boundaries: Phase 003 and Phase 004

| Topic | Phase 003 (delivers) | Phase 004 (introduces) |
|---|---|---|
| Plan shape | Existing linear plan, one set of decisions per gameweek | Scenario tree: several options per gameweek, each with one parent |
| Navigation | Planner keeps its current gameweek selection; Explorer context and return carry plan and gameweek | Previous GW and Next GW along a selected path; sibling switching; no arbitrary jumping in the working view |
| Editing model | Confirmed transfers are applied to the plan through the existing mutation system | Drafts are editable and autosaved; saved options are immutable; alternatives are explicit drafts |
| Transfer Explorer | Plan-aware: explore, rank, preview, confirm in a plan gameweek; separated analysis, context resolution and commit; read-only analysis | Option-aware: explores an exact option and its path; confirms into a draft or creates a draft alternative |
| Views | Existing Planner page | Selected scenario view plus tree overview |
| Deleting | Plan deletion as today | Option deletion removes descendants with confirmation |
| Duplicating a plan | Not delivered (withdrawn; earlier design preserved in Git history) | Largely addressed by branching; revisit only if a real need remains |
| Chips, finances, free transfers | Planner Foundations rules on the linear plan | Same rules evaluated per path |
| Projection horizon beyond the plan | Assumed continuation from the plan's final state, labelled and separately totalled | Redefined along the selected path (see section 7) |
| My Team Transfer Explorer | Unchanged | Unchanged |
| Database | No schema change | Substantial data-model change (to be specified) |

What Phase 003 explicitly does **not** do for Phase 004: no option or branch types, no option identifiers in contracts, no draft or saved distinction, no tree navigation, no feature flags. It only keeps context resolution, analysis and commit apart so that those later changes touch the edges.
