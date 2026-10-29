import type { LegalRearrangement } from "@/lib/squad-rearrangement";

export type PlayerItem = {
  id: number;
  web_name: string;
  first_name: string;
  second_name: string;
  team_name: string;
  team_short_name: string;
  position: "GK" | "DEF" | "MID" | "FWD";
  current_price: number;
  status: string;
};

export type PlayerListResponse = {
  items: PlayerItem[];
  total: number;
  page: number;
  page_size: number;
};

export type FixtureTickerItem = {
  fixture_id: number;
  gameweek_number: number | null;
  kickoff_time: string;
  home_team_short_name: string;
  away_team_short_name: string;
  home_team_difficulty: number;
  away_team_difficulty: number;
  finished: boolean;
};

export type FixtureTickerResponse = {
  items: FixtureTickerItem[];
  total: number;
  page: number;
  page_size: number;
};

export type TeamItem = {
  id: number;
  name: string;
  short_name: string;
  difficulty: number;
};

export type TeamListResponse = {
  items: TeamItem[];
  total: number;
};

export type GameweekItem = {
  id: number;
  number: number;
  name: string;
  is_current: boolean;
  is_next: boolean;
  is_finished: boolean;
};

export type GameweekListResponse = {
  items: GameweekItem[];
  total: number;
};

export type MyTeamPlayerItem = {
  player_id: number;
  web_name: string;
  first_name: string;
  second_name: string;
  team_name: string;
  team_short_name: string;
  position: "GK" | "DEF" | "MID" | "FWD";
  current_price: number;
  status: string;
  is_starting: boolean;
  bench_order: number | null;
  is_captain: boolean;
  is_vice_captain: boolean;
  projection_totals: HorizonProjectionTotals | null;
  fixture_projections: PlayerFixtureProjection[];
};

export type PlayerFixtureProjection = {
  fixture_id: number | null;
  gameweek_number: number;
  projected_points: number;
  kickoff_time: string;
  opponent_team_short_name: string | null;
  is_home: boolean | null;
};

export type HorizonProjectionTotals = {
  horizon_1: number;
  horizon_3: number;
  horizon_5: number;
};

export type MyTeamResponse = {
  squad_id: number;
  name: string;
  bank: number;
  free_transfers: number;
  projection_totals: HorizonProjectionTotals | null;
  bench_projection_totals: HorizonProjectionTotals | null;
  captain_adjusted_projection_totals: HorizonProjectionTotals | null;
  gameweek_numbers: number[];
  legal_rearrangements: LegalRearrangement[];
  players: MyTeamPlayerItem[];
};

export type SaveMyTeamPlayerSelection = {
  player_id: number;
  is_starting: boolean;
  bench_order: number | null;
  is_captain: boolean;
  is_vice_captain: boolean;
};

export type SaveMyTeamRequest = {
  bank: number;
  free_transfers: number;
  players: SaveMyTeamPlayerSelection[];
};

export type ProjectionRefreshResponse = {
  projections_generated: number;
  fixtures_considered: number;
  players_considered: number;
  model_version: string;
  generated_at: string;
};

export type MyTeamRecommendationResponse = {
  model_version: string;
  projection_run_id: number;
  generated_at: string;
  target_gameweek_number: number;
  starting_xi_points: number;
  captain_adjusted_points: number;
  starting_xi: number[];
  bench_goalkeeper: number;
  bench_outfield: number[];
  captain: number;
  vice_captain: number;
  // JSON object keys are always strings, even though the backend's
  // dict[int, float] logically keys by player id.
  player_projected_points: Record<string, number>;
  current_captain_adjusted_points: number;
};

export class MyTeamRecommendationUnavailableError extends Error {
  readonly code: string;
  readonly missingPlayerIds: number[];

  constructor(code: string, message: string, missingPlayerIds: number[]) {
    super(message);
    this.name = "MyTeamRecommendationUnavailableError";
    this.code = code;
    this.missingPlayerIds = missingPlayerIds;
  }
}

export type TransferHorizon = 1 | 3 | 5;

export type TransferOutgoingPlayerSummary = {
  player_id: number;
  web_name: string;
  position: "GK" | "DEF" | "MID" | "FWD";
  team_short_name: string;
  current_price: number;
  selling_price: number;
  projected_points_by_horizon: Record<string, number>;
};

