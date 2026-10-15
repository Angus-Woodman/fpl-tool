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
  it.each(["remove", "replace"])(
    "US3 preserves rejected acquisition and submits chosen %s repair atomically",
    async (choice) => {
      const plan = buildPlannerPlan(8, 9);
      const acquisition = {
        decision_id: plannerIdentity(8000),
        outgoing_player_id: 6,
        outgoing_ownership_id: plannerIdentity(1006),
        incoming_player_id: 106,
        incoming_ownership_id: plannerIdentity(8001),
        outgoing_market_tenths: 50,
        incoming_price_tenths: 50,
        selling_price_tenths: 50,
        observation_source: "stored_player_observation",
        observed_at: "2026-10-14T12:00:00+00:00",
        origin: "captured",
      };
      const downstream = {
        ...acquisition,
        decision_id: plannerIdentity(8002),
        outgoing_player_id: 106,
        outgoing_ownership_id: acquisition.incoming_ownership_id,
        incoming_player_id: 6,
        incoming_ownership_id: plannerIdentity(8003),
      };
      plan.gameweeks[0].decisions = [acquisition];
      plan.gameweeks[1].decisions = [downstream];
      Object.assign(plan.gameweeks[0].players[5], {
        player_id: 106,
        web_name: "P106",
        ownership_id: acquisition.incoming_ownership_id,
        source_decision_id: acquisition.decision_id,
      });
      const requests: { intents: PlanIntent[]; expected_revision: number }[] =
        [];
      vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
        if (init?.method === "POST") {
          const envelope = JSON.parse(String(init.body));
          requests.push(envelope);
          if (requests.length === 1)
            return new Response(
              JSON.stringify({
                detail: {
                  code: "outgoing_not_owned",
                  message: "Outgoing player unavailable",
                  diagnostics: [
                    {
                      code: "outgoing_not_owned",
                      message: "Intended outgoing player 106 is not owned",
                      gameweek_number: 9,
                      decision_id: downstream.decision_id,
                      conflicting_gameweek: null,
                      player_id: 106,
                    },
                  ],
                },
              }),
              { status: 422 },
            );
          return new Response(
            JSON.stringify({
              status: "committed",
              mutation_id: envelope.mutation_id,
              committed_revision: 1,
              plan: { ...plan, revision: 1 },
              candidate: null,
            }),
            { status: 200 },
          );
        }
        if (String(input).includes("/players?"))
          return new Response(
            JSON.stringify({
              items: [
                {
                  id: 99,
                  web_name: "New Mid",
                  first_name: "New",
                  second_name: "Mid",
                  team_name: "Team",
                  team_short_name: "TMX",
                  position: "MID",
                  current_price: 5,
                  status: "a",
                },
              ],
              total: 1,
              page: 1,
              page_size: 50,
            }),
            { status: 200 },
          );
        return new Response(JSON.stringify(plan), { status: 200 });
      });
      render(<PlanBoard planId={plan.plan_id} />);
      fireEvent.click(await screen.findByLabelText("Transfer P106"));
      fireEvent.click(await screen.findByLabelText("Transfer in New Mid"));
      const repair = await screen.findByLabelText(
        "Repair transfer GW9: 106 to 6",
      );
      expect(screen.getByLabelText("Transfer P106")).toBeVisible();
      expect(requests).toHaveLength(1);
      expect(requests[0].intents).toEqual([
        {
          kind: "edit_transfer",
          decision_id: acquisition.decision_id,
          incoming_player_id: 99,
        },
      ]);
      expect(
        screen.getByRole("button", { name: "Apply transfer repair" }),
      ).toBeDisabled();
      fireEvent.change(repair, {
        target: {
          value: choice === "remove" ? "remove" : plannerIdentity(1007),
        },
      });
      fireEvent.click(
        screen.getByRole("button", { name: "Apply transfer repair" }),
      );
      await waitFor(() =>
        expect(screen.getByRole("status")).toHaveTextContent("Saved"),
      );
      expect(requests[1].expected_revision).toBe(0);
      expect(requests[1].intents).toEqual([
        ...requests[0].intents,
        choice === "remove"
          ? { kind: "remove_transfer", decision_id: downstream.decision_id }
          : {
              kind: "edit_transfer",
              decision_id: downstream.decision_id,
              outgoing_player_id: 7,
              outgoing_ownership_id: plannerIdentity(1007),
            },
      ]);
    },
  );

  it("US3 displays replay next FT and plan hit total", async () => {
    const plan = buildPlannerPlan(8, 11);
    plan.total_points_hit = 4;
    plan.gameweeks[0].accounting!.next_free_transfers = 2;
    mockFetch(plan);
    render(<PlanBoard planId={plan.plan_id} />);
    expect(await screen.findByText(/Next FT 2/)).toBeVisible();
    expect(screen.getByText(/Hits taken: 4/)).toBeVisible();
  });

  it("US3 blocked accounting shows unavailable values rather than invented totals", async () => {
    const plan = buildPlannerPlan(8, 11);
    const week = plan.gameweeks[0];
    plan.total_points_hit = null;
    week.players = [];
    week.bank = null;
    week.transfers_made = null;
    week.points_hit = null;
    week.free_transfers_available = null;
    week.accounting = {
      starting_bank_tenths: null,
      closing_bank_tenths: null,
      free_transfers_available: null,
      next_free_transfers: null,
      unlimited_transfers: false,
      transfers_made: null,
      points_hit: null,
    };
    week.evaluation_status = "blocked";
    plan.decision_errors = [
      {
        code: "outgoing_not_owned",
        message: "Intended outgoing player 102 is not owned in that episode",
        gameweek_number: 8,
        decision_id: "missing-decision",
        conflicting_gameweek: null,
        player_id: 102,
      },
    ];
    mockFetch(plan);
    render(<PlanBoard planId={plan.plan_id} />);
    expect(await screen.findByText(/Hits taken: Unavailable/)).toBeVisible();
    expect(screen.getByText(/Next FT Unavailable/)).toBeVisible();
    expect(screen.getByText(/Hit Unavailable/)).toBeVisible();
    expect(screen.getByText(/Intended outgoing player 102/)).toBeVisible();
  });

  it.each([
    ["available", null, null, false, false],
    ["planned_here", null, null, false, true],
    ["planned_elsewhere", "Planned for gameweek 18", 18, true, false],
    ["used_before", "Used before this plan", null, true, false],
    [
      "rule_unavailable",
      "Free Hit conflicts with gameweek 19",
      19,
      true,
      false,
    ],
  ] as const)(
    "US2 renders the server's %s chip state",
    async (state, reason, conflict, disabled, pressed) => {
      const plan = buildPlannerPlan(17, 22);
      plan.gameweeks[0].chip = pressed ? "FREE_HIT" : null;
      plan.gameweeks[0].chip_availability.FREE_HIT = {
        state,
        reason,
        conflicting_gameweek: conflict,
      };
      mockFetch(plan);
      render(<PlanBoard planId={plan.plan_id} />);
      const button = await screen.findByRole("button", {
        name: "Free Hit",
      });
      expect(button).toHaveAttribute("aria-pressed", String(pressed));
      if (disabled) expect(button).toBeDisabled();
      else expect(button).toBeEnabled();
      if (reason) {
        expect(screen.getByText(reason, { exact: true })).toBeVisible();
        expect(button).toHaveAttribute("title", reason);
      }
      expect(
        screen.queryByRole("button", {
          name: "Move Free Hit from GW18 to GW17",
        }) !== null,
      ).toBe(state === "planned_elsewhere");
    },
  );

  it("US2 updates named chip reasons only after acknowledged move and clear", async () => {
    const plan = buildPlannerPlan(17, 22);
    plan.starting_state!.used_chips = ["FREE_HIT"];
    plan.gameweeks[1].chip = "WILDCARD";
    for (const week of plan.gameweeks.slice(0, 3)) {
      week.chip_availability.FREE_HIT = {
        state: "used_before",
        reason: "Used before this plan",
        conflicting_gameweek: null,
      };
      week.chip_availability.WILDCARD =
        week.gameweek_number === 18
          ? { state: "planned_here", reason: null, conflicting_gameweek: null }
          : {
              state: "planned_elsewhere",
              reason: "Planned for gameweek 18",
              conflicting_gameweek: 18,
            };
    }
    const gate = deferred<void>();
    const server = createPlannerFixture(
      plan,
      (current, intents: PlanIntent[]) => {
        for (const intent of intents) {
          if (intent.kind === "move_chip") {
            current.gameweeks[1].chip = null;
            current.gameweeks[0].chip = "WILDCARD";
            current.gameweeks[0].chip_availability.WILDCARD = {
              state: "planned_here",
              reason: null,
              conflicting_gameweek: null,
            };
            for (const week of current.gameweeks.slice(1, 3))
              week.chip_availability.WILDCARD = {
                state: "planned_elsewhere",
                reason: "Planned for gameweek 17",
                conflicting_gameweek: 17,
              };
          } else if (intent.kind === "remove_chip") {
            current.gameweeks[0].chip = null;
            for (const week of current.gameweeks.slice(0, 3))
              week.chip_availability.WILDCARD = {
                state: "available",
                reason: null,
                conflicting_gameweek: null,
              };
          } else throw new Error("Unexpected chip fixture intent");
        }
        return current;
      },
    );
    vi.spyOn(global, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST") {
        const envelope = JSON.parse(String(init.body));
        await gate.promise;
        return Response.json({
          ...server.mutate(envelope),
          mutation_id: envelope.mutation_id,
          candidate: null,
        });
      }
      return Response.json(server.read());
    });
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Move Wildcard from GW18 to GW17",
      }),
    );
    expect(
      screen.getByText("Planned for gameweek 18", { exact: true }),
    ).toBeVisible();
    gate.resolve();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Wildcard" })).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
    expect(
      screen.queryByText("Planned for gameweek 18", { exact: true }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Wildcard" }));
    await waitFor(() => expect(server.read().revision).toBe(2));
    expect(screen.getByRole("button", { name: "Wildcard" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Free Hit" })).toBeDisabled();
    expect(
      screen.getByText("Used before this plan", { exact: true }),
    ).toBeVisible();
    fireEvent.click(screen.getByLabelText("Gameweek 20", { exact: true }));
    expect(screen.getByRole("button", { name: "Free Hit" })).toBeEnabled();
    expect(server.requests.map((request) => request.intents)).toEqual([
      [
        {
          kind: "move_chip",
          chip: "WILDCARD",
          source_gameweek: 18,
          target_gameweek: 17,
        },
      ],
      [{ kind: "remove_chip", gameweek_number: 17, chip: "WILDCARD" }],
    ]);
  });

  it.each([
    ["BENCH_BOOST", "Bench Boost"],
    ["TRIPLE_CAPTAIN", "Triple Captain"],
  ] as const)(
    "US2 %s activation alone preserves the server bank and allowance",
    async (chip, label) => {
      const plan = buildPlannerPlan(17, 18);
      const accounting = structuredClone(
        plan.gameweeks.map((week) => week.accounting),
      );
      const server = createPlannerFixture(
        plan,
        (current, intents: PlanIntent[]) => {
          expect(intents).toEqual([
            { kind: "activate_chip", gameweek_number: 17, chip },
          ]);
          current.gameweeks[0].chip = chip;
          current.gameweeks[0].chip_availability[chip] = {
            state: "planned_here",
            reason: null,
            conflicting_gameweek: null,
          };
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
      fireEvent.click(await screen.findByRole("button", { name: label }));
      await waitFor(() =>
        expect(screen.getByRole("button", { name: label })).toHaveAttribute(
          "aria-pressed",
          "true",
        ),
      );
      expect(
        screen.getByText(/Bank 1.0 · Free transfers 1 · Transfers made 0/),
      ).toBeVisible();
      expect(server.read().gameweeks.map((week) => week.accounting)).toEqual(
        accounting,
      );
    },
  );

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
