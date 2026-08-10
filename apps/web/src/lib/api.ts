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

export async function fetchFixtureTicker(limit = 20): Promise<FixtureTickerResponse> {
  const response = await fetch(`${API_BASE_URL}/fixtures/ticker?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Fixture ticker request failed with status ${response.status}`);
  }

  return (await response.json()) as FixtureTickerResponse;
}