export type RankedTransferCandidate = {
  player_id: number;
  web_name: string;
  team_short_name: string;
  price: number;
  resulting_bank: number;
  team_gain_by_horizon: Record<string, number>;
  direct_xpts_difference: number | null;
  gameweeks_evaluated: number;
  // false: listed and comparable but currently unavailable to apply.
  is_legal: boolean;
  unavailable_reasons: string[];
  // Advisory playing status code only; never a reason for unavailability.
  status: string;
};

export type TransferExplorerResponse = {
  model_version: string;
  projection_run_id: number;
  generated_at: string;
  primary_horizon: number;
  bank: number;
  selling_price_is_approximate: boolean;
  outgoing: TransferOutgoingPlayerSummary;
  candidates: RankedTransferCandidate[];
  evaluated_gameweek_numbers: number[];
};

export type TransferExplorerFetchResult =
  | { type: "ok"; data: TransferExplorerResponse }
  | { type: "no_squad" }
  | { type: "player_not_found" }
  | {
      type: "unavailable";
      code: string;
      message: string;
      missingPlayerIds: number[];
    };

export async function fetchTransferExplorer(
  playerOutId: number,
  primaryHorizon: TransferHorizon = 5,
): Promise<TransferExplorerFetchResult> {
  const response = await fetch(
    `${API_BASE_URL}/my-team/transfers/${playerOutId}?primary_horizon=${primaryHorizon}`,
  );

  if (response.status === 404) {
    const body = (await response.json()) as { detail?: unknown };
    const detail =
      typeof body.detail === "object" && body.detail !== null
        ? (body.detail as { code?: string })
        : undefined;
    if (detail?.code === "player_not_found") {
      return { type: "player_not_found" };
    }
    return { type: "no_squad" };
  }

  if (response.status === 422) {
    const body = (await response.json()) as {
      detail?: {
        code?: string;
        message?: string;
        missing_player_ids?: number[];
      };
    };
    return {
      type: "unavailable",
      code: body.detail?.code ?? "transfer_explorer_unavailable",
      message: body.detail?.message ?? "This transfer could not be explored",
      missingPlayerIds: body.detail?.missing_player_ids ?? [],
    };
  }

  if (!response.ok) {
    throw new Error(
      `Transfer explorer request failed with status ${response.status}`,
    );
  }

  return {
    type: "ok",
    data: (await response.json()) as TransferExplorerResponse,
  };
}

export type LineupSummary = {
  starting_xi: number[];
  bench_goalkeeper: number;
  bench_outfield: number[];
  captain: number;
  vice_captain: number;
  starting_xi_points: number;
  captain_adjusted_points: number;
};

export type TransferPreviewResponse = {
  model_version: string;
  projection_run_id: number;
  generated_at: string;
  target_gameweek_number: number;
  bank: number;
  resulting_bank: number;
  selling_price_is_approximate: boolean;
  player_out_id: number;
  player_in_id: number;
  is_legal: boolean;
  errors: string[];
  projected_team_gain: number;
  direct_player_xpts_difference: number;
  lineup_before: LineupSummary | null;
  lineup_after: LineupSummary | null;
  captain_changed: boolean;
  vice_captain_changed: boolean;
  player_in_status: string;
};

export type TransferPreviewFetchResult =
  | { type: "ok"; data: TransferPreviewResponse }
  | { type: "no_squad" }
  | { type: "player_not_found" }
  | {
      type: "unavailable";
      code: string;
      message: string;
      missingPlayerIds: number[];
    };

export async function fetchTransferPreview(
  playerOutId: number,
  playerInId: number,
): Promise<TransferPreviewFetchResult> {
  const response = await fetch(
    `${API_BASE_URL}/my-team/transfers/${playerOutId}/preview?player_in_id=${playerInId}`,
  );

  if (response.status === 404) {
    const body = (await response.json()) as { detail?: unknown };
    const detail =
      typeof body.detail === "object" && body.detail !== null
        ? (body.detail as { code?: string })
        : undefined;
    if (detail?.code === "player_not_found") {
      return { type: "player_not_found" };
    }
    return { type: "no_squad" };
  }

  if (response.status === 422) {
    const body = (await response.json()) as {
      detail?: {
        code?: string;
        message?: string;
        missing_player_ids?: number[];
      };
    };
    return {
      type: "unavailable",
      code: body.detail?.code ?? "transfer_preview_unavailable",
      message: body.detail?.message ?? "This transfer could not be previewed",
      missingPlayerIds: body.detail?.missing_player_ids ?? [],
    };
  }

  if (!response.ok) {
    throw new Error(
      `Transfer preview request failed with status ${response.status}`,
    );
  }

  return {
    type: "ok",
    data: (await response.json()) as TransferPreviewResponse,
  };
}

