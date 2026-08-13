import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PlanBoard } from "@/components/plans/plan-board";

type PlanGameweekOverrides = {
  gameweek_number: number;
  chip?: string | null;
  free_transfers_available?: number;
  unlimited_transfers?: boolean;
  transfers_made?: number;
  points_hit?: number;
  total_points?: number;
};

function buildPlayers() {
  return [
    { player_id: 1, web_name: "GK One", position: "GK", is_starting: true, bench_order: null },
    { player_id: 2, web_name: "GK Two", position: "GK", is_starting: false, bench_order: 1 },
    { player_id: 3, web_name: "DEF One", position: "DEF", is_starting: true, bench_order: null },
    { player_id: 4, web_name: "DEF Two", position: "DEF", is_starting: true, bench_order: null },
    { player_id: 5, web_name: "DEF Three", position: "DEF", is_starting: true, bench_order: null },
    { player_id: 6, web_name: "DEF Four", position: "DEF", is_starting: true, bench_order: null },
    { player_id: 7, web_name: "DEF Five", position: "DEF", is_starting: false, bench_order: 2 },
    { player_id: 8, web_name: "MID One", position: "MID", is_starting: true, bench_order: null },
    { player_id: 9, web_name: "MID Two", position: "MID", is_starting: true, bench_order: null },
    { player_id: 10, web_name: "MID Three", position: "MID", is_starting: true, bench_order: null },
    { player_id: 11, web_name: "MID Four", position: "MID", is_starting: true, bench_order: null },
    { player_id: 12, web_name: "MID Five", position: "MID", is_starting: false, bench_order: 3 },
    { player_id: 13, web_name: "FWD One", position: "FWD", is_starting: true, bench_order: null },
    { player_id: 14, web_name: "FWD Two", position: "FWD", is_starting: true, bench_order: null },
    { player_id: 15, web_name: "FWD Three", position: "FWD", is_starting: false, bench_order: 4 },
  ].map((player) => ({
    ...player,
    team_short_name: "ARS",
    current_price: 5.0,
    status: "a",
    is_captain: player.player_id === 13,
    is_vice_captain: player.player_id === 9,
    projected_points: player.is_starting ? 4 : 2,
    fixtures: [
      {
        fixture_id: player.player_id,
        projected_points: player.is_starting ? 4 : 2,
        kickoff_time: "2026-08-15T15:00:00+00:00",
        opponent_team_short_name: "CHE",
        is_home: true,
      },
    ],
  }));
}

function buildPlan(gameweeks: PlanGameweekOverrides[] = [{ gameweek_number: 1 }]) {
  return {
    plan_id: 1,
    name: "No Haaland GW1",
    start_gameweek: gameweeks[0].gameweek_number,
    end_gameweek: gameweeks[gameweeks.length - 1].gameweek_number,
    initial_bank: 0.5,
    initial_free_transfers: 1,
    total_points: 50,
    total_points_hit: 0,
    gameweeks: gameweeks.map((gameweek) => ({
      chip: null,
      bank: 0.5,
      free_transfers_available: 1,
      unlimited_transfers: false,
      transfers_made: 0,
      points_hit: 0,
      starting_points: 44,
      bench_points: 8,
      captain_bonus_points: 4,
      total_points: 48,
      players: buildPlayers(),
      transfers_in: [],
      transfers_out: [],
      ...gameweek,
    })),
  };
}

