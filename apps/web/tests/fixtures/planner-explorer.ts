import type {
  PlanExplorerCandidate,
  PlanExplorerHorizonInfo,
  PlanExplorerImpact,
  PlanTransferExplorerResponse,
} from "../../src/lib/api";

import { plannerIdentity } from "./planner";

export { buildPlannerPlan, deferred, plannerIdentity } from "./planner";

export const EXPLORER_PLAN_ID = 7;
export const EXPLORER_GAMEWEEK = 9;
export const EXPLORER_OUTGOING_ID = 6;
export const EXPLORER_RUN_ID = 42;

const HORIZON_KEYS = ["1", "3", "5"] as const;

/** Full coverage for GW9 (1), GW9-11 (3) and GW9-13 (5); GW12-13 are assumed. */
export function buildExplorerHorizons(
  overrides: Partial<Record<1 | 3 | 5, Partial<PlanExplorerHorizonInfo>>> = {},
): PlanExplorerHorizonInfo[] {
  const base: PlanExplorerHorizonInfo[] = [
    {
      horizon: 1,
      requested_gameweeks: [9],
      evaluated_gameweeks: [9],
      saved_plan_gameweeks: [9],
      assumed_gameweeks: [],
      partial: false,
    },
    {
      horizon: 3,
      requested_gameweeks: [9, 10, 11],
      evaluated_gameweeks: [9, 10, 11],
      saved_plan_gameweeks: [9, 10],
      assumed_gameweeks: [11],
      partial: false,
    },
    {
      horizon: 5,
      requested_gameweeks: [9, 10, 11, 12, 13],
      evaluated_gameweeks: [9, 10, 11, 12, 13],
      saved_plan_gameweeks: [9, 10],
      assumed_gameweeks: [11, 12, 13],
      partial: false,
    },
  ];
  return base.map((info) => ({ ...info, ...overrides[info.horizon] }));
}

export function buildImpact(
  overrides: Partial<PlanExplorerImpact> = {},
): PlanExplorerImpact {
  return {
    saved_plan: 3.5,
    assumed_continuation: 2.5,
    net_saved_plan: -0.5,
    valid_through_gameweek: null,
    ...overrides,
  };
}

export function buildExplorerCandidate(
  overrides: Partial<PlanExplorerCandidate> & { player_id: number },
): PlanExplorerCandidate {
  return {
    web_name: `Cand ${overrides.player_id}`,
    team_short_name: "LIV",
    position: "MID",
    status: "a",
    price_tenths: 62,
    state: "available",
    reasons: [],
    conflict: null,
    valid_through_gameweek: null,
    resulting_bank_tenths: 8,
    points_hit_after: 0,
    best_xi_gain_by_horizon: { "1": 1.5, "3": 3.2, "5": 5.5 },
    direct_xpts_difference: 1.2,
    plan_impact_by_horizon: {
      "1": buildImpact({ saved_plan: 1.5, assumed_continuation: null }),
      "3": buildImpact({ saved_plan: 3.2, assumed_continuation: 1.5 }),
      "5": buildImpact(),
    },
    fixtures: [
      {
        gameweek: 9,
        opponent_short_name: "BOU",
        is_home: true,
        difficulty: 2,
      },
    ],
    ...overrides,
  };
}

export function buildAvailableCandidate(): PlanExplorerCandidate {
  return buildExplorerCandidate({
    player_id: 101,
    web_name: "Available Alex",
  });
}

export function buildUnavailableCandidate(
  reasons: string[] = ["financial_shortfall"],
): PlanExplorerCandidate {
  return buildExplorerCandidate({
    player_id: 102,
    web_name: "Unavailable Uri",
    state: "unavailable",
    reasons,
    price_tenths: 95,
    resulting_bank_tenths: null,
    points_hit_after: null,
    plan_impact_by_horizon: {
      "1": buildImpact({
        saved_plan: null,
        assumed_continuation: null,
        net_saved_plan: null,
      }),
      "3": buildImpact({
        saved_plan: null,
        assumed_continuation: null,
        net_saved_plan: null,
      }),
      "5": buildImpact({
        saved_plan: null,
        assumed_continuation: null,
        net_saved_plan: null,
      }),
    },
  });
}

