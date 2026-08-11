import { cleanup, render, screen, waitFor } from "@testing-library/react";
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
    });
  });

  it("renders error state when fetch fails", async () => {
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("team unavailable"));

    render(<MyTeamBoard />);

    await waitFor(() => {
      expect(screen.getByText("team unavailable")).toBeInTheDocument();
    });
  });
});