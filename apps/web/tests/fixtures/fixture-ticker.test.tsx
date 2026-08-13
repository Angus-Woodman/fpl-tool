import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FixtureTicker } from "@/components/fixtures/fixture-ticker";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const TEAMS = [
  { id: 1, name: "Arsenal", short_name: "ARS", difficulty: 4 },
  { id: 2, name: "Aston Villa", short_name: "AVL", difficulty: 3 },
];

const GAMEWEEKS = Array.from({ length: 8 }, (_, index) => ({
  id: index + 1,
  number: index + 1,
  name: `Gameweek ${index + 1}`,
  is_current: false,
  is_next: index === 0,
  is_finished: false,
}));

function fixtureFor(gameweekNumber: number, homeDifficulty: number, awayDifficulty: number) {
  return {
    fixture_id: gameweekNumber,
    gameweek_number: gameweekNumber,
    kickoff_time: "2026-08-21T18:30:00+00:00",
    home_team_short_name: "ARS",
    away_team_short_name: "AVL",
    home_team_difficulty: homeDifficulty,
    away_team_difficulty: awayDifficulty,
    finished: false,
  };
}

function mockFetch(fixturesByGameweek: Record<number, ReturnType<typeof fixtureFor>[]>) {
  return vi.spyOn(global, "fetch").mockImplementation(async (input) => {
    const url = String(input);

    if (url.endsWith("/teams")) {
      return { ok: true, json: async () => ({ items: TEAMS, total: TEAMS.length }) } as Response;
    }

    if (url.endsWith("/gameweeks")) {
      return {
        ok: true,
        json: async () => ({ items: GAMEWEEKS, total: GAMEWEEKS.length }),
      } as Response;
    }

    const gameweekMatch = /gameweek=(\d+)/.exec(url);
    const gameweekNumber = gameweekMatch ? Number(gameweekMatch[1]) : undefined;
    const items =
      gameweekNumber !== undefined ? (fixturesByGameweek[gameweekNumber] ?? []) : [];

    return {
      ok: true,
      json: async () => ({ items, total: items.length, page: 1, page_size: 20 }),
    } as Response;
  });
}