function mockFetch(plan: ReturnType<typeof buildPlan>, saved?: ReturnType<typeof buildPlan>) {
  const saveCalls: { url: string; body: unknown }[] = [];

  vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);

    if (init?.method === "PUT") {
      saveCalls.push({ url, body: JSON.parse(String(init.body)) });
      return new Response(JSON.stringify(saved ?? plan), { status: 200 });
    }
    if (url.includes("/players?")) {
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 99,
              web_name: "New Mid",
              first_name: "New",
              second_name: "Mid",
              team_name: "Chelsea",
              team_short_name: "CHE",
              position: "MID",
              current_price: 5.0,
              status: "a",
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        }),
        { status: 200 },
      );
    }

    return new Response(JSON.stringify(plan), { status: 200 });
  });

  return saveCalls;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("PlanBoard", () => {
  it("renders the plan name and a rail of gameweeks", async () => {
    mockFetch(buildPlan([{ gameweek_number: 1 }, { gameweek_number: 2 }, { gameweek_number: 3 }]));

    render(<PlanBoard planId={1} />);

    expect(await screen.findByText("No Haaland GW1")).toBeInTheDocument();
    expect(screen.getByLabelText("Gameweek 1")).toBeInTheDocument();
    expect(screen.getByLabelText("Gameweek 3")).toBeInTheDocument();
  });

  it("switches the squad view when another gameweek is selected", async () => {
    mockFetch(buildPlan([{ gameweek_number: 1 }, { gameweek_number: 2, free_transfers_available: 2 }]));

    render(<PlanBoard planId={1} />);
    fireEvent.click(await screen.findByLabelText("Gameweek 2"));

    expect(await screen.findByText(/Gameweek 2/)).toBeInTheDocument();
    expect(screen.getByText(/Free transfers 2/)).toBeInTheDocument();
  });

  it("shows gameweek one as having unlimited transfers", async () => {
    mockFetch(buildPlan([{ gameweek_number: 1, unlimited_transfers: true }]));

    render(<PlanBoard planId={1} />);

    expect(await screen.findByText(/Free transfers unlimited/)).toBeInTheDocument();
  });

  it("disables a chip already used in the same half of the season", async () => {
    mockFetch(
      buildPlan([
        { gameweek_number: 1, chip: "BENCH_BOOST" },
        { gameweek_number: 2 },
      ]),
    );

    render(<PlanBoard planId={1} />);
    fireEvent.click(await screen.findByLabelText("Gameweek 2"));

    expect(screen.getByLabelText("Bench Boost")).toBeDisabled();
    expect(screen.getByLabelText("Wildcard")).toBeEnabled();
  });

  it("sends the selected chip when the gameweek is saved", async () => {
    const saveCalls = mockFetch(buildPlan([{ gameweek_number: 1 }]));

    render(<PlanBoard planId={1} />);
    fireEvent.click(await screen.findByLabelText("Triple Captain"));
    fireEvent.click(screen.getByRole("button", { name: "Save Gameweek" }));

    await waitFor(() => expect(saveCalls).toHaveLength(1));
    expect(saveCalls[0].url).toContain("/plans/1/gameweeks/1");
    expect((saveCalls[0].body as { chip: string }).chip).toBe("TRIPLE_CAPTAIN");
  });

  it("rejects a swap that would break the formation", async () => {
    mockFetch(buildPlan([{ gameweek_number: 1 }]));

    render(<PlanBoard planId={1} />);
    fireEvent.click(await screen.findByLabelText("Swap GK One with bench"));
    fireEvent.click(screen.getByLabelText("Swap GK One for DEF Five"));

    expect(
      await screen.findByText("That swap would leave an illegal formation."),
    ).toBeInTheDocument();
  });

  it("stages a transfer in the draft squad", async () => {
    const saveCalls = mockFetch(buildPlan([{ gameweek_number: 1 }]));

    render(<PlanBoard planId={1} />);
    fireEvent.click(await screen.findByLabelText("Transfer MID One"));
    fireEvent.click(await screen.findByLabelText("Transfer in New Mid"));
    fireEvent.click(screen.getByRole("button", { name: "Save Gameweek" }));

    await waitFor(() => expect(saveCalls).toHaveLength(1));
    const body = saveCalls[0].body as { players: { player_id: number }[] };
    expect(body.players.map((player) => player.player_id)).toContain(99);
    expect(body.players.map((player) => player.player_id)).not.toContain(8);
  });

  it("surfaces a rule violation from the API", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      if (init?.method === "PUT") {
        return new Response(
          JSON.stringify({ detail: { code: "budget", message: "Gameweek 1 goes over budget" } }),
          { status: 422 },
        );
      }
      return new Response(JSON.stringify(buildPlan([{ gameweek_number: 1 }])), { status: 200 });
    });

    render(<PlanBoard planId={1} />);
    fireEvent.click(await screen.findByRole("button", { name: "Save Gameweek" }));

    expect(await screen.findByText("Gameweek 1 goes over budget")).toBeInTheDocument();
  });
});
