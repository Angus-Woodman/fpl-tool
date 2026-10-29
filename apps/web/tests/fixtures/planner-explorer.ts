import type {
  PlanExplorerCandidate,
  PlanExplorerHorizonInfo,
  PlanExplorerImpact,
  PlanCommitDescriptor,
  PlanPreviewAccounting,
  PlanPreviewGameweek,
  PlanPreviewTotals,
  PlanTransferExplorerResponse,
  PlanTransferPreviewResponse,
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

export function buildFinancialBlockedCandidate(): PlanExplorerCandidate {
  return buildExplorerCandidate({
    player_id: 104,
    web_name: "Costly Cal",
    state: "blocked_by_later_decision",
    reasons: [],
    valid_through_gameweek: 11,
    conflict: {
      kind: "financial",
      gameweek: 11,
      decision_id: null,
      code: "financial_shortfall",
      message: "The bank would be short in GW11 after this transfer.",
      shortfall_tenths: 25,
    },
    plan_impact_by_horizon: {
      "1": buildImpact(),
      "3": buildImpact({ valid_through_gameweek: 11 }),
      "5": buildImpact({ valid_through_gameweek: 11 }),
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

export function forPlan<
  T extends {
    planning_context: { plan_id: number };
    plan: { plan_id: number };
  },
>(payload: T, planId: number): T {
  payload.planning_context.plan_id = planId;
  payload.plan.plan_id = planId;
  return payload;
}

export function buildCommitDescriptor(
  playerInId = 101,
  overrides: Partial<PlanCommitDescriptor> = {},
): PlanCommitDescriptor {
  return {
    intent: {
      kind: "add_transfer",
      gameweek_number: EXPLORER_GAMEWEEK,
      outgoing_player_id: EXPLORER_OUTGOING_ID,
      outgoing_ownership_id: plannerIdentity(1006),
      incoming_player_id: playerInId,
    },
    guard: {
      expected_outgoing_market_tenths: 54,
      expected_incoming_price_tenths: 62,
    },
    expected_revision: 3,
    ...overrides,
  };
}

function accounting(
  bank: number,
  freeTransfers: number,
  made: number,
  hit: number,
  next: number,
): PlanPreviewAccounting {
  return {
    closing_bank_tenths: bank,
    free_transfers_available: freeTransfers,
    transfers_made: made,
    points_hit: hit,
    next_free_transfers: next,
  };
}

export function buildPreviewGameweek(
  overrides: Partial<PlanPreviewGameweek> & { gameweek: number },
): PlanPreviewGameweek {
  return {
    basis: "saved_plan",
    valid: true,
    chip: null,
    accounting: {
      before: accounting(15, 2, 0, 0, 2),
      after: accounting(8, 2, 1, 0, 1),
    },
    squad_changed: true,
    incoming_role: "starting",
    points: { before: 60, after: 62.5, delta: 2.5 },
    reason: null,
    shortfall_tenths: null,
    ...overrides,
  };
}

export function buildPreviewTotals(
  overrides: Partial<PlanPreviewTotals> = {},
): PlanPreviewTotals {
  return {
    saved_plan: 5,
    assumed_continuation: 7.5,
    hit_change: -4,
    net_saved_plan: 1,
    ...overrides,
  };
}

export function buildPlannerPreviewResponse(
  overrides: Partial<PlanTransferPreviewResponse> = {},
): PlanTransferPreviewResponse {
  const explorer = buildPlannerExplorerResponse();
  const candidate = buildAvailableCandidate();
  return {
    planning_context: explorer.planning_context,
    plan: explorer.plan,
    projection: explorer.projection,
    accounting_before: explorer.accounting_before,
    outgoing: explorer.outgoing,
    candidate: {
      player_id: candidate.player_id,
      web_name: candidate.web_name,
      team_short_name: candidate.team_short_name,
      position: candidate.position,
      status: candidate.status,
      price_tenths: candidate.price_tenths,
    },
    state: "available",
    reasons: [],
    conflict: null,
    valid_through_gameweek: null,
    confirmable: true,
    commit: buildCommitDescriptor(candidate.player_id),
    gameweeks: [
      buildPreviewGameweek({ gameweek: 9 }),
      buildPreviewGameweek({
        gameweek: 10,
        accounting: {
          before: accounting(8, 1, 0, 0, 1),
          after: accounting(8, 1, 0, 0, 1),
        },
        incoming_role: "bench",
        points: { before: 61, after: 61, delta: 0 },
      }),
      buildPreviewGameweek({
        gameweek: 11,
        basis: "assumed_continuation",
        incoming_role: "captain",
        points: { before: 62, after: 66.5, delta: 4.5 },
      }),
      buildPreviewGameweek({
        gameweek: 12,
        basis: "assumed_continuation",
        points: { before: 63, after: 64, delta: 1 },
      }),
    ],
    totals: {
      "1": buildPreviewTotals({
        saved_plan: 2.5,
        assumed_continuation: null,
        hit_change: 0,
        net_saved_plan: 2.5,
      }),
      "3": buildPreviewTotals({
        saved_plan: 2.5,
        assumed_continuation: 4.5,
        hit_change: 0,
        net_saved_plan: 2.5,
      }),
      "5": buildPreviewTotals(),
    },
    lineup_effect: { captain_changed: true, vice_captain_changed: false },
    best_xi: {
      gain_by_horizon: { "1": 1.5, "3": 3.2, "5": 5.5 },
      direct_xpts_difference: 1.2,
    },
    ...overrides,
  };
}

function withheld(gameweek: number): PlanPreviewGameweek {
  return buildPreviewGameweek({
    gameweek,
    valid: false,
    accounting: null,
    squad_changed: false,
    incoming_role: null,
    points: null,
    reason: "beyond_valid_range",
  });
}

/** A planned later sale of the outgoing player: values stop before the clashing GW11. */
export function buildStructuralBlockedPreview(): PlanTransferPreviewResponse {
  const candidate = buildBlockedCandidate();
  return buildPlannerPreviewResponse({
    candidate: {
      player_id: candidate.player_id,
      web_name: candidate.web_name,
      team_short_name: candidate.team_short_name,
      position: candidate.position,
      status: candidate.status,
      price_tenths: candidate.price_tenths,
    },
    state: "blocked_by_later_decision",
    conflict: candidate.conflict,
    valid_through_gameweek: 10,
    confirmable: false,
    commit: null,
    gameweeks: [
      buildPreviewGameweek({ gameweek: 9 }),
      buildPreviewGameweek({ gameweek: 10 }),
      withheld(11),
      { ...withheld(12), basis: "assumed_continuation" },
    ],
    totals: {
      "1": buildPreviewTotals({ assumed_continuation: null }),
      "3": buildPreviewTotals({
        saved_plan: null,
        assumed_continuation: null,
        net_saved_plan: null,
      }),
      "5": buildPreviewTotals({
        saved_plan: null,
        assumed_continuation: null,
        net_saved_plan: null,
      }),
    },
  });
}

/** GW10 would overdraw the bank: its figures explain the shortfall and are not a valid gameweek. */
export function buildFinancialBlockedPreview(): PlanTransferPreviewResponse {
  const candidate = buildFinancialBlockedCandidate();
  return buildPlannerPreviewResponse({
    candidate: {
      player_id: candidate.player_id,
      web_name: candidate.web_name,
      team_short_name: candidate.team_short_name,
      position: candidate.position,
      status: candidate.status,
      price_tenths: candidate.price_tenths,
    },
    state: "blocked_by_later_decision",
    conflict: {
      kind: "financial",
      gameweek: 10,
      decision_id: null,
      code: "financial_shortfall",
      message: "The bank would be short in GW10 after this transfer.",
      shortfall_tenths: 25,
    },
    valid_through_gameweek: 10,
    confirmable: false,
    commit: null,
    gameweeks: [
      buildPreviewGameweek({ gameweek: 9 }),
      buildPreviewGameweek({
        gameweek: 10,
        valid: false,
        accounting: {
          before: accounting(8, 1, 0, 0, 1),
          after: accounting(-25, 1, 1, 0, 1),
        },
        incoming_role: "starting",
        points: { before: 61, after: 62, delta: 1 },
        reason: "financial_shortfall",
        shortfall_tenths: 25,
      }),
      withheld(11),
      { ...withheld(12), basis: "assumed_continuation" },
    ],
    totals: {
      "1": buildPreviewTotals({ assumed_continuation: null }),
      "3": buildPreviewTotals({
        saved_plan: null,
        assumed_continuation: null,
        net_saved_plan: null,
      }),
      "5": buildPreviewTotals({
        saved_plan: null,
        assumed_continuation: null,
        net_saved_plan: null,
      }),
    },
  });
}

export function buildUnavailablePreview(
  reasons: string[] = ["club_limit"],
): PlanTransferPreviewResponse {
  const candidate = buildUnavailableCandidate(reasons);
  return buildPlannerPreviewResponse({
    candidate: {
      player_id: candidate.player_id,
      web_name: candidate.web_name,
      team_short_name: candidate.team_short_name,
      position: candidate.position,
      status: candidate.status,
      price_tenths: candidate.price_tenths,
    },
    state: "unavailable",
    reasons,
    valid_through_gameweek: null,
    confirmable: false,
    commit: null,
    gameweeks: [withheld(9)],
    totals: {
      "1": buildPreviewTotals({
        saved_plan: null,
        assumed_continuation: null,
        net_saved_plan: null,
      }),
      "3": buildPreviewTotals({
        saved_plan: null,
        assumed_continuation: null,
        net_saved_plan: null,
      }),
      "5": buildPreviewTotals({
        saved_plan: null,
        assumed_continuation: null,
        net_saved_plan: null,
      }),
    },
  });
}

/** The edit variant of the descriptor, for replacing a transfer already planned in the gameweek. */
export function buildEditCommitDescriptor(
  playerInId = 101,
): PlanCommitDescriptor {
  return buildCommitDescriptor(playerInId, {
    intent: {
      kind: "edit_transfer",
      decision_id: plannerIdentity(9001),
      incoming_player_id: playerInId,
    },
  });
}
