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

export async function fetchGameweeks(): Promise<GameweekListResponse> {
  const response = await fetch(`${API_BASE_URL}/gameweeks`);
  if (!response.ok) {
    throw new Error(`Gameweeks request failed with status ${response.status}`);
  }

  return (await response.json()) as GameweekListResponse;
}
