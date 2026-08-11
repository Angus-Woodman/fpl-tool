import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MyTeamBoard } from "@/components/team/my-team-board";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("MyTeamBoard", () => {
  it("renders persisted squad data", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        squad_id: 1,
        name: "My Team",
        bank: 1.5,
        free_transfers: 2,
        projection_totals: { horizon_1: 5.5, horizon_3: 14.0, horizon_5: 21.0 },
        bench_projection_totals: { horizon_1: 2.0, horizon_3: 4.0, horizon_5: 6.0 },
        captain_adjusted_projection_totals: { horizon_1: 9.0, horizon_3: 22.0, horizon_5: 31.0 },
        players: [
          {
            player_id: 1,
            web_name: "Saka",
            first_name: "Bukayo",
            second_name: "Saka",
            team_name: "Arsenal",
            team_short_name: "ARS",
            position: "MID",
            current_price: 10.5,
            status: "a",
            is_starting: true,
            bench_order: null,
            is_captain: true,
            is_vice_captain: false,
            projection_totals: { horizon_1: 5.0, horizon_3: 13.0, horizon_5: 18.0 },
          },
          {
            player_id: 2,
            web_name: "Turner",
            first_name: "Matt",
            second_name: "Turner",
            team_name: "Forest",
            team_short_name: "NFO",
            position: "GK",
            current_price: 4.0,
            status: "a",
            is_starting: false,
            bench_order: 1,
            is_captain: false,
            is_vice_captain: true,
            projection_totals: { horizon_1: 2.0, horizon_3: 4.0, horizon_5: 6.0 },
          },
        ],
      }),
    } as Response);

    render(<MyTeamBoard />);

    await waitFor(() => {
      expect(screen.getByText("My Team")).toBeInTheDocument();
      expect(screen.getByText("Bank: 1.5")).toBeInTheDocument();
      expect(screen.getByText("Free Transfers: 2")).toBeInTheDocument();
      expect(screen.getByText("1 GW xPts")).toBeInTheDocument();
      expect(screen.getByText("9.0")).toBeInTheDocument();
      expect(screen.getByText("3 GW xPts")).toBeInTheDocument();
      expect(screen.getByText("22.0")).toBeInTheDocument();
      expect(screen.getByText("Saka")).toBeInTheDocument();
      expect(screen.getByText("xPts 1/3/5: 5.0 / 13.0 / 18.0")).toBeInTheDocument();
      expect(screen.getByText("Turner")).toBeInTheDocument();
      expect(screen.getByText("Bench 1 · NFO · GK")).toBeInTheDocument();
      expect(screen.getByText("C")).toBeInTheDocument();
      expect(screen.getByText("VC")).toBeInTheDocument();
    });
  });

  it("renders empty state when no squad exists", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({ status: 404, ok: false } as Response);

    render(<MyTeamBoard />);

    await waitFor(() => {
      expect(screen.getByText("No Squad Saved Yet")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Create Starter Squad" })).toBeInTheDocument();
    });
  });

  it("creates a starter squad from the empty state", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/my-team") && !init) {
        if (fetchMock.mock.calls.filter(([calledUrl]) => String(calledUrl).endsWith("/my-team") && !init).length === 1) {
          return { status: 404, ok: false } as Response;
        }

        return {
          ok: true,
          json: async () => ({
            squad_id: 1,
            name: "My Team",
            bank: 0,
            free_transfers: 1,
            projection_totals: null,
            bench_projection_totals: null,
            captain_adjusted_projection_totals: null,
            players: [
              {
                player_id: 1,
                web_name: "GK One",
                first_name: "GK",
                second_name: "One",
                team_name: "Arsenal",
                team_short_name: "ARS",
                position: "GK",
                current_price: 4.0,
                status: "a",
                is_starting: true,
                bench_order: null,
                is_captain: false,
                is_vice_captain: false,
                projection_totals: null,
              },
            ],
          }),
        } as Response;
      }

      if (url.includes("/players?") && url.includes("position=GK")) {
        return {
          ok: true,
          json: async () => ({
            items: [
              { id: 1, web_name: "GK One", first_name: "GK", second_name: "One", team_name: "Arsenal", team_short_name: "ARS", position: "GK", current_price: 4.0, status: "a" },
              { id: 2, web_name: "GK Two", first_name: "GK", second_name: "Two", team_name: "Villa", team_short_name: "AVL", position: "GK", current_price: 4.1, status: "a" },
            ],
            total: 2,
            page: 1,
            page_size: 50,
          }),
        } as Response;
      }

      if (url.includes("/players?") && url.includes("position=DEF")) {
        return {
          ok: true,
          json: async () => ({
            items: [
              { id: 3, web_name: "DEF One", first_name: "DEF", second_name: "One", team_name: "Arsenal", team_short_name: "ARS", position: "DEF", current_price: 4.0, status: "a" },
              { id: 4, web_name: "DEF Two", first_name: "DEF", second_name: "Two", team_name: "Villa", team_short_name: "AVL", position: "DEF", current_price: 4.1, status: "a" },
              { id: 5, web_name: "DEF Three", first_name: "DEF", second_name: "Three", team_name: "Bournemouth", team_short_name: "BOU", position: "DEF", current_price: 4.2, status: "a" },
              { id: 6, web_name: "DEF Four", first_name: "DEF", second_name: "Four", team_name: "Chelsea", team_short_name: "CHE", position: "DEF", current_price: 4.3, status: "a" },
              { id: 7, web_name: "DEF Five", first_name: "DEF", second_name: "Five", team_name: "Everton", team_short_name: "EVE", position: "DEF", current_price: 4.4, status: "a" },
            ],
            total: 5,
            page: 1,
            page_size: 80,
          }),
        } as Response;
      }

      if (url.includes("/players?") && url.includes("position=MID")) {
        return {
          ok: true,
          json: async () => ({
            items: [
              { id: 8, web_name: "MID One", first_name: "MID", second_name: "One", team_name: "Fulham", team_short_name: "FUL", position: "MID", current_price: 5.0, status: "a" },
              { id: 9, web_name: "MID Two", first_name: "MID", second_name: "Two", team_name: "Leicester", team_short_name: "LEI", position: "MID", current_price: 5.1, status: "a" },
              { id: 10, web_name: "MID Three", first_name: "MID", second_name: "Three", team_name: "Liverpool", team_short_name: "LIV", position: "MID", current_price: 5.2, status: "a" },
              { id: 11, web_name: "MID Four", first_name: "MID", second_name: "Four", team_name: "Man City", team_short_name: "MCI", position: "MID", current_price: 5.3, status: "a" },
              { id: 12, web_name: "MID Five", first_name: "MID", second_name: "Five", team_name: "Newcastle", team_short_name: "NEW", position: "MID", current_price: 5.4, status: "a" },
            ],
            total: 5,
            page: 1,
            page_size: 80,
          }),
        } as Response;
      }

      if (url.includes("/players?") && url.includes("position=FWD")) {
        return {
          ok: true,
          json: async () => ({
            items: [
              { id: 13, web_name: "FWD One", first_name: "FWD", second_name: "One", team_name: "Palace", team_short_name: "CRY", position: "FWD", current_price: 6.0, status: "a" },
              { id: 14, web_name: "FWD Two", first_name: "FWD", second_name: "Two", team_name: "Spurs", team_short_name: "TOT", position: "FWD", current_price: 6.1, status: "a" },
              { id: 15, web_name: "FWD Three", first_name: "FWD", second_name: "Three", team_name: "West Ham", team_short_name: "WHU", position: "FWD", current_price: 6.2, status: "a" },
            ],
            total: 3,
            page: 1,
            page_size: 50,
          }),
        } as Response;
      }

      if (url.endsWith("/my-team") && init?.method === "PUT") {
        return {
          ok: true,
          json: async () => ({
            squad_id: 1,
            name: "My Team",
            bank: 0,
            free_transfers: 1,
            projection_totals: null,
            bench_projection_totals: null,
            captain_adjusted_projection_totals: null,
            players: [],
          }),
        } as Response;
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(<MyTeamBoard />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Create Starter Squad" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Create Starter Squad" }));

    await waitFor(() => {
      expect(screen.getByText("GK One")).toBeInTheDocument();
    });

    const putCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url).endsWith("/my-team") && init?.method === "PUT"
    );
    expect(putCall).toBeDefined();
  });

  it("renders error state when fetch fails", async () => {
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("team unavailable"));

    render(<MyTeamBoard />);

    await waitFor(() => {
      expect(screen.getByText("team unavailable")).toBeInTheDocument();
    });
  });
});