import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MyTeamRecommendationResponse } from "@/lib/api";
import { MyTeamBoard } from "@/components/team/my-team-board";

function buildRecommendationResponse(): MyTeamRecommendationResponse {
  return {
    model_version: "component_v3",
    projection_run_id: 42,
    generated_at: "2026-08-16T08:10:00+00:00",
    target_gameweek_number: 2,
    starting_xi_points: 40.0,
    captain_adjusted_points: 44.5,
    starting_xi: [1, 3, 4, 5, 6, 8, 9, 10, 11, 13, 14],
    bench_goalkeeper: 2,
    bench_outfield: [7, 12, 15],
    captain: 13,
    vice_captain: 14,
    player_projected_points: {
      "1": 4.0, "3": 4.0, "4": 4.0, "5": 4.0, "6": 4.0, "8": 4.0, "9": 4.0,
      "10": 4.0, "11": 4.0, "13": 4.5, "14": 4.0, "2": 2.0, "7": 2.0, "12": 2.0, "15": 2.0,
    },
    current_captain_adjusted_points: 39.5,
  };
}

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

type Squad = ReturnType<typeof buildFullSquadResponse>;

type PutBody = {
  bank: number;
  free_transfers: number;
  players: {
    player_id: number;
    is_starting: boolean;
    bench_order: number | null;
    is_captain: boolean;
    is_vice_captain: boolean;
  }[];
};

/** Same 15 players, but only `starterIds` start; the rest take bench orders 1-4 in id order. */
function withStarters(squad: Squad, starterIds: number[]): Squad {
  let benchOrder = 0;
  return {
    ...squad,
    players: squad.players.map((player) => {
      const isStarting = starterIds.includes(player.player_id);
      if (!isStarting) {
        benchOrder += 1;
      }
      return { ...player, is_starting: isStarting, bench_order: isStarting ? null : benchOrder };
    }),
  };
}

type BackendOptions = {
  squad?: Squad;
  difficultyTeams?: { id: number; name: string; short_name: string; difficulty: number }[];
  putResponse?: () => Response | Promise<Response>;
};

/** Stateful fake API: a successful PUT updates what the next GET returns. */
function installBackend(options: BackendOptions = {}) {
  const squad = options.squad ?? buildFullSquadResponse();
  const putBodies: PutBody[] = [];
  const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/teams")) {
      const items = options.difficultyTeams ?? [];
      return { ok: true, json: async () => ({ items, total: items.length }) } as Response;
    }
    if (url.endsWith("/my-team/recommendation")) {
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    }
    if (url.endsWith("/my-team") && init?.method === "PUT") {
      const body = JSON.parse(String(init.body)) as PutBody;
      putBodies.push(body);
      if (options.putResponse) {
        return options.putResponse();
      }
      squad.bank = body.bank;
      squad.free_transfers = body.free_transfers;
      for (const selection of body.players) {
        const player = squad.players.find((item) => item.player_id === selection.player_id);
        if (player) {
          player.is_starting = selection.is_starting;
          player.bench_order = selection.bench_order;
          player.is_captain = selection.is_captain;
          player.is_vice_captain = selection.is_vice_captain;
        }
      }
      return { ok: true, json: async () => squad } as Response;
    }
    if (url.endsWith("/my-team")) {
      return { ok: true, json: async () => squad } as Response;
    }
    throw new Error(`Unexpected fetch call: ${url}`);
  });
  return { squad, putBodies, fetchMock };
}

function selectButton(name: string): HTMLElement {
  return screen.getByRole("button", { name: `Select ${name}` });
}

function selectionState(name: string): string | null | undefined {
  return selectButton(name).closest("article")?.getAttribute("data-selection-state");
}

async function renderBoard(): Promise<void> {
  render(<MyTeamBoard />);
  await waitFor(() => {
    expect(screen.getByRole("button", { name: "Select GK One" })).toBeInTheDocument();
  });
}