export type ApplyTransferFetchResult =
  | { type: "ok"; data: MyTeamResponse }
  | { type: "no_squad" }
  | { type: "player_not_found" }
  | {
      type: "unavailable";
      code: string;
      message: string;
      missingPlayerIds: number[];
      errors: string[];
    };

export async function applyTransfer(
  playerOutId: number,
  playerInId: number,
): Promise<ApplyTransferFetchResult> {
  const response = await fetch(
    `${API_BASE_URL}/my-team/transfers/${playerOutId}/apply`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_in_id: playerInId }),
    },
  );

  if (response.status === 404) {
    const body = (await response.json()) as { detail?: unknown };
    const detail =
      typeof body.detail === "object" && body.detail !== null
        ? (body.detail as { code?: string })
        : undefined;
    if (detail?.code === "player_not_found") {
      return { type: "player_not_found" };
    }
    return { type: "no_squad" };
  }

  if (response.status === 422) {
    const body = (await response.json()) as {
      detail?: {
        code?: string;
        message?: string;
        missing_player_ids?: number[];
        errors?: string[];
      };
    };
    return {
      type: "unavailable",
      code: body.detail?.code ?? "transfer_apply_unavailable",
      message: body.detail?.message ?? "This transfer could not be applied",
      missingPlayerIds: body.detail?.missing_player_ids ?? [],
      errors: body.detail?.errors ?? [],
    };
  }

  if (!response.ok) {
    throw new Error(
      `Apply transfer request failed with status ${response.status}`,
    );
  }

  return { type: "ok", data: (await response.json()) as MyTeamResponse };
}

export type PlanChip =
  "WILDCARD" | "FREE_HIT" | "BENCH_BOOST" | "TRIPLE_CAPTAIN";

export type PlanSummary = {
  plan_id: number;
  name: string;
  start_gameweek: number;
  end_gameweek: number;
};

export type PlanListResponse = {
  plans: PlanSummary[];
};

export type PlanFixture = {
  fixture_id: number | null;
  projected_points: number;
  kickoff_time: string;
  opponent_team_short_name: string | null;
  is_home: boolean | null;
};

export type PlanPlayer = {
  player_id: number;
  web_name: string;
  team_short_name: string;
  position: "GK" | "DEF" | "MID" | "FWD";
  current_price: number;
  status: string;
  is_starting: boolean;
  bench_order: number | null;
  is_captain: boolean;
  is_vice_captain: boolean;
  projected_points: number;
  fixtures: PlanFixture[];
  slot_id: string | null;
  ownership_id: string | null;
  source_decision_id: string | null;
  purchase_price_tenths: number | null;
  provenance: PurchaseProvenance | null;
};

export type PurchaseProvenance = {
  source: string;
  original_price_tenths: number;
  basis_kind: "starting" | "planned_acquisition";
  confirmation: "assumed" | "user_confirmed" | "authoritative" | null;
};

export type StartingOwnership = {
  slot_id: string;
  ownership_id: string;
  player_id: number;
  web_name: string;
  purchase_price_tenths: number;
  provenance: PurchaseProvenance;
};

export type StartingState = {
  players: StartingOwnership[];
  lineup: {
    slot_id: string;
    is_starting: boolean;
    bench_order: number | null;
    is_captain: boolean;
    is_vice_captain: boolean;
  }[];
  bank_tenths: number;
  free_transfers: number | null;
  used_chips: PlanChip[];
  free_hit_gameweek_19: boolean;
  origin:
    | "my_team_capture"
    | "legacy_first_gameweek_assumed"
    | "rebased_plan"
    | "earlier_horizon_assumed";
  bank_assumptions: string[];
};

export type PlanDecision = {
  decision_id: string;
  outgoing_player_id: number;
  outgoing_ownership_id: string;
  incoming_player_id: number;
  incoming_ownership_id: string;
  outgoing_market_tenths: number;
  incoming_price_tenths: number;
  selling_price_tenths: number | null;
  purchase_price_tenths?: number | null;
  basis_kind?: "starting" | "planned_acquisition" | null;
  basis_confirmation?: "assumed" | "user_confirmed" | "authoritative" | null;
  outgoing_live_market_tenths?: number | null;
  incoming_live_price_tenths?: number | null;
  observation_source: string;
  observed_at: string;
  origin: string;
};

export type PlanChipAvailability = {
  state:
    | "available"
    | "planned_here"
    | "planned_elsewhere"
    | "used_before"
    | "rule_unavailable";
  reason: string | null;
  conflicting_gameweek: number | null;
};

