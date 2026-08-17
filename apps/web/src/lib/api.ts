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
  | { type: "unavailable"; code: string; message: string; missingPlayerIds: number[] };

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
      detail?: { code?: string; message?: string; missing_player_ids?: number[] };
    };
    return {
      type: "unavailable",
      code: body.detail?.code ?? "transfer_explorer_unavailable",
      message: body.detail?.message ?? "This transfer could not be explored",
      missingPlayerIds: body.detail?.missing_player_ids ?? [],
    };
  }

  if (!response.ok) {
    throw new Error(`Transfer explorer request failed with status ${response.status}`);
  }

  return { type: "ok", data: (await response.json()) as TransferExplorerResponse };
}

export type PlanChip = "WILDCARD" | "FREE_HIT" | "BENCH_BOOST" | "TRIPLE_CAPTAIN";

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
};

export type PlanTransfer = {
  player_id: number;
  web_name: string;
};

export type PlanGameweek = {
  gameweek_number: number;
  chip: PlanChip | null;
  bank: number;
  free_transfers_available: number;
  unlimited_transfers: boolean;
  transfers_made: number;
  points_hit: number;
  starting_points: number;
  bench_points: number;
  captain_bonus_points: number;
  total_points: number;
  players: PlanPlayer[];
  transfers_in: PlanTransfer[];
  transfers_out: PlanTransfer[];
};

export type PlanResponse = {
  plan_id: number;
  name: string;
  start_gameweek: number;
  end_gameweek: number;
  initial_bank: number;
  initial_free_transfers: number;
  total_points: number;
  total_points_hit: number;
  gameweeks: PlanGameweek[];
};

export type SavePlanGameweekRequest = {
  chip: PlanChip | null;
  players: SaveMyTeamPlayerSelection[];
};

export class PlanRuleError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "PlanRuleError";
    this.code = code;
  }
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

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
  if (params?.team_id !== undefined) query.set("team_id", String(params.team_id));
  if (params?.gameweek !== undefined) query.set("gameweek", String(params.gameweek));

  const response = await fetch(`${API_BASE_URL}/fixtures/ticker?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`Fixture ticker request failed with status ${response.status}`);
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

export async function updateTeamDifficulty(teamId: number, difficulty: number): Promise<TeamItem> {
  const response = await fetch(`${API_BASE_URL}/teams/${teamId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ difficulty }),
  });
  if (!response.ok) {
    throw new Error(`Update team difficulty request failed with status ${response.status}`);
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

export async function saveMyTeam(payload: SaveMyTeamRequest): Promise<MyTeamResponse> {
  const response = await fetch(`${API_BASE_URL}/my-team`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Save my team request failed with status ${response.status}`);
  }

  return (await response.json()) as MyTeamResponse;
}

export async function refreshProjections(): Promise<ProjectionRefreshResponse> {
  const response = await fetch(`${API_BASE_URL}/projections/run`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`Projection refresh request failed with status ${response.status}`);
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
      detail?: { code?: string; message?: string; missing_player_ids?: number[] };
    };
    throw new MyTeamRecommendationUnavailableError(
      body.detail?.code ?? "recommendation_unavailable",
      body.detail?.message ?? "The recommendation could not be computed",
      body.detail?.missing_player_ids ?? [],
    );
  }
  if (!response.ok) {
    throw new Error(`My team recommendation request failed with status ${response.status}`);
  }

  return (await response.json()) as MyTeamRecommendationResponse;
}

async function readPlanResponse(response: Response, action: string): Promise<PlanResponse> {
  if (response.status === 422) {
    const body = (await response.json()) as { detail?: { code?: string; message?: string } };
    throw new PlanRuleError(
      body.detail?.code ?? "invalid_plan",
      body.detail?.message ?? "That change is not allowed",
    );
  }
  if (!response.ok) {
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

export async function updatePlan(
  planId: number,
  payload: { name?: string; start_gameweek?: number; end_gameweek?: number },
): Promise<PlanResponse> {
  const response = await fetch(`${API_BASE_URL}/plans/${planId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return readPlanResponse(response, "Update plan");
}

export async function deletePlan(planId: number): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/plans/${planId}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(`Delete plan request failed with status ${response.status}`);
  }
}

export async function savePlanGameweek(
  planId: number,
  gameweekNumber: number,
  payload: SavePlanGameweekRequest,
): Promise<PlanResponse> {
  const response = await fetch(`${API_BASE_URL}/plans/${planId}/gameweeks/${gameweekNumber}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return readPlanResponse(response, "Save plan gameweek");
}
