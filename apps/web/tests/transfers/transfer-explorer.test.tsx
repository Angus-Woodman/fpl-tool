import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TransferExplorerResponse } from "@/lib/api";
import { TransferExplorer } from "@/components/transfers/transfer-explorer";

const { useSearchParams, useRouter } = vi.hoisted(() => ({
  useSearchParams: vi.fn(),
  useRouter: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams,
  useRouter,
}));

function makeSearchParams(params: Record<string, string> = {}): URLSearchParams {
  return new URLSearchParams(params);
}

const routerPush = vi.fn();

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  routerPush.mockClear();
});

function buildSquadResponse() {
  const players = [
    { player_id: 1, web_name: "GK One", position: "GK", team_short_name: "ARS" },
    { player_id: 9, web_name: "MID Nine", position: "MID", team_short_name: "LIV" },
  ];

  return {
    squad_id: 1,
    name: "My Team",
    bank: 1.5,
    free_transfers: 2,
    projection_totals: null,
    bench_projection_totals: null,
    captain_adjusted_projection_totals: null,
    gameweek_numbers: [],
    players: players.map((player) => ({
      ...player,
      first_name: player.web_name,
      second_name: player.web_name,
      team_name: player.team_short_name,
      current_price: 5.0,
      status: "a",
      is_starting: true,
      bench_order: null,
      is_captain: false,
      is_vice_captain: false,
      projection_totals: null,
      fixture_projections: [],
    })),
  };
}

function buildExplorerResponse(): TransferExplorerResponse {
  return {
    model_version: "component_v3",
    projection_run_id: 42,
    generated_at: "2026-08-16T08:10:00+00:00",
    primary_horizon: 5,
    bank: 1.5,
    selling_price_is_approximate: true,
    outgoing: {
      player_id: 9,
      web_name: "MID Nine",
      position: "MID",
      team_short_name: "LIV",
      current_price: 5.0,
      selling_price: 5.0,
      projected_points_by_horizon: { "1": 3.3, "3": 9.0, "5": 15.0 },
    },
    candidates: [
      { player_id: 201, web_name: "Low1High5", team_short_name: "AVL", price: 5.5, resulting_bank: 1.0, team_gain_by_horizon: { "1": 0.2, "3": 1.0, "5": 5.0 }, direct_xpts_difference: 0.5, gameweeks_evaluated: 5 },
      { player_id: 202, web_name: "High1Low5", team_short_name: "CHE", price: 5.0, resulting_bank: 1.5, team_gain_by_horizon: { "1": 2.0, "3": 2.5, "5": 2.6 }, direct_xpts_difference: 1.2, gameweeks_evaluated: 5 },
    ],
    evaluated_gameweek_numbers: [5, 6, 7, 8, 9],
  };
}

function mockFetchWith(explorerResult: unknown, explorerStatus = 200): void {
  vi.spyOn(global, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/my-team")) {
      return { ok: true, json: async () => buildSquadResponse() } as Response;
    }
    if (url.includes("/my-team/transfers/")) {
      return {
        ok: explorerStatus === 200,
        status: explorerStatus,
        json: async () => explorerResult,
      } as Response;
    }
    throw new Error(`Unexpected fetch call: ${url}`);
  });
}

function buildPreviewResponseBody() {
  return {
    model_version: "component_v3",
    projection_run_id: 42,
    generated_at: "2026-08-16T08:10:00+00:00",
    target_gameweek_number: 5,
    bank: 1.5,
    resulting_bank: 1.0,
    selling_price_is_approximate: true,
    player_out_id: 9,
    player_in_id: 201,
    is_legal: true,
    errors: [],
    projected_team_gain: 2.6,
    direct_player_xpts_difference: 1.2,
    lineup_before: {
      starting_xi: [1, 3, 9],
      bench_goalkeeper: 2,
      bench_outfield: [4, 5, 6],
      captain: 9,
      vice_captain: 1,
      starting_xi_points: 30.0,
      captain_adjusted_points: 33.3,
    },
    lineup_after: {
      starting_xi: [1, 3, 201],
      bench_goalkeeper: 2,
      bench_outfield: [4, 5, 6],
      captain: 201,
      vice_captain: 1,
      starting_xi_points: 30.7,
      captain_adjusted_points: 35.9,
    },
    captain_changed: true,
    vice_captain_changed: false,
  };
}

