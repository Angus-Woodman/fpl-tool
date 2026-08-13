import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MyTeamBoard } from "@/components/team/my-team-board";

function buildFullSquadResponse() {
  const players = [
    { player_id: 1, web_name: "GK One", team_short_name: "ARS", position: "GK", current_price: 4.0, is_starting: true, bench_order: null, is_captain: false, is_vice_captain: false },
    { player_id: 2, web_name: "GK Two", team_short_name: "AVL", position: "GK", current_price: 4.1, is_starting: false, bench_order: 1, is_captain: false, is_vice_captain: false },
    { player_id: 3, web_name: "DEF One", team_short_name: "BOU", position: "DEF", current_price: 4.2, is_starting: true, bench_order: null, is_captain: false, is_vice_captain: false },
    { player_id: 4, web_name: "DEF Two", team_short_name: "CHE", position: "DEF", current_price: 4.3, is_starting: true, bench_order: null, is_captain: false, is_vice_captain: false },
    { player_id: 5, web_name: "DEF Three", team_short_name: "EVE", position: "DEF", current_price: 4.4, is_starting: true, bench_order: null, is_captain: false, is_vice_captain: false },
    { player_id: 6, web_name: "DEF Four", team_short_name: "FUL", position: "DEF", current_price: 4.5, is_starting: true, bench_order: null, is_captain: false, is_vice_captain: false },
    { player_id: 7, web_name: "DEF Five", team_short_name: "LEI", position: "DEF", current_price: 4.6, is_starting: false, bench_order: 2, is_captain: false, is_vice_captain: false },
    { player_id: 8, web_name: "MID One", team_short_name: "LIV", position: "MID", current_price: 5.0, is_starting: true, bench_order: null, is_captain: true, is_vice_captain: false },
    { player_id: 9, web_name: "MID Two", team_short_name: "MCI", position: "MID", current_price: 5.1, is_starting: true, bench_order: null, is_captain: false, is_vice_captain: true },
    { player_id: 10, web_name: "MID Three", team_short_name: "NEW", position: "MID", current_price: 5.2, is_starting: true, bench_order: null, is_captain: false, is_vice_captain: false },
    { player_id: 11, web_name: "MID Four", team_short_name: "NFO", position: "MID", current_price: 5.3, is_starting: true, bench_order: null, is_captain: false, is_vice_captain: false },
    { player_id: 12, web_name: "MID Five", team_short_name: "SOU", position: "MID", current_price: 5.4, is_starting: false, bench_order: 3, is_captain: false, is_vice_captain: false },
    { player_id: 13, web_name: "FWD One", team_short_name: "TOT", position: "FWD", current_price: 6.0, is_starting: true, bench_order: null, is_captain: false, is_vice_captain: false },
    { player_id: 14, web_name: "FWD Two", team_short_name: "WHU", position: "FWD", current_price: 6.1, is_starting: true, bench_order: null, is_captain: false, is_vice_captain: false },
    { player_id: 15, web_name: "FWD Three", team_short_name: "WOL", position: "FWD", current_price: 6.2, is_starting: false, bench_order: 4, is_captain: false, is_vice_captain: false },
  ];

  return {
    squad_id: 1,
    name: "My Team",
    bank: 1.5,
    free_transfers: 2,
    projection_totals: { horizon_1: 5.5, horizon_3: 14.0, horizon_5: 21.0 },
    bench_projection_totals: { horizon_1: 2.0, horizon_3: 4.0, horizon_5: 6.0 },
    captain_adjusted_projection_totals: { horizon_1: 9.0, horizon_3: 22.0, horizon_5: 31.0 },
    gameweek_numbers: [2, 3, 4],
    players: players.map((player) => ({
      ...player,
      first_name: player.web_name,
      second_name: player.web_name,
      team_name: player.team_short_name,
      status: "a",
      projection_totals: { horizon_1: 2.0, horizon_3: 4.0, horizon_5: 6.0 },
      fixture_projections: [
        {
          fixture_id: player.player_id * 10 + 1,
          gameweek_number: 2,
          projected_points: player.is_starting ? 4.0 : 2.0,
          kickoff_time: "2026-08-15T15:00:00+00:00",
          opponent_team_short_name: "CHE",
          is_home: true,
        },
        {
          fixture_id: player.player_id * 10 + 2,
          gameweek_number: 3,
          projected_points: player.is_starting ? 3.0 : 1.5,
          kickoff_time: "2026-08-22T15:00:00+00:00",
          opponent_team_short_name: "TOT",
          is_home: false,
        },
      ],
    })),
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("MyTeamBoard", () => {
  it("renders computed cost/bank and no free transfers panel", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return { ok: true, json: async () => ({ items: [], total: 0 }) } as Response;
      }
      return { ok: true, json: async () => buildFullSquadResponse() } as Response;
    });

    render(<MyTeamBoard />);

    await waitFor(() => {
      expect(screen.getByText("Cost: 74.4")).toBeInTheDocument();
      expect(screen.getByText("Bank: 25.6")).toBeInTheDocument();
      expect(screen.queryByText("Free Transfers:")).not.toBeInTheDocument();
      expect(screen.getByText("Gameweek 2")).toBeInTheDocument();
    });
  });

  it("navigates gameweeks and updates opponent labels", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return { ok: true, json: async () => ({ items: [], total: 0 }) } as Response;
      }
      return { ok: true, json: async () => buildFullSquadResponse() } as Response;
    });

    render(<MyTeamBoard />);

    await waitFor(() => {
      expect(screen.getAllByText("Opponent: CHE (H)").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: "Next Game" }));

    await waitFor(() => {
      expect(screen.getByText("Gameweek 3")).toBeInTheDocument();
      expect(screen.getAllByText("Opponent: TOT (A)").length).toBeGreaterThan(0);
    });
  });

  it("swaps starter with bench and saves updated selection", async () => {
    const squadResponse = buildFullSquadResponse();
    const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return { ok: true, json: async () => ({ items: [], total: 0 }) } as Response;
      }
      if (url.endsWith("/my-team") && !init) {
        return { ok: true, json: async () => squadResponse } as Response;
      }
      if (url.endsWith("/my-team") && init?.method === "PUT") {
        return { ok: true, json: async () => squadResponse } as Response;
      }
      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(<MyTeamBoard />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Edit Team" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Edit Team" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Swap GK One with bench" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Swap GK One with bench" }));
    fireEvent.change(screen.getByLabelText("Bench Player for GK One"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm Swap" }));

    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));

    await waitFor(() => {
      const putCall = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/my-team") && init?.method === "PUT"
      );
      expect(putCall).toBeDefined();
      const payload = JSON.parse(String(putCall?.[1]?.body));
      const gkOne = payload.players.find((player: { player_id: number }) => player.player_id === 1);
      const gkTwo = payload.players.find((player: { player_id: number }) => player.player_id === 2);
      expect(gkOne?.is_starting).toBe(false);
      expect(gkTwo?.is_starting).toBe(true);
      expect(payload.bank).toBe(25.6);
    });
  });

  it("transfers a starter for a replacement from the player pool", async () => {
    const squadResponse = buildFullSquadResponse();
    const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);

      if (url.endsWith("/teams")) {
        return { ok: true, json: async () => ({ items: [], total: 0 }) } as Response;
      }
      if (url.endsWith("/my-team") && !init) {
        return { ok: true, json: async () => squadResponse } as Response;
      }
      if (url.endsWith("/my-team") && init?.method === "PUT") {
        return { ok: true, json: async () => squadResponse } as Response;
      }
      if (url.includes("/players?")) {
        const query = new URLSearchParams(url.split("?")[1]);
        const position = query.get("position");
        const items =
          position === "GK"
            ? [
                {
                  id: 101,
                  web_name: "GK Three",
                  first_name: "GK",
                  second_name: "Three",
                  team_name: "Bournemouth",
                  team_short_name: "BOU",
                  position: "GK",
                  current_price: 6.0,
                  status: "a",
                },
              ]
            : [];
        return { ok: true, json: async () => ({ items, total: items.length, page: 1, page_size: 60 }) } as Response;
      }
      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(<MyTeamBoard />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Edit Team" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Edit Team" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Transfer GK One" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Transfer GK One" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Replacement Player for GK One")).not.toBeDisabled();
    });

    fireEvent.change(screen.getByLabelText("Replacement Player for GK One"), {
      target: { value: "101" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm Transfer" }));

    await waitFor(() => {
      const putCall = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/my-team") && init?.method === "PUT"
      );
      expect(putCall).toBeDefined();
      const payload = JSON.parse(String(putCall?.[1]?.body));
      expect(payload.bank).toBe(23.6);
      const replaced = payload.players.find((player: { player_id: number }) => player.player_id === 101);
      expect(replaced).toBeDefined();
      expect(replaced.is_starting).toBe(true);
      expect(
        payload.players.some((player: { player_id: number }) => player.player_id === 1)
      ).toBe(false);
    });
  });

  it("offers a None/xPts/Fixture difficulty optimiser dropdown that hides manual edit controls", async () => {
    const squadResponse = buildFullSquadResponse();
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return {
          ok: true,
          json: async () => ({
            items: [
              { id: 1, name: "Chelsea", short_name: "CHE", difficulty: 5 },
              { id: 2, name: "Tottenham", short_name: "TOT", difficulty: 1 },
            ],
            total: 2,
          }),
        } as Response;
      }
      return { ok: true, json: async () => squadResponse } as Response;
    });

    render(<MyTeamBoard />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Edit Team" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Edit Team" }));

    const select = screen.getByLabelText("Optimise starting 11 by") as HTMLSelectElement;
    expect(select).toHaveValue("none");
    expect(screen.getByRole("button", { name: "Swap GK One with bench" })).toBeInTheDocument();

    fireEvent.change(select, { target: { value: "difficulty" } });

    await waitFor(() => {
      expect(select).toHaveValue("difficulty");
      expect(screen.queryByRole("button", { name: "Swap GK One with bench" })).not.toBeInTheDocument();
    });

    fireEvent.change(select, { target: { value: "xpts" } });

    await waitFor(() => {
      expect(select).toHaveValue("xpts");
      expect(screen.queryByRole("button", { name: "Swap GK One with bench" })).not.toBeInTheDocument();
    });

    fireEvent.change(select, { target: { value: "none" } });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Swap GK One with bench" })).toBeInTheDocument();
    });
  });

  it("refreshes projections and shows status", async () => {
    const squadResponse = buildFullSquadResponse();
    vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return { ok: true, json: async () => ({ items: [], total: 0 }) } as Response;
      }
      if (url.endsWith("/my-team") && !init) {
        return { ok: true, json: async () => squadResponse } as Response;
      }
      if (url.endsWith("/projections/run") && init?.method === "POST") {
        return {
          ok: true,
          json: async () => ({
            projections_generated: 120,
            fixtures_considered: 10,
            players_considered: 80,
            model_version: "baseline-v1",
            generated_at: "2026-01-01T09:30:00+00:00",
          }),
        } as Response;
      }
      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(<MyTeamBoard />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Refresh xPts" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Refresh xPts" }));

    await waitFor(() => {
      expect(screen.getByText("Refreshed xPts (120 projections).")).toBeInTheDocument();
    });
  });

  it("shows the create-starter-squad prompt when the squad exists but has no players", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return { ok: true, json: async () => ({ items: [], total: 0 }) } as Response;
      }
      return {
        ok: true,
        json: async () => ({
          squad_id: 4,
          name: "My Team",
          bank: 1.5,
          free_transfers: 1,
          projection_totals: null,
          bench_projection_totals: null,
          captain_adjusted_projection_totals: null,
          gameweek_numbers: [],
          players: [],
        }),
      } as Response;
    });

    render(<MyTeamBoard />);

    await waitFor(() => {
      expect(screen.getByText("No Squad Saved Yet")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Create Starter Squad" })).toBeInTheDocument();
    });
  });
});
