import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FixtureTicker } from "@/components/fixtures/fixture-ticker";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("FixtureTicker", () => {
  it("renders loaded fixture rows", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          {
            fixture_id: 1,
            gameweek_number: 2,
            kickoff_time: "2026-08-21T18:30:00+00:00",
            home_team_short_name: "ARS",
            away_team_short_name: "AVL",
            finished: false,
          },
        ],
        total: 1,
      }),
    } as Response);

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("ARS vs AVL")).toBeInTheDocument();
      expect(screen.getByText("Showing 1 fixtures")).toBeInTheDocument();
    });

    expect(fetchSpy).toHaveBeenCalledWith("http://127.0.0.1:8000/fixtures/ticker?limit=20");
  });

  it("applies filters and refetches ticker", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [],
        total: 0,
      }),
    } as Response);

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    fireEvent.change(screen.getByLabelText("Fixture limit"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Filter by team id"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Filter by gameweek"), { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenLastCalledWith(
        "http://127.0.0.1:8000/fixtures/ticker?limit=5&team_id=3&gameweek=7"
      );
    });
  });

  it("renders empty state", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [],
        total: 0,
      }),
    } as Response);

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("No upcoming fixtures found.")).toBeInTheDocument();
    });
  });

  it("renders error state", async () => {
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("fixtures unavailable"));

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("fixtures unavailable")).toBeInTheDocument();
    });
  });
});