function mockFetchWithApply(applyResult: unknown, applyStatus = 200) {
  return vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/my-team") && !init) {
      return { ok: true, json: async () => buildSquadResponse() } as Response;
    }
    if (url.includes("/preview")) {
      return { ok: true, json: async () => buildPreviewResponseBody() } as Response;
    }
    if (url.includes("/apply")) {
      return {
        ok: applyStatus === 200,
        status: applyStatus,
        json: async () => applyResult,
      } as Response;
    }
    if (url.includes("/my-team/transfers/")) {
      return { ok: true, json: async () => buildExplorerResponse() } as Response;
    }
    throw new Error(`Unexpected fetch call: ${url}`);
  });
}

describe("TransferExplorer", () => {
  it("preselects the outgoing player from ?out= and renders the ranked candidates", async () => {
    useSearchParams.mockReturnValue(makeSearchParams({ out: "9" }));
    useRouter.mockReturnValue({ push: routerPush });
    mockFetchWith(buildExplorerResponse());

    render(<TransferExplorer />);

    await waitFor(() => {
      expect(screen.getByText("Replacing MID Nine")).toBeInTheDocument();
    });

    expect(screen.getByText("Low1High5")).toBeInTheDocument();
    expect(screen.getByText("High1Low5")).toBeInTheDocument();
    expect(screen.getByText(/component_v3 · generated/)).toBeInTheDocument();
  });

  it("re-sorts candidates locally when the horizon changes, without refetching", async () => {
    useSearchParams.mockReturnValue(makeSearchParams({ out: "9" }));
    useRouter.mockReturnValue({ push: routerPush });
    const fetchSpy = vi.fn();
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      fetchSpy(url);
      if (url.endsWith("/my-team")) {
        return { ok: true, json: async () => buildSquadResponse() } as Response;
      }
      return { ok: true, json: async () => buildExplorerResponse() } as Response;
    });

    render(<TransferExplorer />);

    await waitFor(() => {
      expect(screen.getByText("Low1High5")).toBeInTheDocument();
    });

    // Default horizon is 5 GWs: Low1High5 (5.0) ranks above High1Low5 (2.6).
    let rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Low1High5");

    const callsBeforeSwitch = fetchSpy.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "1 GW" }));

    await waitFor(() => {
      rows = screen.getAllByRole("row").slice(1);
      expect(rows[0]).toHaveTextContent("High1Low5");
    });
    // Switching horizon must not trigger a new network request.
    expect(fetchSpy.mock.calls.length).toBe(callsBeforeSwitch);
  });

  it("shows an empty state when there are no legal candidates", async () => {
    useSearchParams.mockReturnValue(makeSearchParams({ out: "9" }));
    useRouter.mockReturnValue({ push: routerPush });
    mockFetchWith({ ...buildExplorerResponse(), candidates: [] });

    render(<TransferExplorer />);

    await waitFor(() => {
      expect(
        screen.getByText("No legal, affordable replacements were found for this player right now."),
      ).toBeInTheDocument();
    });
  });

  it("shows a structured message when the player is not in the squad", async () => {
    useSearchParams.mockReturnValue(makeSearchParams({ out: "999" }));
    useRouter.mockReturnValue({ push: routerPush });
    mockFetchWith(
      {
        detail: {
          code: "player_not_in_squad",
          message: "Player 999 is not in the current squad",
          missing_player_ids: [],
        },
      },
      422,
    );

    render(<TransferExplorer />);

    await waitFor(() => {
      expect(screen.getByText(/is not in the current squad/)).toBeInTheDocument();
    });
    // Falls back to letting the user pick a valid outgoing player.
    expect(screen.getByLabelText("Outgoing player")).toBeInTheDocument();
  });

  it("shows a no-projection-run message distinctly", async () => {
    useSearchParams.mockReturnValue(makeSearchParams({ out: "9" }));
    useRouter.mockReturnValue({ push: routerPush });
    mockFetchWith(
      {
        detail: {
          code: "no_projection_run",
          message: "No projection run found",
          missing_player_ids: [],
        },
      },
      422,
    );

    render(<TransferExplorer />);

    await waitFor(() => {
      expect(
        screen.getByText("Projections need to be refreshed before transfers can be explored."),
      ).toBeInTheDocument();
    });
  });

  it("shows the outgoing player selector when no ?out= is present", async () => {
    useSearchParams.mockReturnValue(makeSearchParams());
    useRouter.mockReturnValue({ push: routerPush });
    mockFetchWith(buildExplorerResponse());

    render(<TransferExplorer />);

    await waitFor(() => {
      expect(screen.getByLabelText("Outgoing player")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Outgoing player"), { target: { value: "9" } });

    expect(routerPush).toHaveBeenCalledWith("/transfers?out=9");
  });

  it("opens a preview without persisting the squad, and renders the resulting XI/gain", async () => {
    useSearchParams.mockReturnValue(makeSearchParams({ out: "9" }));
    useRouter.mockReturnValue({ push: routerPush });

    const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/my-team")) {
        return { ok: true, json: async () => buildSquadResponse() } as Response;
      }
      if (url.includes("/preview")) {
        return {
          ok: true,
          json: async () => ({
            model_version: "component_v3",
            projection_run_id: 42,
            generated_at: "2026-08-16T08:10:00+00:00",
            target_gameweek_number: 5,
            bank: 1.5,
            resulting_bank: 1.0,
            selling_price_is_approximate: true,
            player_out_id: 9,
            player_in_id: 202,
            is_legal: true,
            errors: [],
            projected_team_gain: 2.6,
            direct_player_xpts_difference: 1.2,
            lineup_before: {
              starting_xi: [1, 3, 9],
              bench_goalkeeper: 2,
              bench_outfield: [4, 5, 6],
              captain: 9,
              vice_captain: 1,
              starting_xi_points: 30.0,
              captain_adjusted_points: 33.3,
            },
            lineup_after: {
              starting_xi: [1, 3, 202],
              bench_goalkeeper: 2,
              bench_outfield: [4, 5, 6],
              captain: 202,
              vice_captain: 1,
              starting_xi_points: 30.7,
              captain_adjusted_points: 35.9,
            },
            captain_changed: true,
            vice_captain_changed: false,
          }),
        } as Response;
      }
      if (url.includes("/my-team/transfers/")) {
        return { ok: true, json: async () => buildExplorerResponse() } as Response;
      }
      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(<TransferExplorer />);

    await waitFor(() => {
      expect(screen.getByText("Low1High5")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole("button", { name: "Preview transfer" })[0]);

    await waitFor(() => {
      expect(screen.getByText("Preview: MID Nine → Low1High5")).toBeInTheDocument();
    });

    const previewSection = screen.getByText("Preview: MID Nine → Low1High5").closest("section");
    expect(previewSection).not.toBeNull();
    expect(previewSection).toHaveTextContent("£1.0m");
    expect(screen.getByText(/Projected gain: \+2.6 xPts/)).toBeInTheDocument();
    expect(previewSection).toHaveTextContent("Captain changes.");

    const putCalls = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === "PUT",
    );
    expect(putCalls).toHaveLength(0);
  });

  it("shows an error message when the preview cannot be computed", async () => {
    useSearchParams.mockReturnValue(makeSearchParams({ out: "9" }));
    useRouter.mockReturnValue({ push: routerPush });

    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/my-team")) {
        return { ok: true, json: async () => buildSquadResponse() } as Response;
      }
      if (url.includes("/preview")) {
        return {
          ok: false,
          status: 422,
          json: async () => ({
            detail: {
              code: "missing_projections",
              message: "Player 202 has no projection",
              missing_player_ids: [202],
            },
          }),
        } as Response;
      }
      return { ok: true, json: async () => buildExplorerResponse() } as Response;
    });

    render(<TransferExplorer />);

    await waitFor(() => {
      expect(screen.getByText("Low1High5")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole("button", { name: "Preview transfer" })[0]);

    await waitFor(() => {
      expect(screen.getByText("Player 202 has no projection")).toBeInTheDocument();
    });
  });

  it("explicitly applies the transfer and links back to My Team on success", async () => {
    useSearchParams.mockReturnValue(makeSearchParams({ out: "9" }));
    useRouter.mockReturnValue({ push: routerPush });

    const fetchMock = mockFetchWithApply({
      squad_id: 1,
      name: "My Team",
      bank: 1.0,
      free_transfers: 1,
      projection_totals: null,
      bench_projection_totals: null,
      captain_adjusted_projection_totals: null,
      gameweek_numbers: [],
      players: [],
    });

    render(<TransferExplorer />);

    await waitFor(() => {
      expect(screen.getByText("Low1High5")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole("button", { name: "Preview transfer" })[0]);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Apply transfer" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Apply transfer" }));

    await waitFor(() => {
      expect(screen.getByText("Transfer applied")).toBeInTheDocument();
    });

    expect(screen.getByRole("link", { name: "View My Team" })).toHaveAttribute(
      "href",
      "/my-team",
    );

    const applyCall = fetchMock.mock.calls.find(([url]) => String(url).includes("/apply"));
    expect(applyCall).toBeDefined();
    expect(applyCall?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(applyCall?.[1]?.body))).toEqual({ player_in_id: 201 });
  });

  it("shows an error message when applying fails, without a false success state", async () => {
    useSearchParams.mockReturnValue(makeSearchParams({ out: "9" }));
    useRouter.mockReturnValue({ push: routerPush });

    mockFetchWithApply(
      {
        detail: {
          code: "transfer_illegal",
          message: "This transfer is not legal: insufficient_bank",
          errors: ["insufficient_bank"],
        },
      },
      422,
    );

    render(<TransferExplorer />);

    await waitFor(() => {
      expect(screen.getByText("Low1High5")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole("button", { name: "Preview transfer" })[0]);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Apply transfer" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Apply transfer" }));

    await waitFor(() => {
      expect(
        screen.getByText("This transfer is not legal: insufficient_bank"),
      ).toBeInTheDocument();
    });

    expect(screen.queryByText("Transfer applied")).not.toBeInTheDocument();
  });

  describe("preview eligibility and legality messaging", () => {
    function mockPreview(previewResponse: Response) {
      return vi.spyOn(global, "fetch").mockImplementation(async (input) => {
        const url = String(input);
        if (url.endsWith("/my-team")) {
          return { ok: true, json: async () => buildSquadResponse() } as Response;
        }
        if (url.includes("/preview")) {
          return previewResponse;
        }
        return { ok: true, json: async () => buildExplorerResponse() } as Response;
      });
    }

    async function openFirstPreview(): Promise<void> {
      useSearchParams.mockReturnValue(makeSearchParams({ out: "9" }));
      useRouter.mockReturnValue({ push: routerPush });

      render(<TransferExplorer />);

      await waitFor(() => {
        expect(screen.getByText("Low1High5")).toBeInTheDocument();
      });
      fireEvent.click(screen.getAllByRole("button", { name: "Preview transfer" })[0]);
    }

    it("shows a 422 player_not_in_candidate_pool message in the unavailable state, with no Apply button", async () => {
      mockPreview({
        ok: false,
        status: 422,
        json: async () => ({
          detail: {
            code: "player_not_in_candidate_pool",
            message: "Low1High5 is not currently selectable in FPL.",
            missing_player_ids: [],
          },
        }),
      } as Response);

      await openFirstPreview();

      await waitFor(() => {
        expect(screen.getByText("Low1High5 is not currently selectable in FPL.")).toBeInTheDocument();
      });
      expect(screen.queryByRole("button", { name: "Apply transfer" })).not.toBeInTheDocument();
    });

    it("maps legality error codes to readable text and never shows the raw code", async () => {
      mockPreview({
        ok: true,
        json: async () => ({
          ...buildPreviewResponseBody(),
          is_legal: false,
          errors: ["insufficient_bank", "club_limit_exceeded", "some_future_code"],
          resulting_bank: -0.5,
          lineup_after: null,
        }),
      } as Response);

      await openFirstPreview();

      await waitFor(() => {
        expect(screen.getByText(/This transfer is not currently legal/)).toBeInTheDocument();
      });
      const message = screen.getByText(/This transfer is not currently legal/);
      expect(message).toHaveTextContent(/insufficient budget/i);
      expect(message).toHaveTextContent(/3 players from that club/i);
      expect(message).not.toHaveTextContent("insufficient_bank");
      expect(message).not.toHaveTextContent("club_limit_exceeded");
      expect(message).not.toHaveTextContent("some_future_code");
      expect(screen.getByRole("button", { name: "Apply transfer" })).toBeDisabled();
    });

    it("never issues a PUT /my-team or an apply request when a preview is opened", async () => {
      const fetchMock = mockPreview({
        ok: true,
        json: async () => buildPreviewResponseBody(),
      } as Response);

      await openFirstPreview();

      await waitFor(() => {
        expect(screen.getByText("Preview: MID Nine → Low1High5")).toBeInTheDocument();
      });
      await waitFor(() => {
        expect(screen.getByRole("button", { name: "Apply transfer" })).toBeEnabled();
      });

      const mutating = fetchMock.mock.calls.filter(([url, init]) => {
        const method = (init as RequestInit | undefined)?.method;
        return method === "PUT" || method === "POST" || String(url).includes("/apply");
      });
      expect(mutating).toHaveLength(0);
    });
  });
});
