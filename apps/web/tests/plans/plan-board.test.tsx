import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PlanBoard } from "@/components/plans/plan-board";
import type { PlanChip, PlanIntent, PlanPlayer, PlanResponse } from "@/lib/api";
import {
  buildPlannerPlan,
  createPlannerFixture,
  deferred,
  plannerIdentity,
} from "../fixtures/planner";

type PlanGameweekOverrides = {
  gameweek_number: number;
  chip?: PlanChip | null;
  free_transfers_available?: number;
  unlimited_transfers?: boolean;
  transfers_made?: number;
  points_hit?: number;
  total_points?: number;
};

function buildPlayers(): PlanPlayer[] {
  return (
    [
      {
        player_id: 1,
        web_name: "GK One",
        position: "GK",
        is_starting: true,
        bench_order: null,
      },
      {
        player_id: 2,
        web_name: "GK Two",
        position: "GK",
        is_starting: false,
        bench_order: 1,
      },
      {
        player_id: 3,
        web_name: "DEF One",
        position: "DEF",
        is_starting: true,
        bench_order: null,
      },
      {
        player_id: 4,
        web_name: "DEF Two",
        position: "DEF",
        is_starting: true,
        bench_order: null,
      },
      {
        player_id: 5,
        web_name: "DEF Three",
        position: "DEF",
        is_starting: true,
        bench_order: null,
      },
      {
        player_id: 6,
        web_name: "DEF Four",
        position: "DEF",
        is_starting: true,
        bench_order: null,
      },
      {
        player_id: 7,
        web_name: "DEF Five",
        position: "DEF",
        is_starting: false,
        bench_order: 2,
      },
      {
        player_id: 8,
        web_name: "MID One",
        position: "MID",
        is_starting: true,
        bench_order: null,
      },
      {
        player_id: 9,
        web_name: "MID Two",
        position: "MID",
        is_starting: true,
        bench_order: null,
      },
      {
        player_id: 10,
        web_name: "MID Three",
        position: "MID",
        is_starting: true,
        bench_order: null,
      },
      {
        player_id: 11,
        web_name: "MID Four",
        position: "MID",
        is_starting: true,
        bench_order: null,
      },
      {
        player_id: 12,
        web_name: "MID Five",
        position: "MID",
        is_starting: false,
        bench_order: 3,
      },
      {
        player_id: 13,
        web_name: "FWD One",
        position: "FWD",
        is_starting: true,
        bench_order: null,
      },
      {
        player_id: 14,
        web_name: "FWD Two",
        position: "FWD",
        is_starting: true,
        bench_order: null,
      },
      {
        player_id: 15,
        web_name: "FWD Three",
        position: "FWD",
        is_starting: false,
        bench_order: 4,
      },
    ] as const
  ).map((player) => ({
    ...player,
    team_short_name: "ARS",
    current_price: 5.0,
    status: "a",
    is_captain: player.player_id === 13,
    is_vice_captain: player.player_id === 9,
    projected_points: player.is_starting ? 4 : 2,
    slot_id: plannerIdentity(player.player_id),
    ownership_id: plannerIdentity(1000 + player.player_id),
    source_decision_id: null,
    purchase_price_tenths: 50,
    provenance: {
      source: "stored_market",
      original_price_tenths: 50,
      basis_kind: "starting",
      confirmation: "assumed",
    },
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

function buildPlan(
  gameweeks: PlanGameweekOverrides[] = [{ gameweek_number: 1 }],
): PlanResponse {
  const canonical = buildPlannerPlan(
    gameweeks[0].gameweek_number,
    gameweeks[gameweeks.length - 1].gameweek_number,
  );
  return {
    ...canonical,
    name: "No Haaland GW1",
    start_gameweek: gameweeks[0].gameweek_number,
    end_gameweek: gameweeks[gameweeks.length - 1].gameweek_number,
    initial_bank: 0.5,
    initial_free_transfers: 1,
    total_points: 50,
    total_points_hit: 0,
    gameweeks: gameweeks.map((gameweek, index) => ({
      ...canonical.gameweeks[index],
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
      legal_rearrangements: [
        { first_player_id: 1, second_player_id: 2, kind: "substitution" },
      ],
      ...gameweek,
    })),
  };
}

function mockFetch(plan: PlanResponse, saved?: PlanResponse) {
  const saveCalls: { url: string; body: unknown }[] = [];

  vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);

    if (init?.method === "POST") {
      saveCalls.push({ url, body: JSON.parse(String(init.body)) });
      const envelope = JSON.parse(String(init.body));
      return new Response(
        JSON.stringify({
          status: "committed",
          mutation_id: envelope.mutation_id,
          committed_revision: envelope.expected_revision + 1,
          plan: {
            ...(saved ?? plan),
            revision: envelope.expected_revision + 1,
          },
          candidate: null,
        }),
        { status: 200 },
      );
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
  it.each([1, 12, 20, 25])(
    "shows the applicable starting-state controls at GW%s",
    async (start) => {
      const plan = buildPlannerPlan(start, start + 1);
      mockFetch(plan);
      render(<PlanBoard planId={plan.plan_id} />);
      await screen.findByRole("heading", {
        name: `Starting state at GW${start}`,
      });
      expect(
        screen.getAllByRole("spinbutton", { name: /purchase price$/ }),
      ).toHaveLength(15);
      expect(screen.getAllByText("Estimated", { exact: true })).toHaveLength(
        15,
      );
      expect(
        screen.getByText("Estimated bases", { exact: true }),
      ).toBeInTheDocument();
      if (start === 1) {
        expect(
          screen.queryByLabelText("Starting free transfers"),
        ).not.toBeInTheDocument();
        expect(
          screen.getByText("Free transfers: N/A (unlimited)"),
        ).toBeInTheDocument();
      } else {
        expect(screen.getByLabelText("Starting free transfers")).toHaveValue(1);
      }
      expect(screen.queryByLabelText("Free Hit used in GW19") !== null).toBe(
        start === 20,
      );
      expect(
        screen.queryByLabelText("Wildcard used before this plan") !== null,
      ).toBe(![1, 20].includes(start));
      if (![1, 20].includes(start)) {
        expect(
          screen.getByRole("group", {
            name: `Chips used before GW${start} (${start < 20 ? "GW1-19" : "GW20-38"})`,
          }),
        ).toBeInTheDocument();
      }
      expect(
        screen.queryByRole("spinbutton", { name: /starting bank/i }),
      ).not.toBeInTheDocument();
    },
  );

  it("automatically saves FT0, confirmation and a single basis correction without an all-player gate", async () => {
    const plan = buildPlannerPlan();
    const server = createPlannerFixture(
      plan,
      (current, intents: PlanIntent[]) => {
        if (!current.starting_state) throw new Error("Missing starting state");
        for (const intent of intents) {
          if (intent.kind === "set_starting_transfers")
            current.starting_state.free_transfers = intent.value;
          if (
            intent.kind === "confirm_purchase_price" ||
            intent.kind === "correct_purchase_price"
          ) {
            const player = current.starting_state.players.find(
              (item) => item.ownership_id === intent.ownership_id,
            )!;
            player.provenance.confirmation = "user_confirmed";
            if (intent.kind === "correct_purchase_price")
              player.purchase_price_tenths = intent.price_tenths;
          }
        }
        return current;
      },
    );
    vi.spyOn(global, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST") {
        const envelope = JSON.parse(String(init.body));
        return Response.json({
          ...server.mutate(envelope),
          mutation_id: envelope.mutation_id,
          candidate: null,
        });
      }
      return Response.json(server.read());
    });
    render(<PlanBoard planId={plan.plan_id} />);
    const transfers = await screen.findByLabelText("Starting free transfers");
    fireEvent.change(transfers, { target: { value: "0" } });
    fireEvent.blur(transfers);
    await waitFor(() => expect(transfers).toHaveValue(0));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Saved"),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm P1 purchase price" }),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Confirm P1 purchase price" }),
      ).not.toBeInTheDocument(),
    );
    const price = screen.getByLabelText("P2 purchase price");
    fireEvent.change(price, { target: { value: "4.8" } });
    fireEvent.blur(price);
    await waitFor(() => expect(server.read().revision).toBe(3));
    expect(server.requests.map((request) => request.expected_revision)).toEqual(
      [0, 1, 2],
    );
    expect(server.requests.map((request) => request.intents)).toEqual([
      [{ kind: "set_starting_transfers", value: 0 }],
      [{ kind: "confirm_purchase_price", ownership_id: plannerIdentity(1001) }],
      [
        {
          kind: "correct_purchase_price",
          ownership_id: plannerIdentity(1002),
          price_tenths: 48,
        },
      ],
    ]);
    expect(server.read().starting_state?.bank_tenths).toBe(10);
    expect(
      server.read().starting_state?.players[1].provenance.original_price_tenths,
    ).toBe(50);
    expect(screen.getAllByText("Estimated", { exact: true })).toHaveLength(13);
    expect(
      screen.getByRole("button", { name: "Make P4 captain" }),
    ).toBeEnabled();
  });

  it("retains a contradictory chip declaration and names the planned conflict", async () => {
    const plan = buildPlannerPlan(12, 19);
    plan.gameweeks[6].chip = "WILDCARD";
    vi.spyOn(global, "fetch").mockImplementation(async (_input, init) =>
      init?.method === "POST"
        ? Response.json(
            {
              detail: {
                code: "chip_used_before",
                message: "Gameweek 18: Wildcard is already planned",
              },
            },
            { status: 422 },
          )
        : Response.json(plan),
    );
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(
      await screen.findByLabelText("Wildcard used before this plan"),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Gameweek 18");
    expect(
      screen.getByLabelText("Wildcard used before this plan"),
    ).not.toBeChecked();
    expect(screen.getByLabelText("Gameweek 18")).toHaveTextContent("WILDCARD");
    expect(plan.revision).toBe(0);
  });

  it("renders the plan name and a rail of gameweeks", async () => {
    mockFetch(
      buildPlan([
        { gameweek_number: 1 },
        { gameweek_number: 2 },
        { gameweek_number: 3 },
      ]),
    );

    render(<PlanBoard planId={1} />);

    expect(await screen.findByText("No Haaland GW1")).toBeInTheDocument();
    expect(screen.getByLabelText("Gameweek 1")).toBeInTheDocument();
    expect(screen.getByLabelText("Gameweek 3")).toBeInTheDocument();
  });
  it("preserves queued captain and vice intents while navigating during a delayed save", async () => {
    let plan = buildPlan([{ gameweek_number: 1 }, { gameweek_number: 2 }]);
    const release = deferred<void>();
    const posts: {
      expected_revision: number;
      intents: { kind: string; player_id: number }[];
    }[] = [];
    vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      if (init?.method === "POST") {
        const envelope = JSON.parse(String(init.body));
        posts.push(envelope);
        if (posts.length === 1) await release.promise;
        const intent = envelope.intents[0];
        plan = {
          ...plan,
          revision: plan.revision + 1,
          gameweeks: plan.gameweeks.map((week) =>
            week.gameweek_number !== 1
              ? week
              : {
                  ...week,
                  players: week.players.map((player) => ({
                    ...player,
                    is_captain:
                      intent.kind === "change_captain"
                        ? player.player_id === intent.player_id
                        : player.is_captain,
                    is_vice_captain:
                      intent.kind === "change_vice_captain"
                        ? player.player_id === intent.player_id
                        : player.is_vice_captain,
                  })),
                },
          ),
        };
        return Response.json({
          status: "committed",
          mutation_id: envelope.mutation_id,
          committed_revision: plan.revision,
          plan,
          candidate: null,
        });
      }
      return Response.json(plan);
    });
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(await screen.findByLabelText("Make DEF Two captain"));
    fireEvent.click(screen.getByLabelText("Make DEF Three vice-captain"));
    fireEvent.click(screen.getByLabelText("Gameweek 2"));
    expect(posts).toHaveLength(1);
    release.resolve();
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Saved"),
    );
    expect(posts[1]).toMatchObject({
      expected_revision: 1,
      intents: [
        { kind: "change_vice_captain", gameweek_number: 1, player_id: 5 },
      ],
    });
    fireEvent.click(screen.getByLabelText("Gameweek 1"));
    const captain = screen.getByText("DEF Two").closest("article")!;
    const vice = screen.getByText("DEF Three").closest("article")!;
    expect(
      within(captain).getByText("C", { selector: "span" }),
    ).toBeInTheDocument();
    expect(
      within(vice).getByText("VC", { selector: "span" }),
    ).toBeInTheDocument();
  });

  it("switches the squad view when another gameweek is selected", async () => {
    mockFetch(
      buildPlan([
        { gameweek_number: 1 },
        { gameweek_number: 2, free_transfers_available: 2 },
      ]),
    );

    render(<PlanBoard planId={1} />);
    fireEvent.click(await screen.findByLabelText("Gameweek 2"));

    expect(await screen.findByText(/Gameweek 2/)).toBeInTheDocument();
    expect(screen.getByText(/Free transfers 2/)).toBeInTheDocument();
  });

  it("shows gameweek one as having unlimited transfers", async () => {
    mockFetch(buildPlan([{ gameweek_number: 1, unlimited_transfers: true }]));

    render(<PlanBoard planId={1} />);

    expect(
      await screen.findByText(/Free transfers unlimited/),
    ).toBeInTheDocument();
  });

  it("disables a chip already used in the same half of the season", async () => {
    const plan = buildPlan([
      { gameweek_number: 1, chip: "BENCH_BOOST" },
      { gameweek_number: 2 },
    ]);
    plan.gameweeks[1].chip_availability.BENCH_BOOST = {
      state: "planned_elsewhere",
      reason: "Planned in gameweek 1",
      conflicting_gameweek: 1,
    };
    mockFetch(plan);

    render(<PlanBoard planId={1} />);
    fireEvent.click(await screen.findByLabelText("Gameweek 2"));

    expect(screen.getByLabelText("Bench Boost")).toBeDisabled();
    expect(screen.getByLabelText("Wildcard")).toBeEnabled();
  });

  it("automatically sends the selected chip without a whole-gameweek save", async () => {
    const saveCalls = mockFetch(buildPlan([{ gameweek_number: 1 }]));

    render(<PlanBoard planId={1} />);
    fireEvent.click(await screen.findByLabelText("Triple Captain"));

    await waitFor(() => expect(saveCalls).toHaveLength(1));
    expect(saveCalls[0].url).toContain("/mutations");
    expect((saveCalls[0].body as { intents: unknown[] }).intents).toEqual([
      { kind: "activate_chip", gameweek_number: 1, chip: "TRIPLE_CAPTAIN" },
    ]);
    expect(
      screen.queryByRole("button", { name: "Save Gameweek" }),
    ).not.toBeInTheDocument();
  });

  it("offers only authoritative server-provided swap targets", async () => {
    mockFetch(buildPlan([{ gameweek_number: 1 }]));

    render(<PlanBoard planId={1} />);
    fireEvent.click(await screen.findByLabelText("Swap GK One with bench"));
    expect(
      screen.queryByLabelText("Swap GK One for DEF Five"),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("Swap GK One for GK Two")).toBeInTheDocument();
  });

  it("automatically sends a bound transfer decision, never a membership snapshot", async () => {
    const saveCalls = mockFetch(buildPlan([{ gameweek_number: 1 }]));

    render(<PlanBoard planId={1} />);
    fireEvent.click(await screen.findByLabelText("Transfer MID One"));
    fireEvent.click(await screen.findByLabelText("Transfer in New Mid"));

    await waitFor(() => expect(saveCalls).toHaveLength(1));
    const body = saveCalls[0].body as { intents: unknown[]; players?: unknown };
    expect(body.intents).toEqual([
      {
        kind: "add_transfer",
        gameweek_number: 1,
        outgoing_player_id: 8,
        outgoing_ownership_id: plannerIdentity(1008),
        incoming_player_id: 99,
      },
    ]);
    expect(body.players).toBeUndefined();
  });

  it("surfaces a rule violation from the API", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      if (init?.method === "POST") {
        return new Response(
          JSON.stringify({
            detail: { code: "budget", message: "Gameweek 1 goes over budget" },
          }),
          { status: 422 },
        );
      }
      return new Response(JSON.stringify(buildPlan([{ gameweek_number: 1 }])), {
        status: 200,
      });
    });

    render(<PlanBoard planId={1} />);
    fireEvent.click(await screen.findByLabelText("Triple Captain"));

    expect(
      await screen.findByText("Gameweek 1 goes over budget"),
    ).toBeInTheDocument();
  });
});