export type PlanTransfer = {
  player_id: number;
  web_name: string;
};

export type PlanGameweek = {
  gameweek_number: number;
  chip: PlanChip | null;
  bank: number | null;
  free_transfers_available: number | null;
  unlimited_transfers: boolean;
  transfers_made: number | null;
  points_hit: number | null;
  starting_points: number | null;
  bench_points: number | null;
  captain_bonus_points: number | null;
  total_points: number | null;
  players: PlanPlayer[];
  transfers_in: PlanTransfer[];
  transfers_out: PlanTransfer[];
  decisions: PlanDecision[];
  accounting: {
    starting_bank_tenths: number | null;
    closing_bank_tenths: number | null;
    free_transfers_available: number | null;
    next_free_transfers: number | null;
    unlimited_transfers: boolean;
    transfers_made: number | null;
    points_hit: number | null;
  } | null;
  chip_availability: Partial<Record<PlanChip, PlanChipAvailability>>;
  legal_rearrangements: LegalRearrangement[];
  evaluation_status: "complete" | "blocked";
};

export type PlanResponse = {
  plan_id: number;
  name: string;
  start_gameweek: number;
  end_gameweek: number;
  initial_bank: number;
  initial_free_transfers: number;
  total_points: number | null;
  total_points_hit: number | null;
  gameweeks: PlanGameweek[];
  revision: number;
  evaluator_version: string;
  foundation_state: "legacy_pending" | "ready";
  starting_state: StartingState | null;
  financial_status: {
    provisional?: boolean;
    requires_resolution?: boolean;
    earliest_shortfall_gameweek?: number | null;
    earliest_shortfall_tenths?: number | null;
    earliest_shortfall_reason?: string | null;
    gameweeks?: {
      gameweek_number: number;
      shortfall_tenths: number | null;
      affected_chain: number[];
      provisional?: boolean;
    }[];
  };
  decision_errors: {
    code: string;
    message: string;
    gameweek_number: number;
    decision_id: string | null;
    conflicting_gameweek: number | null;
    player_id: number | null;
  }[];
  initialization: {
    ready: boolean;
    reason?: string;
    retryable?: boolean;
    boundary_origin?: string;
  };
};

export type PlanIntent =
  | { kind: "rename_plan"; name: string }
  | {
      kind: "change_horizon";
      start_gameweek: number;
      end_gameweek: number;
      used_chips?: PlanChip[];
      free_hit_gameweek_19?: boolean;
    }
  | { kind: "set_starting_transfers"; value: number | null }
  | {
      kind: "set_starting_chips";
      used_chips: PlanChip[];
      free_hit_gameweek_19: boolean;
    }
  | {
      kind: "correct_purchase_price";
      ownership_id: string;
      price_tenths: number;
    }
  | { kind: "confirm_purchase_price"; ownership_id: string }
  | {
      kind: "change_captain" | "change_vice_captain";
      gameweek_number: number;
      player_id: number;
    }
  | {
      kind: "swap_lineup_players";
      gameweek_number: number;
      first_player_id: number;
      second_player_id: number;
    }
  | {
      kind: "activate_chip" | "remove_chip";
      gameweek_number: number;
      chip: PlanChip;
      expected_chip?: PlanChip | null;
    }
  | {
      kind: "move_chip";
      source_gameweek: number;
      target_gameweek: number;
      chip: PlanChip;
    }
  | {
      kind: "add_transfer";
      gameweek_number: number;
      outgoing_player_id: number;
      outgoing_ownership_id: string;
      incoming_player_id: number;
      expected_outgoing_market_tenths?: number;
      expected_incoming_price_tenths?: number;
    }
  | {
      kind: "edit_transfer";
      decision_id: string;
      outgoing_player_id?: number;
      outgoing_ownership_id?: string;
      outgoing_source_decision_id?: string;
      incoming_player_id?: number;
      expected_outgoing_market_tenths?: number;
      expected_incoming_price_tenths?: number;
    }
  | { kind: "remove_transfer"; decision_id: string };

export type PlanMutationEnvelope = {
  mutation_id: string;
  expected_revision: number;
  intents: PlanIntent[];
};
export type PlanMutationResponse = {
  status: "committed" | "already_committed" | "accepted_not_saved";
  mutation_id: string;
  committed_revision: number | null;
  plan: PlanResponse;
  candidate: PlanResponse | null;
};
export type PlannerErrorDetail = {
  code: string;
  message: string;
  mutation_id?: string;
  plan?: PlanResponse | null;
  candidate?: PlanResponse | null;
  intent_metadata?: unknown;
  diagnostics?: PlanResponse["decision_errors"];
};