export function buildBlockedCandidate(): PlanExplorerCandidate {
  return buildExplorerCandidate({
    player_id: 103,
    web_name: "Blocked Ben",
    state: "blocked_by_later_decision",
    reasons: [],
    valid_through_gameweek: 10,
    conflict: {
      kind: "structural",
      gameweek: 11,
      decision_id: plannerIdentity(9011),
      code: "sold_this_gameweek",
      message: "Ben is sold by a planned transfer in GW11.",
      shortfall_tenths: null,
    },
  });
}

export function buildPlannerExplorerResponse(
  overrides: Partial<PlanTransferExplorerResponse> = {},
): PlanTransferExplorerResponse {
  return {
    planning_context: {
      plan_id: EXPLORER_PLAN_ID,
      gameweek: EXPLORER_GAMEWEEK,
      revision: 3,
    },
    plan: {
      plan_id: EXPLORER_PLAN_ID,
      name: "Run-in plan",
      revision: 3,
      start_gameweek: 9,
      end_gameweek: 14,
      gameweek: EXPLORER_GAMEWEEK,
      chip: null,
      evaluator_version: "planner-foundations-1",
    },
    projection: {
      model_version: "component_v3",
      run_id: EXPLORER_RUN_ID,
      generated_at: "2026-08-16T08:10:00+00:00",
      newer_run_available: false,
      primary_horizon: 5,
      horizons: buildExplorerHorizons(),
      limited_to_selected_gameweek: false,
      limited_reason: null,
      unprojected_candidate_ids: [],
    },
    accounting_before: {
      starting_bank_tenths: 15,
      closing_bank_tenths: 15,
      free_transfers_available: 2,
      transfers_made: 0,
      points_hit: 0,
      unlimited_transfers: false,
      provisional: false,
    },
    outgoing: {
      player_id: EXPLORER_OUTGOING_ID,
      web_name: "P6",
      position: "MID",
      team_short_name: "T6",
      ownership_id: plannerIdentity(1006),
      operation: "add_transfer",
      replaces_decision_id: null,
      purchase_price_tenths: 50,
      purchase_basis: { basis_kind: "starting", confirmation: "assumed" },
      market_price_tenths: 54,
      selling_price_tenths: 52,
      selling_provisional: true,
      projected_points_by_horizon: { "1": 2, "3": 6, "5": 10 },
    },
    candidates: [
      buildAvailableCandidate(),
      buildUnavailableCandidate(),
      buildBlockedCandidate(),
    ],
    ...overrides,
  };
}

/** Preview payload (US2 reads it); kept untyped until the preview client lands. */
export function buildPlannerPreviewPayload(playerInId = 101) {
  const explorer = buildPlannerExplorerResponse();
  return {
    planning_context: explorer.planning_context,
    plan: explorer.plan,
    projection: explorer.projection,
    accounting_before: explorer.accounting_before,
    outgoing: explorer.outgoing,
    candidate: {
      player_id: playerInId,
      web_name: "Available Alex",
      team_short_name: "LIV",
      position: "MID",
      status: "a",
      price_tenths: 62,
    },
    state: "available",
    reasons: [] as string[],
    conflict: null,
    valid_through_gameweek: null,
    confirmable: true,
    commit: buildPlannerCommitDescriptor(playerInId),
    gameweeks: [],
    totals: Object.fromEntries(
      HORIZON_KEYS.map((key) => [
        key,
        {
          saved_plan: 3.5,
          assumed_continuation: 2.5,
          hit_change: 0,
          net_saved_plan: 3.5,
        },
      ]),
    ),
    lineup_effect: { captain_changed: false, vice_captain_changed: false },
    best_xi: {
      gain_by_horizon: { "1": 1.5, "3": 3.2, "5": 5.5 },
      direct_xpts_difference: 1.2,
    },
  };
}

export function buildPlannerCommitDescriptor(playerInId = 101) {
  return {
    intent: {
      kind: "add_transfer" as const,
      incoming_player_id: playerInId,
      gameweek_number: EXPLORER_GAMEWEEK,
      outgoing_player_id: EXPLORER_OUTGOING_ID,
      outgoing_ownership_id: plannerIdentity(1006),
    },
    guard: {
      expected_outgoing_market_tenths: 54,
      expected_incoming_price_tenths: 62,
    },
    expected_revision: 3,
  };
}