function selectionFor(body: PutBody, playerId: number): PutBody["players"][number] {
  const selection = body.players.find((item) => item.player_id === playerId);
  if (!selection) {
    throw new Error(`Player ${playerId} missing from PUT body`);
  }
  return selection;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("MyTeamBoard", () => {
  it("displays the saved bank rather than one recomputed from current prices", async () => {
    const squad = buildFullSquadResponse();
    squad.bank = 2.3; // 100 - 74.4 would be 25.6; the saved bank is what counts.
    installBackend({ squad });

    await renderBoard();

    expect(screen.getByText("Cost: 74.4")).toBeInTheDocument();
    expect(screen.getByText("Bank: 2.3")).toBeInTheDocument();
    expect(screen.queryByText("Bank: 25.6")).not.toBeInTheDocument();
    expect(screen.queryByText("Free Transfers:")).not.toBeInTheDocument();
    expect(screen.getByText("Gameweek 2")).toBeInTheDocument();
  });

  it("has no Edit Team mode and no inline transfer controls, and does not load the player pool", async () => {
    const { fetchMock } = installBackend();

    await renderBoard();

    expect(screen.queryByRole("button", { name: "Edit Team" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save Changes" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Transfer / })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Replacement Player/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm Transfer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Swap .* with bench/ })).not.toBeInTheDocument();
    const playerPoolCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes("/players"));
    expect(playerPoolCalls).toHaveLength(0);
  });

  it("keeps the Explore transfers link on every card", async () => {
    installBackend();

    await renderBoard();

    const links = screen.getAllByRole("link", { name: /Explore transfers/ });
    expect(links).toHaveLength(15);
    expect(links[0]).toHaveAttribute("href", expect.stringMatching(/^\/transfers\?out=\d+$/));
  });

  it("links every starter and bench card to /transfers?out=<player_id>, with or without a selection", async () => {
    const squad = buildFullSquadResponse();
    installBackend({ squad });

    await renderBoard();

    function expectLinksFor(players: Squad["players"]): void {
      for (const player of players) {
        const card = selectButton(player.web_name).closest("article");
        expect(card).not.toBeNull();
        const link = within(card as HTMLElement).getByRole("link", { name: /Explore transfers/ });
        expect(link).toHaveAttribute("href", `/transfers?out=${player.player_id}`);
      }
    }

    const starters = squad.players.filter((player) => player.is_starting);
    const bench = squad.players.filter((player) => !player.is_starting);
    expect(starters).toHaveLength(11);
    expect(bench).toHaveLength(4);

    expectLinksFor(squad.players);

    // Starter-first and bench-first selection must leave every link in place.
    fireEvent.click(selectButton("DEF One"));
    expectLinksFor(squad.players);
    fireEvent.click(selectButton("DEF One"));
    fireEvent.click(selectButton("GK Two"));
    expectLinksFor(squad.players);
  });

  it("navigates gameweeks and updates opponent labels", async () => {
    installBackend();

    await renderBoard();
    await waitFor(() => {
      expect(screen.getAllByText("Opponent: CHE (H)").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: "Next Game" }));

    await waitFor(() => {
      expect(screen.getByText("Gameweek 3")).toBeInTheDocument();
      expect(screen.getAllByText("Opponent: TOT (A)").length).toBeGreaterThan(0);
    });
  });

  describe("direct selection", () => {
    it("marks the selected player and only its legal swap targets", async () => {
      installBackend();
      await renderBoard();

      expect(selectButton("GK One")).toHaveAttribute("aria-pressed", "false");
      expect(selectionState("GK One")).toBe("idle");

      fireEvent.click(selectButton("GK One"));

      expect(selectButton("GK One")).toHaveAttribute("aria-pressed", "true");
      expect(selectionState("GK One")).toBe("selected");
      expect(selectionState("GK Two")).toBe("target");
      expect(selectionState("DEF Five")).toBe("not-target");
      expect(selectionState("DEF One")).toBe("not-target");

      // An outfield starter can swap with any bench outfielder that keeps the formation legal.
      fireEvent.click(selectButton("DEF One"));

      expect(selectionState("DEF One")).toBe("selected");
      expect(selectionState("DEF Five")).toBe("target");
      expect(selectionState("MID Five")).toBe("target");
      expect(selectionState("FWD Three")).toBe("target");
      expect(selectionState("GK Two")).toBe("not-target");
    });

    it("replaces the selection when a non-target is chosen, without saving", async () => {
      const { putBodies } = installBackend();
      await renderBoard();

      fireEvent.click(selectButton("GK One"));
      fireEvent.click(selectButton("DEF One"));

      expect(selectButton("DEF One")).toHaveAttribute("aria-pressed", "true");
      expect(selectButton("GK One")).toHaveAttribute("aria-pressed", "false");
      expect(putBodies).toHaveLength(0);
    });

    it("cancels the selection by toggling the player or using Clear selection", async () => {
      const { putBodies } = installBackend();
      await renderBoard();

      fireEvent.click(selectButton("GK One"));
      fireEvent.click(selectButton("GK One"));
      expect(selectButton("GK One")).toHaveAttribute("aria-pressed", "false");

      fireEvent.click(selectButton("GK One"));
      fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
      expect(selectButton("GK One")).toHaveAttribute("aria-pressed", "false");
      expect(screen.queryByRole("button", { name: "Clear selection" })).not.toBeInTheDocument();
      expect(putBodies).toHaveLength(0);
    });

    it("says so when the selected player has no legal swap targets", async () => {
      const squad = buildFullSquadResponse();
      // Unusual shape: no bench goalkeeper, so the starting keeper has nobody to swap with.
      squad.players = squad.players.map((player) =>
        player.player_id === 2 ? { ...player, position: "MID" } : player,
      );
      installBackend({ squad });
      await renderBoard();

      fireEvent.click(selectButton("GK One"));

      expect(screen.getByText("No valid swap targets for GK One.")).toBeInTheDocument();
      expect(selectButton("GK One")).toHaveAttribute("aria-pressed", "true");
    });

    it("keeps the viewed gameweek selected after a successful swap and reload", async () => {
      const { putBodies } = installBackend();
      await renderBoard();

      fireEvent.click(screen.getByRole("button", { name: "Next Game" }));
      await waitFor(() => {
        expect(screen.getByText("Gameweek 3")).toBeInTheDocument();
      });

      fireEvent.click(selectButton("GK One"));
      fireEvent.click(selectButton("GK Two"));
      await waitFor(() => {
        expect(putBodies).toHaveLength(1);
      });
      await waitFor(() => {
        expect(screen.getByTestId("swap-confirmation")).toHaveTextContent("Swapped GK One with GK Two.");
      });

      // The squad was reloaded (GK One is now on the bench) yet the gameweek did not reset to 2.
      expect(screen.getByText("ARS · GK · Bench 1")).toBeInTheDocument();
      expect(screen.getByText("Gameweek 3")).toBeInTheDocument();
      expect(screen.queryByText("Gameweek 2")).not.toBeInTheDocument();
    });

    it("does not issue overlapping saves while a swap is in flight", async () => {
      const squad = buildFullSquadResponse();
      let release: () => void = () => undefined;
      const gate = new Promise<void>((resolve) => {
        release = resolve;
      });
      const { putBodies } = installBackend({
        squad,
        putResponse: async () => {
          await gate;
          return { ok: true, json: async () => squad } as Response;
        },
      });
      await renderBoard();

      fireEvent.click(selectButton("GK One"));
      fireEvent.click(selectButton("GK Two"));
      await waitFor(() => {
        expect(putBodies).toHaveLength(1);
      });

      // While the first save is pending, selection is disabled and further clicks do nothing.
      expect(selectButton("GK Two")).toBeDisabled();
      expect(selectButton("DEF One")).toBeDisabled();
      fireEvent.click(selectButton("GK Two"));
      fireEvent.click(selectButton("DEF One"));
      fireEvent.click(selectButton("DEF Five"));
      expect(putBodies).toHaveLength(1);

      release();
      await waitFor(() => {
        expect(screen.getByTestId("swap-confirmation")).toHaveTextContent("Swapped GK One with GK Two.");
      });
      expect(putBodies).toHaveLength(1);
      expect(selectButton("DEF One")).not.toBeDisabled();
    });

    it("offers a swap that leads to a 5-2-3 formation", async () => {
      // Starting 5-3-2: swapping MID One for FWD Three gives 5-2-3, legal under the domain rule (MID 2-5).
      const squad = withStarters(buildFullSquadResponse(), [1, 3, 4, 5, 6, 7, 8, 9, 10, 13, 14]);
      installBackend({ squad });
      await renderBoard();

      fireEvent.click(selectButton("MID One"));

      expect(selectionState("FWD Three")).toBe("target");
    });

    it("disables selection while an optimiser mode is showing and restores it for None", async () => {
      installBackend({
        difficultyTeams: [
          { id: 1, name: "Chelsea", short_name: "CHE", difficulty: 5 },
          { id: 2, name: "Tottenham", short_name: "TOT", difficulty: 1 },
        ],
      });
      await renderBoard();

      const select = screen.getByLabelText("Optimise starting 11 by") as HTMLSelectElement;
      expect(select).toHaveValue("none");

      fireEvent.change(select, { target: { value: "difficulty" } });
      await waitFor(() => {
        expect(screen.queryByRole("button", { name: "Select GK One" })).not.toBeInTheDocument();
      });
      // Projection-related controls remain available.
      expect(screen.getByRole("button", { name: "Refresh xPts" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Next Game" })).toBeInTheDocument();

      fireEvent.change(select, { target: { value: "xpts" } });
      await waitFor(() => {
        expect(screen.queryByRole("button", { name: "Select GK One" })).not.toBeInTheDocument();
      });

      fireEvent.change(select, { target: { value: "none" } });
      await waitFor(() => {
        expect(screen.getByRole("button", { name: "Select GK One" })).toBeInTheDocument();
      });
    });
  });

  describe("swaps and reorders", () => {
    it("swaps a starter with a bench player in one save and confirms it", async () => {
      const { putBodies } = installBackend();
      await renderBoard();

      fireEvent.click(selectButton("GK One"));
      fireEvent.click(selectButton("GK Two"));

      await waitFor(() => {
        expect(putBodies).toHaveLength(1);
      });
      const body = putBodies[0];
      expect(selectionFor(body, 1)).toMatchObject({ is_starting: false, bench_order: 1 });
      expect(selectionFor(body, 2)).toMatchObject({ is_starting: true, bench_order: null });

      await waitFor(() => {
        expect(screen.getByTestId("swap-confirmation")).toHaveAttribute("aria-live", "polite");
        expect(screen.getByTestId("swap-confirmation")).toHaveTextContent("Swapped GK One with GK Two.");
      });

      // The reloaded squad reflects the swap, and the selection is cleared.
      await waitFor(() => {
        expect(screen.getByText("ARS · GK · Bench 1")).toBeInTheDocument();
      });
      expect(selectButton("GK One")).toHaveAttribute("aria-pressed", "false");
    });

    it("updates the confirmation on a second swap", async () => {
      installBackend();
      await renderBoard();

      fireEvent.click(selectButton("GK One"));
      fireEvent.click(selectButton("GK Two"));
      await waitFor(() => {
        expect(screen.getByTestId("swap-confirmation")).toHaveTextContent("Swapped GK One with GK Two.");
      });

      fireEvent.click(selectButton("DEF One"));
      fireEvent.click(selectButton("DEF Five"));
      await waitFor(() => {
        expect(screen.getByTestId("swap-confirmation")).toHaveTextContent("Swapped DEF One with DEF Five.");
      });
    });

    it("swaps in the other direction when a bench player is selected first", async () => {
      const { putBodies } = installBackend();
      await renderBoard();

      fireEvent.click(selectButton("DEF Five"));
      expect(selectionState("DEF One")).toBe("target");
      fireEvent.click(selectButton("DEF One"));

      await waitFor(() => {
        expect(putBodies).toHaveLength(1);
      });
      expect(selectionFor(putBodies[0], 7)).toMatchObject({ is_starting: true, bench_order: null });
      expect(selectionFor(putBodies[0], 3)).toMatchObject({ is_starting: false, bench_order: 2 });
    });

    it("lets the bench goalkeeper be selected first and swapped with the starting goalkeeper", async () => {
      const { putBodies } = installBackend();
      await renderBoard();

      fireEvent.click(selectButton("GK Two"));
      expect(selectionState("GK One")).toBe("target");
      fireEvent.click(selectButton("GK One"));

      await waitFor(() => {
        expect(putBodies).toHaveLength(1);
      });
      expect(selectionFor(putBodies[0], 2)).toMatchObject({ is_starting: true, bench_order: null });
      expect(selectionFor(putBodies[0], 1)).toMatchObject({ is_starting: false, bench_order: 1 });
    });

    it("moves the captain badge to the incoming starter when the captain is benched", async () => {
      const { putBodies } = installBackend();
      await renderBoard();

      fireEvent.click(selectButton("MID One")); // captain
      fireEvent.click(selectButton("MID Five"));

      await waitFor(() => {
        expect(putBodies).toHaveLength(1);
      });
      expect(selectionFor(putBodies[0], 8)).toMatchObject({ is_starting: false, is_captain: false });
      expect(selectionFor(putBodies[0], 12)).toMatchObject({ is_starting: true, is_captain: true });
    });

    it("reorders two outfield bench players, swapping only their bench order", async () => {
      const { putBodies } = installBackend();
      await renderBoard();

      fireEvent.click(selectButton("DEF Five")); // bench 2
      expect(selectionState("MID Five")).toBe("target"); // bench 3
      fireEvent.click(selectButton("MID Five"));

      await waitFor(() => {
        expect(putBodies).toHaveLength(1);
      });
      const body = putBodies[0];
      expect(selectionFor(body, 7)).toMatchObject({ is_starting: false, bench_order: 3 });
      expect(selectionFor(body, 12)).toMatchObject({ is_starting: false, bench_order: 2 });
      expect(selectionFor(body, 2)).toMatchObject({ is_starting: false, bench_order: 1 });
      expect(selectionFor(body, 15)).toMatchObject({ is_starting: false, bench_order: 4 });
      expect(body.players.filter((player) => player.is_starting)).toHaveLength(11);
    });

    it("does not allow the bench goalkeeper to be reordered against outfield subs", async () => {
      const { putBodies } = installBackend();
      await renderBoard();

      fireEvent.click(selectButton("GK Two"));
      expect(selectionState("DEF Five")).toBe("not-target");
      fireEvent.click(selectButton("DEF Five"));

      expect(selectButton("DEF Five")).toHaveAttribute("aria-pressed", "true");
      expect(selectionState("GK Two")).toBe("not-target");
      expect(putBodies).toHaveLength(0);
    });

    it("preserves the saved bank and free transfers on a swap and on a reorder", async () => {
      const squad = buildFullSquadResponse();
      squad.bank = 2.3; // differs from 100 - sum(current_price) = 25.6
      squad.free_transfers = 3;
      const { putBodies } = installBackend({ squad });
      await renderBoard();

      fireEvent.click(selectButton("GK One"));
      fireEvent.click(selectButton("GK Two"));
      await waitFor(() => {
        expect(putBodies).toHaveLength(1);
      });
      expect(putBodies[0].bank).toBe(2.3);
      expect(putBodies[0].free_transfers).toBe(3);

      await waitFor(() => {
        expect(screen.getByText("ARS · GK · Bench 1")).toBeInTheDocument();
      });

      fireEvent.click(selectButton("DEF Five"));
      fireEvent.click(selectButton("MID Five"));
      await waitFor(() => {
        expect(putBodies).toHaveLength(2);
      });
      expect(putBodies[1].bank).toBe(2.3);
      expect(putBodies[1].free_transfers).toBe(3);

      expect(screen.getByText("Bank: 2.3")).toBeInTheDocument();
    });

    it("shows the server message and leaves the displayed squad unchanged when a save is rejected", async () => {
      installBackend({
        putResponse: () =>
          ({
            ok: false,
            status: 400,
            json: async () => ({ detail: "Starting XI must contain between 1 and 1 GK" }),
          }) as Response,
      });
      await renderBoard();

      fireEvent.click(selectButton("GK One"));
      fireEvent.click(selectButton("GK Two"));

      expect(
        await screen.findByText("Starting XI must contain between 1 and 1 GK"),
      ).toBeInTheDocument();
      expect(screen.getByTestId("swap-confirmation")).toBeEmptyDOMElement();
      // GK Two is still the bench goalkeeper (bench 1); GK One still starts.
      expect(screen.getByText("AVL · GK · Bench 1")).toBeInTheDocument();
      expect(screen.queryByText("ARS · GK · Bench 1")).not.toBeInTheDocument();
    });
  });

  describe("projected points visibility", () => {
    const PER_PLAYER_XPTS = /^GW xPts:/;
    const HORIZON_CARD = /^[135] GW xPts$/;

    function installRecommendationBackend(): void {
      const squad = buildFullSquadResponse();
      const recommendation = buildRecommendationResponse();
      vi.spyOn(global, "fetch").mockImplementation(async (input) => {
        const url = String(input);
        if (url.endsWith("/teams")) {
          return { ok: true, json: async () => ({ items: [], total: 0 }) } as Response;
        }
        if (url.endsWith("/my-team/recommendation")) {
          return { ok: true, json: async () => recommendation } as Response;
        }
        return { ok: true, json: async () => squad } as Response;
      });
    }

    function revealControl(): HTMLElement {
      return screen.getByRole("button", { name: "Show projected points" });
    }

    function expectFiguresHidden(): void {
      expect(screen.queryAllByText(PER_PLAYER_XPTS)).toHaveLength(0);
      expect(screen.queryAllByText(HORIZON_CARD)).toHaveLength(0);
      expect(screen.queryByText("This Gameweek")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Current" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Recommended" })).not.toBeInTheDocument();
    }

    it("hides per-player xPts, the 1/3/5 GW cards and the recommendation panel by default", async () => {
      installRecommendationBackend();

      await renderBoard();

      expectFiguresHidden();
      expect(revealControl()).toBeInTheDocument();
    });

    it("keeps the optimiser, gameweek navigation, refresh control and opponents visible while hidden", async () => {
      installRecommendationBackend();

      await renderBoard();

      expect(screen.getByLabelText("Optimise starting 11 by")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Previous Game" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Next Game" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Refresh xPts" })).toBeInTheDocument();
      expect(screen.getByText("Gameweek 2")).toBeInTheDocument();
      expect(screen.getAllByText("Opponent: CHE (H)").length).toBeGreaterThan(0);
    });

    it("reveals all three kinds of figure and hides them again with the same control", async () => {
      installRecommendationBackend();
      await renderBoard();

      fireEvent.click(revealControl());

      expect(screen.getAllByText(PER_PLAYER_XPTS)).toHaveLength(15);
      expect(screen.getAllByText(HORIZON_CARD)).toHaveLength(3);
      expect(await screen.findByText("This Gameweek")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Recommended" })).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Hide projected points" }));

      expectFiguresHidden();
      expect(revealControl()).toBeInTheDocument();
    });

    it("returns to the Current view when figures are hidden while Recommended is active", async () => {
      installRecommendationBackend();
      await renderBoard();

      fireEvent.click(revealControl());
      fireEvent.click(await screen.findByRole("button", { name: "Recommended" }));
      expect(await screen.findByText("Recommended Starting XI")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Hide projected points" }));

      expect(screen.queryByText("Recommended Starting XI")).not.toBeInTheDocument();
      expect(screen.getByText("Starting XI")).toBeInTheDocument();

      fireEvent.click(revealControl());
      expect(screen.getByRole("button", { name: "Current" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      expect(screen.queryByText("Recommended Starting XI")).not.toBeInTheDocument();
    });

    it("hides the figures again after unmounting and remounting", async () => {
      installRecommendationBackend();
      const first = render(<MyTeamBoard />);
      await waitFor(() => {
        expect(screen.getByRole("button", { name: "Select GK One" })).toBeInTheDocument();
      });
      fireEvent.click(revealControl());
      expect(screen.getAllByText(PER_PLAYER_XPTS)).toHaveLength(15);

      first.unmount();
      await renderBoard();

      expectFiguresHidden();
      expect(revealControl()).toBeInTheDocument();
    });

    it("never persists the reveal state in localStorage, sessionStorage or cookies", async () => {
      installRecommendationBackend();
      const setItem = vi.spyOn(Storage.prototype, "setItem");
      await renderBoard();

      fireEvent.click(revealControl());
      fireEvent.click(screen.getByRole("button", { name: "Hide projected points" }));

      expect(setItem).not.toHaveBeenCalled();
      expect(window.localStorage.length).toBe(0);
      expect(window.sessionStorage.length).toBe(0);
      expect(document.cookie).toBe("");
    });

    it("still shows the recommendation failure state once figures are revealed", async () => {
      const squad = buildFullSquadResponse();
      vi.spyOn(global, "fetch").mockImplementation(async (input) => {
        const url = String(input);
        if (url.endsWith("/teams")) {
          return { ok: true, json: async () => ({ items: [], total: 0 }) } as Response;
        }
        if (url.endsWith("/my-team/recommendation")) {
          return {
            ok: false,
            status: 422,
            json: async () => ({
              detail: { code: "missing_player_projections", message: "Projections missing", missing_player_ids: [9] },
            }),
          } as Response;
        }
        return { ok: true, json: async () => squad } as Response;
      });
      await renderBoard();
      expect(screen.queryByText("Projections missing")).not.toBeInTheDocument();

      fireEvent.click(revealControl());

      expect(await screen.findByText("Projections missing")).toBeInTheDocument();
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
      if (url.endsWith("/my-team/recommendation")) {
        return { ok: false, status: 404, json: async () => ({}) } as Response;
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

    // recommendation intentionally left unmocked; the empty-squad view never
    // triggers a recommendation fetch since it renders before any player data
    // is available.

    render(<MyTeamBoard />);

    await waitFor(() => {
      expect(screen.getByText("No Squad Saved Yet")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Create Starter Squad" })).toBeInTheDocument();
    });
  });

  it("renders the recommendation summary and lets the user switch between Current and Recommended", async () => {
    const squadResponse = buildFullSquadResponse();
    const recommendationResponse = buildRecommendationResponse();
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return { ok: true, json: async () => ({ items: [], total: 0 }) } as Response;
      }
      if (url.endsWith("/my-team/recommendation")) {
        return { ok: true, json: async () => recommendationResponse } as Response;
      }
      return { ok: true, json: async () => squadResponse } as Response;
    });

    render(<MyTeamBoard />);

    fireEvent.click(await screen.findByRole("button", { name: "Show projected points" }));

    await waitFor(() => {
      expect(screen.getByText("GW 2")).toBeInTheDocument();
      expect(screen.getByText(/component_v3 · generated/)).toBeInTheDocument();
    });

    // Current view is shown by default, with the existing Starting XI/Bench headings.
    expect(screen.getByText("Starting XI")).toBeInTheDocument();
    expect(screen.getByText("Bench")).toBeInTheDocument();
    expect(screen.queryByText("Recommended Starting XI")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Recommended" }));

    await waitFor(() => {
      expect(screen.getByText("Recommended Starting XI")).toBeInTheDocument();
      expect(screen.getByText("Recommended Bench")).toBeInTheDocument();
    });
    expect(screen.queryByText("Starting XI")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Current" }));

    await waitFor(() => {
      expect(screen.getByText("Starting XI")).toBeInTheDocument();
    });
  });

  it("never issues a PUT to persist the squad merely from loading a recommendation", async () => {
    const squadResponse = buildFullSquadResponse();
    const recommendationResponse = buildRecommendationResponse();
    const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return { ok: true, json: async () => ({ items: [], total: 0 }) } as Response;
      }
      if (url.endsWith("/my-team/recommendation")) {
        return { ok: true, json: async () => recommendationResponse } as Response;
      }
      return { ok: true, json: async () => squadResponse } as Response;
    });

    render(<MyTeamBoard />);

    fireEvent.click(await screen.findByRole("button", { name: "Show projected points" }));

    await waitFor(() => {
      expect(screen.getByText("GW 2")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Recommended" }));

    await waitFor(() => {
      expect(screen.getByText("Recommended Starting XI")).toBeInTheDocument();
    });

    const putCalls = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === "PUT",
    );
    expect(putCalls).toHaveLength(0);
  });

  it("shows the structured 422 failure when squad players are missing projections", async () => {
    const squadResponse = buildFullSquadResponse();
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return { ok: true, json: async () => ({ items: [], total: 0 }) } as Response;
      }
      if (url.endsWith("/my-team/recommendation")) {
        return {
          ok: false,
          status: 422,
          json: async () => ({
            detail: {
              code: "missing_player_projections",
              message: "1 squad player(s) have no component_v3 projection in run 42",
              missing_player_ids: [9],
            },
          }),
        } as Response;
      }
      return { ok: true, json: async () => squadResponse } as Response;
    });

    render(<MyTeamBoard />);

    fireEvent.click(await screen.findByRole("button", { name: "Show projected points" }));

    await waitFor(() => {
      expect(
        screen.getByText("1 squad player(s) have no component_v3 projection in run 42"),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("Missing projections for: MID Two.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recommended" })).toBeDisabled();
  });
});