export class PlannerMutationError extends Error {
  constructor(
    readonly status: number,
    readonly detail: PlannerErrorDetail,
  ) {
    super(detail.message);
    this.name = "PlannerMutationError";
  }
}

export class PlanRuleError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "PlanRuleError";
    this.code = code;
  }
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function fetchPlayers(params: {
  search?: string;
  position?: "GK" | "DEF" | "MID" | "FWD";
  status?: string;
  sort?: "web_name" | "price_desc" | "price_asc";
  page?: number;
  page_size?: number;
}): Promise<PlayerListResponse> {
  const query = new URLSearchParams();

  if (params.search) query.set("search", params.search);
  if (params.position) query.set("position", params.position);
  if (params.status) query.set("status", params.status);
  if (params.sort) query.set("sort", params.sort);
  if (params.page) query.set("page", String(params.page));
  if (params.page_size) query.set("page_size", String(params.page_size));

  const response = await fetch(`${API_BASE_URL}/players?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`Players request failed with status ${response.status}`);
  }

  return (await response.json()) as PlayerListResponse;
}

export async function fetchFixtureTicker(params?: {
  page?: number;
  limit?: number;
  team_id?: number;
  gameweek?: number;
}): Promise<FixtureTickerResponse> {
  const query = new URLSearchParams();
  query.set("page", String(params?.page ?? 1));
  query.set("limit", String(params?.limit ?? 20));
  if (params?.team_id !== undefined)
    query.set("team_id", String(params.team_id));
  if (params?.gameweek !== undefined)
    query.set("gameweek", String(params.gameweek));

  const response = await fetch(
    `${API_BASE_URL}/fixtures/ticker?${query.toString()}`,
  );
  if (!response.ok) {
    throw new Error(
      `Fixture ticker request failed with status ${response.status}`,
    );
  }

  return (await response.json()) as FixtureTickerResponse;
}

export async function fetchTeams(): Promise<TeamListResponse> {
  const response = await fetch(`${API_BASE_URL}/teams`);
  if (!response.ok) {
    throw new Error(`Teams request failed with status ${response.status}`);
  }

  return (await response.json()) as TeamListResponse;
}

export async function updateTeamDifficulty(
  teamId: number,
  difficulty: number,
): Promise<TeamItem> {
  const response = await fetch(`${API_BASE_URL}/teams/${teamId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ difficulty }),
  });
  if (!response.ok) {
    throw new Error(
      `Update team difficulty request failed with status ${response.status}`,
    );
  }

  return (await response.json()) as TeamItem;
}

export async function fetchGameweeks(): Promise<GameweekListResponse> {
  const response = await fetch(`${API_BASE_URL}/gameweeks`);
  if (!response.ok) {
    throw new Error(`Gameweeks request failed with status ${response.status}`);
  }

  return (await response.json()) as GameweekListResponse;
}

export async function fetchMyTeam(): Promise<MyTeamResponse | null> {
  const response = await fetch(`${API_BASE_URL}/my-team`);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`My team request failed with status ${response.status}`);
  }

  return (await response.json()) as MyTeamResponse;
}