describe("FixtureTicker", () => {
  it("renders a team x gameweek grid with difficulty-coded opponents", async () => {
    mockFetch({ 1: [fixtureFor(1, 3, 4)] });

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("GW1")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("AVL (H)")).toBeInTheDocument();
      expect(screen.getByText("ARS (A)")).toBeInTheDocument();
    });

    expect(screen.getByText("ARS")).toBeInTheDocument();
    expect(screen.getByText("AVL")).toBeInTheDocument();
  });

  it("navigates the gameweek window with Prev/Next", async () => {
    const fetchSpy = mockFetch({ 1: [fixtureFor(1, 3, 4)], 2: [fixtureFor(2, 3, 4)] });

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("GW1")).toBeInTheDocument();
      expect(screen.getByText("GW6")).toBeInTheDocument();
    });

    expect(screen.getByLabelText("Previous gameweeks")).toBeDisabled();

    fireEvent.click(screen.getByLabelText("Next gameweeks"));

    await waitFor(() => {
      expect(screen.getByText("GW7")).toBeInTheDocument();
      expect(screen.queryByText("GW1")).not.toBeInTheDocument();
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/fixtures/ticker?page=1&limit=20&gameweek=7"
    );
  });

  it("sorts teams via the sort dropdown (A-Z, easiest, hardest)", async () => {
    mockFetch({ 1: [fixtureFor(1, 3, 4)] });

    const { container } = render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("AVL (H)")).toBeInTheDocument();
    });

    function rowLabels(): (string | null)[] {
      return Array.from(container.querySelectorAll("tbody tr td:first-child span")).map(
        (cell) => cell.textContent
      );
    }

    expect(rowLabels()).toEqual(["ARS", "AVL"]);

    fireEvent.change(screen.getByLabelText("Sort teams"), {
      target: { value: "hardest-first" },
    });
    await waitFor(() => {
      expect(rowLabels()).toEqual(["ARS", "AVL"]);
    });

    fireEvent.change(screen.getByLabelText("Sort teams"), {
      target: { value: "easiest-first" },
    });
    await waitFor(() => {
      expect(rowLabels()).toEqual(["AVL", "ARS"]);
    });

    fireEvent.change(screen.getByLabelText("Sort teams"), { target: { value: "alphabetical" } });
    await waitFor(() => {
      expect(rowLabels()).toEqual(["ARS", "AVL"]);
    });
  });

  it("re-sorts by the total difficulty across the whole visible window when it changes", async () => {
    mockFetch({
      1: [fixtureFor(1, 3, 4)],
      3: [
        {
          fixture_id: 30,
          gameweek_number: 3,
          kickoff_time: "2026-09-04T18:30:00+00:00",
          home_team_short_name: "AVL",
          away_team_short_name: "ARS",
          home_team_difficulty: 1,
          away_team_difficulty: 5,
          finished: false,
        },
      ],
    });

    const { container } = render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("AVL (H)")).toBeInTheDocument();
    });

    function rowLabels(): (string | null)[] {
      return Array.from(container.querySelectorAll("tbody tr td:first-child span")).map(
        (cell) => cell.textContent
      );
    }

    fireEvent.change(screen.getByLabelText("Sort teams"), {
      target: { value: "hardest-first" },
    });
    fireEvent.change(screen.getByLabelText("Gameweek window size"), {
      target: { value: "2" },
    });

    // Window covers only GW1 (ARS faces a difficulty-4 AVL, AVL faces a difficulty-3 ARS).
    await waitFor(() => {
      expect(rowLabels()).toEqual(["ARS", "AVL"]);
    });

    fireEvent.change(screen.getByLabelText("Gameweek window size"), {
      target: { value: "3" },
    });

    // GW3 tips AVL's cumulative difficulty above ARS's, flipping the order.
    await waitFor(() => {
      expect(rowLabels()).toEqual(["AVL", "ARS"]);
    });
  });

  it("adjusts the visible gameweek window size", async () => {
    mockFetch({ 1: [fixtureFor(1, 3, 4)] });

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("GW1")).toBeInTheDocument();
      expect(screen.getByText("GW6")).toBeInTheDocument();
      expect(screen.queryByText("GW7")).not.toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Gameweek window size"), {
      target: { value: "2" },
    });

    await waitFor(() => {
      expect(screen.getByText("GW1")).toBeInTheDocument();
      expect(screen.getByText("GW2")).toBeInTheDocument();
      expect(screen.queryByText("GW3")).not.toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Gameweek window size"), {
      target: { value: "10" },
    });

    await waitFor(() => {
      expect(screen.getByText("GW8")).toBeInTheDocument();
    });
  });

  it("saves an edited team difficulty and refreshes fixture colours", async () => {
    const fetchSpy = mockFetch({ 1: [fixtureFor(1, 3, 4)] });
    fetchSpy.mockImplementation(async (input, init) => {
      const url = String(input);

      if (url.endsWith("/teams")) {
        return { ok: true, json: async () => ({ items: TEAMS, total: TEAMS.length }) } as Response;
      }

      if (url.endsWith("/gameweeks")) {
        return {
          ok: true,
          json: async () => ({ items: GAMEWEEKS, total: GAMEWEEKS.length }),
        } as Response;
      }

      if (url.endsWith("/teams/1") && init?.method === "PATCH") {
        return {
          ok: true,
          json: async () => ({ id: 1, name: "Arsenal", short_name: "ARS", difficulty: 1 }),
        } as Response;
      }

      const gameweekMatch = /gameweek=(\d+)/.exec(url);
      const gameweekNumber = gameweekMatch ? Number(gameweekMatch[1]) : undefined;
      const items = gameweekNumber === 1 ? [fixtureFor(1, 3, 1)] : [];

      return {
        ok: true,
        json: async () => ({ items, total: items.length, page: 1, page_size: 20 }),
      } as Response;
    });

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("AVL (H)")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("ARS difficulty"), { target: { value: "1" } });

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "http://127.0.0.1:8000/teams/1",
        expect.objectContaining({ method: "PATCH" })
      );
    });

    await waitFor(() => {
      expect(screen.getByLabelText("ARS difficulty")).toHaveValue("1");
    });
  });
});