export async function saveMyTeam(
  payload: SaveMyTeamRequest,
): Promise<MyTeamResponse> {
  const response = await fetch(`${API_BASE_URL}/my-team`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    // The API returns a readable `detail` string for rejected squads (for example an illegal formation).
    const body = (await response.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    if (typeof body?.detail === "string") {
      throw new Error(body.detail);
    }
    throw new Error(
      `Save my team request failed with status ${response.status}`,
    );
  }

  return (await response.json()) as MyTeamResponse;
}

export async function refreshProjections(): Promise<ProjectionRefreshResponse> {
  const response = await fetch(`${API_BASE_URL}/projections/run`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(
      `Projection refresh request failed with status ${response.status}`,
    );
  }

  return (await response.json()) as ProjectionRefreshResponse;
}

export async function fetchMyTeamRecommendation(): Promise<MyTeamRecommendationResponse | null> {
  const response = await fetch(`${API_BASE_URL}/my-team/recommendation`);
  if (response.status === 404) {
    return null;
  }
  if (response.status === 422) {
    const body = (await response.json()) as {
      detail?: {
        code?: string;
        message?: string;
        missing_player_ids?: number[];
      };
    };
    throw new MyTeamRecommendationUnavailableError(
      body.detail?.code ?? "recommendation_unavailable",
      body.detail?.message ?? "The recommendation could not be computed",
      body.detail?.missing_player_ids ?? [],
    );
  }
  if (!response.ok) {
    throw new Error(
      `My team recommendation request failed with status ${response.status}`,
    );
  }

  return (await response.json()) as MyTeamRecommendationResponse;
}

async function readPlanResponse(
  response: Response,
  action: string,
): Promise<PlanResponse> {
  if (response.status === 422) {
    const body = (await response.json()) as {
      detail?: { code?: string; message?: string };
    };
    throw new PlanRuleError(
      body.detail?.code ?? "invalid_plan",
      body.detail?.message ?? "That change is not allowed",
    );
  }
  if (!response.ok) {
    if (response.status === 400) {
      const body = (await response.json().catch(() => null)) as {
        detail?: unknown;
      } | null;
      const detail = body?.detail;
      if (typeof detail === "string" && detail) {
        throw new Error(detail);
      }
      if (typeof detail === "object" && detail !== null) {
        const { message } = detail as { message?: unknown };
        if (typeof message === "string" && message) {
          throw new Error(message);
        }
      }
    }
    throw new Error(`${action} request failed with status ${response.status}`);
  }

  return (await response.json()) as PlanResponse;
}

export async function fetchPlans(): Promise<PlanListResponse> {
  const response = await fetch(`${API_BASE_URL}/plans`);
  if (!response.ok) {
    throw new Error(`Plans request failed with status ${response.status}`);
  }

  return (await response.json()) as PlanListResponse;
}

export async function fetchPlan(planId: number): Promise<PlanResponse | null> {
  const response = await fetch(`${API_BASE_URL}/plans/${planId}`);
  if (response.status === 404) {
    return null;
  }

  return readPlanResponse(response, "Plan");
}

// Planner-aware Transfer Explorer (read-only list). Money is integer tenths of
// a million end to end; the browser only formats it for display.
export type PlanExplorerHorizonKey = "1" | "3" | "5";

export type PlanExplorerHorizonInfo = {
  horizon: TransferHorizon;
  requested_gameweeks: number[];
  evaluated_gameweeks: number[];
  saved_plan_gameweeks: number[];
  assumed_gameweeks: number[];
  partial: boolean;
};

export type PlanExplorerProjection = {
  model_version: string;
  run_id: number;
  generated_at: string;
  newer_run_available: boolean;
  primary_horizon: number;
  horizons: PlanExplorerHorizonInfo[];
  limited_to_selected_gameweek: boolean;
  limited_reason: "free_hit_gameweek" | null;
  unprojected_candidate_ids: number[];
};

export type PlanExplorerAccountingBefore = {
  starting_bank_tenths: number | null;
  closing_bank_tenths: number | null;
  free_transfers_available: number | null;
  transfers_made: number | null;
  points_hit: number | null;
  unlimited_transfers: boolean;
  provisional: boolean;
};

export type PlanExplorerOutgoing = {
  player_id: number;
  web_name: string;
  position: "GK" | "DEF" | "MID" | "FWD";
  team_short_name: string;
  ownership_id: string;
  operation: "add_transfer" | "edit_transfer";
  replaces_decision_id: string | null;
  purchase_price_tenths: number;
  purchase_basis: {
    basis_kind: string;
    confirmation: string | null;
  };
  market_price_tenths: number;
  selling_price_tenths: number | null;
  selling_provisional: boolean;
  projected_points_by_horizon: Record<PlanExplorerHorizonKey, number>;
};

export type PlanExplorerConflict = {
  kind: "structural" | "financial";
  gameweek: number;
  decision_id: string | null;
  code: string;
  message: string;
  shortfall_tenths: number | null;
};

export type PlanExplorerImpact = {
  saved_plan: number | null;
  assumed_continuation: number | null;
  net_saved_plan: number | null;
  valid_through_gameweek: number | null;
};

export type PlanExplorerFixture = {
  gameweek: number;
  opponent_short_name: string | null;
  is_home: boolean | null;
  difficulty: number | null;
};

export type PlanExplorerCandidateState =
  "available" | "unavailable" | "blocked_by_later_decision";

export type PlanExplorerCandidate = {
  player_id: number;
  web_name: string;
  team_short_name: string;
  position: "GK" | "DEF" | "MID" | "FWD";
  status: string;
  price_tenths: number;
  state: PlanExplorerCandidateState;
  reasons: string[];
  conflict: PlanExplorerConflict | null;
  valid_through_gameweek: number | null;
  resulting_bank_tenths: number | null;
  points_hit_after: number | null;
  best_xi_gain_by_horizon: Record<PlanExplorerHorizonKey, number>;
  direct_xpts_difference: number | null;
  plan_impact_by_horizon: Record<PlanExplorerHorizonKey, PlanExplorerImpact>;
  fixtures: PlanExplorerFixture[];
};

export type PlanTransferExplorerResponse = {
  planning_context: { plan_id: number; gameweek: number; revision: number };
  plan: {
    plan_id: number;
    name: string;
    revision: number;
    start_gameweek: number;
    end_gameweek: number;
    gameweek: number;
    chip: string | null;
    evaluator_version: string;
  };
  projection: PlanExplorerProjection;
  accounting_before: PlanExplorerAccountingBefore;
  outgoing: PlanExplorerOutgoing;
  candidates: PlanExplorerCandidate[];
};

export type PlanTransferExplorerFetchResult =
  | { type: "ok"; data: PlanTransferExplorerResponse }
  | { type: "plan_not_found" }
  | { type: "plan_not_ready"; message: string }
  | { type: "player_not_found" }
  | {
      type: "unavailable";
      code: string;
      message: string;
      missingPlayerIds: number[];
    };

type PlanTransferErrorBody = {
  detail?: {
    code?: string;
    message?: string;
    missing_player_ids?: number[];
  };
};

async function readPlanTransferErrorDetail(
  response: Response,
): Promise<NonNullable<PlanTransferErrorBody["detail"]>> {
  try {
    const body = (await response.json()) as PlanTransferErrorBody;
    return typeof body.detail === "object" && body.detail !== null
      ? body.detail
      : {};
  } catch {
    // A non-JSON error body carries no contract code; callers fall back to a
    // generic unavailable message rather than guessing a reason.
    return {};
  }
}

async function mapPlanTransferFailure(
  response: Response,
  label: string,
): Promise<Exclude<PlanTransferExplorerFetchResult, { type: "ok" }>> {
  if (response.status === 404) {
    const detail = await readPlanTransferErrorDetail(response);
    return detail.code === "player_not_found"
      ? { type: "player_not_found" }
      : { type: "plan_not_found" };
  }
  if (response.status === 409) {
    const detail = await readPlanTransferErrorDetail(response);
    return {
      type: "plan_not_ready",
      message: detail.message ?? "This plan is not ready for transfers yet",
    };
  }
  if (response.status === 422) {
    const detail = await readPlanTransferErrorDetail(response);
    return {
      type: "unavailable",
      code: detail.code ?? "transfer_explorer_unavailable",
      message: detail.message ?? "This transfer could not be explored",
      missingPlayerIds: detail.missing_player_ids ?? [],
    };
  }
  throw new Error(`${label} request failed with status ${response.status}`);
}

export async function fetchPlanTransferExplorer(params: {
  planId: number;
  gameweek: number;
  playerOutId: number;
  primaryHorizon?: TransferHorizon;
  projectionRunId?: number | null;
}): Promise<PlanTransferExplorerFetchResult> {
  const query = new URLSearchParams({
    primary_horizon: String(params.primaryHorizon ?? 5),
  });
  if (params.projectionRunId != null) {
    query.set("projection_run_id", String(params.projectionRunId));
  }
  const response = await fetch(
    `${API_BASE_URL}/plans/${params.planId}/gameweeks/${params.gameweek}/transfers/${params.playerOutId}?${query.toString()}`,
  );
  if (!response.ok) {
    return mapPlanTransferFailure(response, "Planner transfer explorer");
  }
  return {
    type: "ok",
    data: (await response.json()) as PlanTransferExplorerResponse,
  };
}

export type PlanPreviewAccounting = {
  closing_bank_tenths: number | null;
  free_transfers_available: number | null;
  transfers_made: number | null;
  points_hit: number | null;
  next_free_transfers: number | null;
};

export type PlanPreviewReason =
  | "no_projection"
  | "beyond_valid_range"
  | "continuation_lineup_illegal"
  | "financial_shortfall";

export type PlanPreviewGameweek = {
  gameweek: number;
  basis: "saved_plan" | "assumed_continuation";
  valid: boolean;
  chip: string | null;
  accounting: {
    before: PlanPreviewAccounting;
    after: PlanPreviewAccounting;
  } | null;
  squad_changed: boolean;
  incoming_role: "starting" | "bench" | "captain" | "vice_captain" | null;
  points: { before: number; after: number; delta: number } | null;
  reason: PlanPreviewReason | null;
  shortfall_tenths: number | null;
};

export type PlanPreviewTotals = {
  saved_plan: number | null;
  assumed_continuation: number | null;
  hit_change: number;
  net_saved_plan: number | null;
};

/** The Planner mutation the server issued for this preview; submitted exactly as given. */
export type PlanCommitDescriptor = {
  intent:
    | {
        kind: "add_transfer";
        gameweek_number: number;
        outgoing_player_id: number;
        outgoing_ownership_id: string;
        incoming_player_id: number;
      }
    | {
        kind: "edit_transfer";
        decision_id: string;
        incoming_player_id: number;
      };
  guard: {
    expected_outgoing_market_tenths: number;
    expected_incoming_price_tenths: number;
  };
  expected_revision: number;
};

export type PlanTransferPreviewResponse = {
  planning_context: PlanTransferExplorerResponse["planning_context"];
  plan: PlanTransferExplorerResponse["plan"];
  projection: PlanExplorerProjection;
  accounting_before: PlanExplorerAccountingBefore;
  outgoing: PlanExplorerOutgoing;
  candidate: {
    player_id: number;
    web_name: string;
    team_short_name: string;
    position: "GK" | "DEF" | "MID" | "FWD";
    status: string;
    price_tenths: number;
  };
  state: PlanExplorerCandidateState;
  reasons: string[];
  conflict: PlanExplorerConflict | null;
  valid_through_gameweek: number | null;
  confirmable: boolean;
  commit: PlanCommitDescriptor | null;
  gameweeks: PlanPreviewGameweek[];
  totals: Record<PlanExplorerHorizonKey, PlanPreviewTotals>;
  lineup_effect: { captain_changed: boolean; vice_captain_changed: boolean };
  best_xi: {
    gain_by_horizon: Record<PlanExplorerHorizonKey, number>;
    direct_xpts_difference: number | null;
  };
};

export type PlanTransferPreviewFetchResult =
  | { type: "ok"; data: PlanTransferPreviewResponse }
  | Exclude<PlanTransferExplorerFetchResult, { type: "ok" }>;

export async function fetchPlanTransferPreview(params: {
  planId: number;
  gameweek: number;
  playerOutId: number;
  playerInId: number;
  projectionRunId?: number | null;
}): Promise<PlanTransferPreviewFetchResult> {
  const query = new URLSearchParams({
    player_in_id: String(params.playerInId),
  });
  if (params.projectionRunId != null) {
    query.set("projection_run_id", String(params.projectionRunId));
  }
  const response = await fetch(
    `${API_BASE_URL}/plans/${params.planId}/gameweeks/${params.gameweek}/transfers/${params.playerOutId}/preview?${query.toString()}`,
  );
  if (!response.ok) {
    return mapPlanTransferFailure(response, "Planner transfer preview");
  }
  return {
    type: "ok",
    data: (await response.json()) as PlanTransferPreviewResponse,
  };
}

export async function createPlan(payload: {
  name: string;
  start_gameweek: number;
  end_gameweek: number;
}): Promise<PlanResponse> {
  const response = await fetch(`${API_BASE_URL}/plans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return readPlanResponse(response, "Create plan");
}

export async function deletePlan(planId: number): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/plans/${planId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(
      `Delete plan request failed with status ${response.status}`,
    );
  }
}

async function readPlannerMutation(
  response: Response,
): Promise<PlanMutationResponse> {
  const body = await response.json();
  if (!response.ok) {
    const detail = body.detail;
    throw new PlannerMutationError(
      response.status,
      detail && !Array.isArray(detail) && typeof detail.code === "string"
        ? detail
        : { code: "invalid_request", message: "Planner request rejected" },
    );
  }
  if (
    !["committed", "already_committed", "accepted_not_saved"].includes(
      body.status,
    ) ||
    !Number.isInteger(body.plan?.revision) ||
    typeof body.mutation_id !== "string"
  ) {
    throw new PlannerMutationError(503, {
      code: "outcome_unknown",
      message: "Invalid response; reconcile the same edit",
    });
  }
  return body as PlanMutationResponse;
}

export async function mutatePlan(
  planId: number,
  envelope: PlanMutationEnvelope,
): Promise<PlanMutationResponse> {
  return readPlannerMutation(
    await fetch(`${API_BASE_URL}/plans/${planId}/mutations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(envelope),
    }),
  );
}

export async function fetchPlanMutation(
  planId: number,
  mutationId: string,
): Promise<PlanMutationResponse> {
  return readPlannerMutation(
    await fetch(`${API_BASE_URL}/plans/${planId}/mutations/${mutationId}`),
  );
}
