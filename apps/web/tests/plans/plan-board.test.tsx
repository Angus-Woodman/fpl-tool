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
import { getPlanSaveCoordinator } from "@/lib/plan-save-coordinator";
import type {
  PlanChip,
  PlanDecision,
  PlanIntent,
  PlanPlayer,
  PlanResponse,
} from "@/lib/api";
import {
  applyPlannerIntents,
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

function us4Decision(overrides: Partial<PlanDecision> = {}): PlanDecision {
  return {
    decision_id: plannerIdentity(8000),
    outgoing_player_id: 2,
    outgoing_ownership_id: plannerIdentity(1002),
    incoming_player_id: 102,
    incoming_ownership_id: plannerIdentity(8001),
    outgoing_market_tenths: 54,
    incoming_price_tenths: 62,
    selling_price_tenths: 51,
    purchase_price_tenths: 48,
    basis_kind: "starting",
    basis_confirmation: "user_confirmed",
    outgoing_live_market_tenths: 56,
    incoming_live_price_tenths: 60,
    observation_source: "stored_player_observation",
    observed_at: "2026-10-14T12:00:00+00:00",
    origin: "captured",
    ...overrides,
  };
}

function us4Plan(start = 8, end = 9): PlanResponse {
  const plan = buildPlannerPlan(start, end);
  plan.gameweeks[0].decisions = [us4Decision()];
  plan.gameweeks[0].transfers_out = [{ player_id: 2, web_name: "P2" }];
  plan.gameweeks[0].transfers_in = [{ player_id: 102, web_name: "P102" }];
  return plan;
}

function shortfallStatus(plan: PlanResponse): void {
  plan.gameweeks[1].bank = -0.1;
  plan.gameweeks[1].accounting!.closing_bank_tenths = -1;
  plan.financial_status = {
    provisional: true,
    requires_resolution: true,
    earliest_shortfall_gameweek: 9,
    earliest_shortfall_tenths: 1,
    earliest_shortfall_reason:
      "Bank is £0.1m below zero in gameweek 9 after its saved transfers",
    gameweeks: [
      {
        gameweek_number: 8,
        shortfall_tenths: 0,
        affected_chain: [],
        provisional: true,
      },
      {
        gameweek_number: 9,
        shortfall_tenths: 1,
        affected_chain: [9],
        provisional: true,
      },
      {
        gameweek_number: 10,
        shortfall_tenths: 1,
        affected_chain: [9, 10],
        provisional: true,
      },
    ],
  };
}

describe("PlanBoard", () => {
  it("US4 inspection separates basis, saved quotes, sale and live prices and states the policy", async () => {
    const plan = us4Plan();
    mockFetch(plan);
    render(<PlanBoard planId={plan.plan_id} />);
    const details = await screen.findByRole("region", {
      name: "Transfer price details: P2 to P102",
    });
    expect(details).toHaveTextContent("Purchase basis £4.8m · Confirmed");
    expect(details).toHaveTextContent("Saved market assumption £5.4m");
    expect(details).toHaveTextContent("Selling price used £5.1m");
    expect(details).toHaveTextContent("Acquisition price paid £6.2m");
    expect(details).toHaveTextContent(
      "Latest market (not used): P2 £5.6m · P102 £6.0m",
    );
    expect(
      screen.getByText(/Market refreshes do not reprice saved transfers/),
    ).toBeVisible();
  });

  it("US4 presents a planned acquisition's source readably, never as a raw decision identifier", async () => {
    const plan = us4Plan();
    const carried = plan.starting_state!.players[1];
    carried.provenance = {
      source: `decision:${plannerIdentity(8000)}@stored_player_observation@2026-10-15T14:04:28+00:00`,
      original_price_tenths: 50,
      basis_kind: "planned_acquisition",
      confirmation: null,
    };
    mockFetch(plan);
    render(<PlanBoard planId={plan.plan_id} />);
    const row = (await screen.findByLabelText("P2 purchase price")).closest(
      "li",
    )!;
    expect(row).toHaveTextContent("Planned acquisition");
    expect(row).toHaveTextContent(
      "Original 5.0 · acquired by a planned transfer",
    );
    expect(row).not.toHaveTextContent("decision:");
    expect(row).not.toHaveTextContent(plannerIdentity(8000));
  });

  it.each([
    ["both available", 56, 60, "P2 £5.6m · P102 £6.0m"],
    ["outgoing only", 56, null, "P2 £5.6m · P102 Unavailable"],
    ["incoming only", null, 60, "P2 Unavailable · P102 £6.0m"],
    ["both unavailable", null, null, null],
  ])(
    "US4 shows live prices independently when %s without changing saved values",
    async (_name, outgoingLive, incomingLive, expected) => {
      const plan = us4Plan();
      plan.gameweeks[0].decisions = [
        us4Decision({
          outgoing_live_market_tenths: outgoingLive,
          incoming_live_price_tenths: incomingLive,
        }),
      ];
      mockFetch(plan);
      render(<PlanBoard planId={plan.plan_id} />);
      const details = await screen.findByRole("region", {
        name: "Transfer price details: P2 to P102",
      });
      if (expected === null) {
        expect(details).not.toHaveTextContent("Latest market");
      } else {
        expect(details).toHaveTextContent(
          `Latest market (not used): ${expected}`,
        );
      }
      expect(details).toHaveTextContent("Saved market assumption £5.4m");
      expect(details).toHaveTextContent("Selling price used £5.1m");
      expect(details).toHaveTextContent("Acquisition price paid £6.2m");
    },
  );

  it("US4 estimated bases are lightweight, provisional and never block planning", async () => {
    const plan = us4Plan();
    plan.gameweeks[0].decisions = [
      us4Decision({ basis_confirmation: "assumed", purchase_price_tenths: 50 }),
    ];
    plan.financial_status = { provisional: true, requires_resolution: false };
    mockFetch(plan);
    render(<PlanBoard planId={plan.plan_id} />);
    const details = await screen.findByRole("region", {
      name: "Transfer price details: P2 to P102",
    });
    expect(details).toHaveTextContent("Purchase basis £5.0m · Estimated");
    expect(screen.getByText("Estimated bases")).toBeVisible();
    expect(screen.queryByText("Requires resolution")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Make P4 captain")).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Remove transfer 2 to 102" }),
    ).toBeEnabled();
  });

  it("US4 keeps saved, provisional and requires-resolution status separate and navigates to the earliest gameweek", async () => {
    const plan = us4Plan(8, 10);
    shortfallStatus(plan);
    mockFetch(plan);
    render(<PlanBoard planId={plan.plan_id} />);
    expect(await screen.findByRole("status")).toHaveTextContent("Saved");
    expect(screen.getByText("Estimated bases")).toBeVisible();
    expect(screen.getByText("Requires resolution")).toBeVisible();
    const issue = screen.getByRole("region", { name: "Financial resolution" });
    expect(issue).toHaveTextContent("Shortfall £0.1m in GW9");
    expect(issue).toHaveTextContent("Bank is £0.1m below zero in gameweek 9");
    expect(issue).toHaveTextContent("Dependent gameweeks: GW9, GW10");
    expect(issue).toHaveTextContent("Saved does not mean financially valid");
    expect(screen.getByLabelText("Gameweek 8")).toHaveAttribute(
      "aria-current",
      "true",
    );
    fireEvent.click(within(issue).getByRole("button", { name: "Go to GW9" }));
    expect(screen.getByLabelText("Gameweek 9")).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("US4 shows a negative bank as a shortfall rather than clamping or hiding it", async () => {
    const plan = us4Plan();
    shortfallStatus(plan);
    mockFetch(plan);
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(await screen.findByLabelText("Gameweek 9"));
    expect(screen.getByText(/Bank Shortfall £0.1m/)).toBeVisible();
    expect(screen.queryByText(/Bank -0.1/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Bank 0.0/)).not.toBeInTheDocument();
  });

  it("US4 retains decisions during repair and clears the flags only after an acknowledged legal repair", async () => {
    const plan = us4Plan();
    shortfallStatus(plan);
    const repaired = us4Plan();
    repaired.plan_id = plan.plan_id;
    repaired.revision = 1;
    repaired.gameweeks[0].decisions = [];
    repaired.gameweeks[0].transfers_in = [];
    repaired.gameweeks[0].transfers_out = [];
    repaired.financial_status = {
      provisional: true,
      requires_resolution: false,
    };
    const requests: { intents: PlanIntent[]; expected_revision: number }[] = [];
    vi.spyOn(global, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method !== "POST")
        return new Response(JSON.stringify(plan), { status: 200 });
      const envelope = JSON.parse(String(init.body));
      requests.push(envelope);
      return new Response(
        JSON.stringify({
          status: "committed",
          mutation_id: envelope.mutation_id,
          committed_revision: 1,
          plan: repaired,
          candidate: null,
        }),
        { status: 200 },
      );
    });
    render(<PlanBoard planId={plan.plan_id} />);
    expect(await screen.findByText("Requires resolution")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Remove transfer 2 to 102" }),
    ).toBeVisible();
    expect(requests).toHaveLength(0);
    fireEvent.click(
      screen.getByRole("button", { name: "Remove transfer 2 to 102" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Saved"),
    );
    expect(requests[0]).toMatchObject({
      expected_revision: 0,
      intents: [
        { kind: "remove_transfer", decision_id: plannerIdentity(8000) },
      ],
    });
    expect(screen.queryByText("Requires resolution")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Financial resolution" }),
    ).not.toBeInTheDocument();
  });

  it.each(["none", "duplicate", "additional"])(
    "retains accepted repair diagnostics after a 422 with %s diagnostics",
    async (mode) => {
      const plan = buildPlannerPlan(8, 9);
      plan.decision_errors = [
        {
          code: "outgoing_not_owned",
          message: "Accepted legacy ownership needs repair",
          gameweek_number: 8,
          decision_id: null,
          conflicting_gameweek: null,
          player_id: 102,
        },
      ];
      const requests: unknown[] = [];
      vi.spyOn(global, "fetch").mockImplementation(async (_input, init) => {
        if (init?.method === "POST") {
          requests.push(JSON.parse(String(init.body)));
          if (requests.length === 1)
            return new Response(
              JSON.stringify({
                detail: {
                  code: "unrelated_rejection",
                  message: "Unrelated edit rejected",
                  ...(mode === "none"
                    ? {}
                    : {
                        diagnostics:
                          mode === "duplicate"
                            ? [...plan.decision_errors]
                            : [
                                {
                                  ...plan.decision_errors[0],
                                  message: "Proposed ownership unavailable",
                                },
                              ],
                      }),
                },
              }),
              { status: 422 },
            );
          return new Response(
            JSON.stringify({
              status: "committed",
              mutation_id: JSON.parse(String(init.body)).mutation_id,
              committed_revision: 1,
              plan: { ...plan, revision: 1 },
              candidate: null,
            }),
            { status: 200 },
          );
        }
        return new Response(JSON.stringify(plan), { status: 200 });
      });
      render(<PlanBoard planId={plan.plan_id} />);
      expect(
        await screen.findByText(/Accepted legacy ownership needs repair/),
      ).toBeVisible();
      fireEvent.click(screen.getByLabelText("Make P4 captain"));
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Unrelated edit rejected",
      );
      expect(
        screen.getAllByText(/Accepted legacy ownership needs repair/),
      ).toHaveLength(1);
      if (mode === "additional")
        expect(
          screen.getByText(/Proposed ownership unavailable/),
        ).toHaveTextContent("Rejected edit");
      expect(
        screen.getByText(/Accepted legacy ownership needs repair/),
      ).toHaveTextContent("Saved plan");
      expect(screen.getByLabelText("Make P4 captain")).toBeVisible();
      expect(requests).toHaveLength(1);
      expect(plan.revision).toBe(0);
      expect(
        plan.gameweeks[0].players.find((player) => player.is_captain)
          ?.player_id,
      ).toBe(10);
      fireEvent.click(screen.getByLabelText("Make P5 captain"));
      await waitFor(() =>
        expect(screen.getByRole("status")).toHaveTextContent("Saved"),
      );
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(
        screen.queryByText(/Proposed ownership unavailable/),
      ).not.toBeInTheDocument();
      expect(
        screen.getByText(/Accepted legacy ownership needs repair/),
      ).toBeVisible();
    },
  );

  it.each(["saved", "rejected"])(
    "US3 %s-origin repair replays rejected intents only for the rejected proposal",
    async (origin) => {
      const plan = buildPlannerPlan(8, 9);
      const decision = (id: number, outgoing: number, incoming: number) => ({
        decision_id: plannerIdentity(id),
        outgoing_player_id: outgoing,
        outgoing_ownership_id: plannerIdentity(1000 + outgoing),
        incoming_player_id: incoming,
        incoming_ownership_id: plannerIdentity(id + 1),
        outgoing_market_tenths: 50,
        incoming_price_tenths: 50,
        selling_price_tenths: 50,
        observation_source: "stored_player_observation",
        observed_at: "2026-10-14T12:00:00+00:00",
        origin: "captured",
      });
      const saved = decision(8000, 6, 106);
      const rejectedTarget = decision(8100, 7, 107);
      plan.gameweeks[0].decisions = [saved];
      plan.gameweeks[1].decisions = [rejectedTarget];
      const diagnostic = (target: typeof saved, message: string) => ({
        code: "outgoing_not_owned",
        message,
        gameweek_number: target === saved ? 8 : 9,
        decision_id: target.decision_id,
        conflicting_gameweek: null,
        player_id: target.outgoing_player_id,
      });
      plan.decision_errors = [
        diagnostic(saved, "Saved ownership needs repair"),
      ];
      const captain = {
        kind: "change_captain",
        gameweek_number: 8,
        player_id: 4,
      };
      const requests: { intents: PlanIntent[]; expected_revision: number }[] =
        [];
      vi.spyOn(global, "fetch").mockImplementation(async (_input, init) => {
        if (init?.method !== "POST")
          return new Response(JSON.stringify(plan), { status: 200 });
        const envelope = JSON.parse(String(init.body));
        requests.push(envelope);
        if (requests.length === 1)
          return new Response(
            JSON.stringify({
              detail: {
                code: "outgoing_not_owned",
                message: "Captain edit rejected",
                diagnostics: [
                  diagnostic(rejectedTarget, "Rejected edit breaks ownership"),
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
            plan: {
              ...plan,
              revision: 1,
              decision_errors: [],
              gameweeks: plan.gameweeks.map((week) => ({
                ...week,
                decisions: [],
              })),
            },
            candidate: null,
          }),
          { status: 200 },
        );
      });
      render(<PlanBoard planId={plan.plan_id} />);
      expect(
        await screen.findByText(/Saved ownership needs repair/),
      ).toBeVisible();
      fireEvent.click(screen.getByLabelText("Make P4 captain"));
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Captain edit rejected",
      );
      expect(
        screen.getByText(/Saved ownership needs repair/),
      ).toHaveTextContent("Saved plan");
      expect(
        screen.getByText(/Rejected edit breaks ownership/),
      ).toHaveTextContent("Rejected edit");
      const target = origin === "saved" ? saved : rejectedTarget;
      const group = screen.getByRole("group", {
        name:
          origin === "saved" ? "Saved plan repairs" : "Rejected edit repairs",
      });
      fireEvent.change(
        within(group).getByLabelText(
          `Repair transfer GW${target === saved ? 8 : 9}: ${target.outgoing_player_id} to ${target.incoming_player_id}`,
        ),
        { target: { value: "remove" } },
      );
      fireEvent.click(
        within(group).getByRole("button", { name: "Apply transfer repair" }),
      );
      await waitFor(() =>
        expect(screen.getByRole("status")).toHaveTextContent("Saved"),
      );
      expect(requests).toHaveLength(2);
      expect(requests[1].expected_revision).toBe(0);
      expect(requests[1].intents).toEqual(
        origin === "saved"
          ? [{ kind: "remove_transfer", decision_id: saved.decision_id }]
          : [
              captain,
              { kind: "remove_transfer", decision_id: target.decision_id },
            ],
      );
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(
        screen.queryByText(/Rejected edit breaks ownership/),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByText(/Saved ownership needs repair/),
      ).not.toBeInTheDocument();
    },
  );

  it.each(["remove", "replace", "proposed"])(
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
          value:
            choice === "remove"
              ? "remove"
              : choice === "proposed"
                ? `source:${acquisition.decision_id}`
                : plannerIdentity(1007),
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
          : choice === "proposed"
            ? {
                kind: "edit_transfer",
                decision_id: downstream.decision_id,
                outgoing_player_id: 99,
                outgoing_source_decision_id: acquisition.decision_id,
              }
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

  it("FR-016 shows all four chips in one gameweek with visibly different states and reasons", async () => {
    const plan = buildPlannerPlan(17, 22);
    const week = plan.gameweeks[1];
    week.chip = "WILDCARD";
    week.chip_availability = {
      WILDCARD: {
        state: "planned_here",
        reason: null,
        conflicting_gameweek: null,
      },
      FREE_HIT: {
        state: "planned_elsewhere",
        reason: "Planned for gameweek 17",
        conflicting_gameweek: 17,
      },
      BENCH_BOOST: {
        state: "used_before",
        reason: "Used before this plan",
        conflicting_gameweek: null,
      },
      TRIPLE_CAPTAIN: {
        state: "rule_unavailable",
        reason: "Triple Captain is unavailable here",
        conflicting_gameweek: null,
      },
    };
    mockFetch(plan);
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(await screen.findByLabelText("Gameweek 18"));

    const chip = (name: string) => screen.getByRole("button", { name });
    expect(chip("Wildcard")).toHaveAttribute("aria-pressed", "true");
    expect(chip("Free Hit")).toBeDisabled();
    expect(chip("Bench Boost")).toBeDisabled();
    expect(chip("Triple Captain")).toBeDisabled();
    const reasons = [
      "Planned for gameweek 17",
      "Used before this plan",
      "Triple Captain is unavailable here",
    ];
    for (const reason of reasons)
      expect(screen.getByText(reason, { exact: true })).toBeVisible();
    expect(new Set(reasons).size).toBe(3);
    // One chip per gameweek: with Wildcard here, no other chip may be moved in.
    expect(
      screen.queryByRole("button", { name: /^Move / }),
    ).not.toBeInTheDocument();
  });

  it("FR-041 keeps an accepted provenance correction visible, not saved and retryable with the same ID", async () => {
    const plan = buildPlannerPlan();
    const applyCorrection = (current: PlanResponse, intents: PlanIntent[]) => {
      for (const intent of intents) {
        if (intent.kind !== "correct_purchase_price") continue;
        const player = current.starting_state!.players.find(
          (item) => item.ownership_id === intent.ownership_id,
        )!;
        player.provenance.confirmation = "user_confirmed";
        player.purchase_price_tenths = intent.price_tenths;
      }
      return current;
    };
    const candidate = applyCorrection(structuredClone(plan), [
      {
        kind: "correct_purchase_price",
        ownership_id: plannerIdentity(1002),
        price_tenths: 48,
      },
    ]);
    const { posts, server } = plannerServer(plan, {
      apply: applyCorrection,
      post: async (_envelope, call) =>
        call === 1
          ? json(
              {
                detail: {
                  code: "accepted_not_saved",
                  message:
                    "Accepted edit is not saved; retry the same mutation ID",
                  plan,
                  candidate,
                },
              },
              503,
            )
          : undefined,
    });
    render(<PlanBoard planId={plan.plan_id} />);
    const price = await screen.findByLabelText("P2 purchase price");
    fireEvent.change(price, { target: { value: "4.8" } });
    fireEvent.blur(price);

    await waitFor(() => expect(statusText()).toBe("Not saved"));
    expect(screen.getByLabelText("P2 purchase price")).toHaveValue(4.8);
    expect(server.read().revision).toBe(0);
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Retry Same Edit" }));
    await waitFor(() => expect(statusText()).toBe("Saved"));
    expect(posts).toHaveLength(2);
    expect(posts[1]).toEqual(posts[0]);
    expect(server.read().revision).toBe(1);
    expect(screen.getByLabelText("P2 purchase price")).toHaveValue(4.8);
    const calm = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(calm);
    expect(calm.defaultPrevented).toBe(false);
  });

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

  describe("direct rearrangement", () => {
    function selectButton(name: string): HTMLElement {
      return screen.getByRole("button", { name: `Select ${name}` });
    }

    function selectionState(name: string): string | null | undefined {
      return selectButton(name)
        .closest("article")
        ?.getAttribute("data-selection-state");
    }

    function benchNames(): string[] {
      const bench = screen.getByRole("heading", { name: "Bench" })
        .parentElement as HTMLElement;
      return within(bench)
        .getAllByRole("button", { name: /^Select / })
        .map(
          (button) =>
            button.getAttribute("aria-label")?.replace("Select ", "") ?? "",
        );
    }

    function planWithTargets(
      targets: PlanResponse["gameweeks"][number]["legal_rearrangements"],
    ): PlanResponse {
      const plan = buildPlan([{ gameweek_number: 1 }]);
      plan.gameweeks[0].legal_rearrangements = targets;
      return plan;
    }

    function exchangeRoles(
      plan: PlanResponse,
      gameweek: number,
      firstId: number,
      secondId: number,
    ): PlanResponse {
      const week = plan.gameweeks.find(
        (item) => item.gameweek_number === gameweek,
      )!;
      const first = week.players.find((p) => p.player_id === firstId)!;
      const second = week.players.find((p) => p.player_id === secondId)!;
      const roles = (p: PlanPlayer) => ({
        is_starting: p.is_starting,
        bench_order: p.bench_order,
        is_captain: p.is_captain,
        is_vice_captain: p.is_vice_captain,
      });
      const [firstRoles, secondRoles] = [roles(first), roles(second)];
      Object.assign(first, secondRoles);
      Object.assign(second, firstRoles);
      return plan;
    }

    function applySwaps(plan: PlanResponse, intents: PlanIntent[]) {
      for (const intent of intents) {
        if (intent.kind === "swap_lineup_players")
          exchangeRoles(
            plan,
            intent.gameweek_number,
            intent.first_player_id,
            intent.second_player_id,
          );
      }
      return applyPlannerIntents(plan, intents);
    }

    const targets: PlanResponse["gameweeks"][number]["legal_rearrangements"] = [
      { first_player_id: 1, second_player_id: 2, kind: "substitution" },
      { first_player_id: 3, second_player_id: 7, kind: "substitution" },
      { first_player_id: 7, second_player_id: 12, kind: "bench_priority" },
    ];

    it("replaces the dropdown swap with a Select control on every starter and bench card", async () => {
      mockFetch(planWithTargets(targets));

      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });

      expect(screen.getAllByRole("button", { name: /^Select / })).toHaveLength(
        15,
      );
      expect(
        screen.queryByRole("button", { name: /^Swap .* with bench$/ }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /^Swap .* for / }),
      ).not.toBeInTheDocument();
      expect(screen.queryByText("Swap With Bench")).not.toBeInTheDocument();
      expect(selectButton("GK One")).toHaveAttribute("aria-pressed", "false");
    });

    it("marks only the server's targets when a starter is selected", async () => {
      mockFetch(planWithTargets(targets));
      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });

      fireEvent.click(selectButton("DEF One"));

      expect(selectButton("DEF One")).toHaveAttribute("aria-pressed", "true");
      expect(selectionState("DEF One")).toBe("selected");
      expect(selectionState("DEF Five")).toBe("target");
      expect(selectionState("MID Five")).toBe("not-target");
      expect(selectionState("GK Two")).toBe("not-target");
      expect(selectionState("MID One")).toBe("not-target");
    });

    it("marks starters and bench-priority targets when a substitute is selected first", async () => {
      mockFetch(planWithTargets(targets));
      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });

      fireEvent.click(selectButton("DEF Five"));

      expect(selectionState("DEF One")).toBe("target");
      expect(selectionState("MID Five")).toBe("target");
      expect(selectionState("GK Two")).toBe("not-target");
      expect(selectionState("GK One")).toBe("not-target");
    });

    it("never offers the bench goalkeeper against outfield substitutes unless the server lists it", async () => {
      mockFetch(planWithTargets(targets));
      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });

      fireEvent.click(selectButton("GK Two"));

      expect(selectionState("GK One")).toBe("target");
      for (const name of ["DEF Five", "MID Five", "FWD Three"]) {
        expect(selectionState(name)).toBe("not-target");
      }
    });

    it("replaces or cancels a selection without saving anything", async () => {
      const saveCalls = mockFetch(planWithTargets(targets));
      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });

      fireEvent.click(selectButton("GK One"));
      fireEvent.click(selectButton("DEF One"));
      expect(selectButton("DEF One")).toHaveAttribute("aria-pressed", "true");
      expect(selectButton("GK One")).toHaveAttribute("aria-pressed", "false");

      fireEvent.click(selectButton("DEF One"));
      expect(selectButton("DEF One")).toHaveAttribute("aria-pressed", "false");

      fireEvent.click(selectButton("GK One"));
      fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
      expect(selectButton("GK One")).toHaveAttribute("aria-pressed", "false");
      expect(
        screen.queryByRole("button", { name: "Clear selection" }),
      ).not.toBeInTheDocument();
      expect(saveCalls).toHaveLength(0);
    });

    it("describes valid targets to assistive technology and announces when there are none", async () => {
      mockFetch(planWithTargets(targets));
      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });
      const notice = screen.getByTestId("no-targets-notice");
      expect(notice).toHaveAttribute("aria-live", "polite");
      expect(notice).toBeEmptyDOMElement();

      fireEvent.click(selectButton("DEF One"));
      expect(selectButton("DEF Five")).toHaveAccessibleDescription(
        "Valid swap target",
      );
      expect(selectButton("MID Five")).not.toHaveAccessibleDescription();

      fireEvent.click(selectButton("MID One"));
      expect(notice).toHaveTextContent("No valid swap targets for MID One.");
    });

    it("exposes whether a transfer picker is open", async () => {
      mockFetch(planWithTargets(targets));
      render(<PlanBoard planId={1} />);
      const transfer = await screen.findByLabelText("Transfer MID One");
      expect(transfer).toHaveAttribute("aria-expanded", "false");
      fireEvent.click(transfer);
      await waitFor(() =>
        expect(transfer).toHaveAttribute("aria-expanded", "true"),
      );
    });

    it("says so when the selected player has no legal targets", async () => {
      mockFetch(planWithTargets(targets));
      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });

      fireEvent.click(selectButton("MID One"));

      expect(
        screen.getByText("No valid swap targets for MID One."),
      ).toBeInTheDocument();
    });

    it("sends one swap intent for the shown gameweek on the second selection and announces it", async () => {
      const plan = planWithTargets(targets);
      const saveCalls = mockFetch(
        plan,
        exchangeRoles(structuredClone(plan), 1, 3, 7),
      );
      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });

      fireEvent.click(selectButton("DEF One"));
      fireEvent.click(selectButton("DEF Five"));

      await waitFor(() => expect(saveCalls).toHaveLength(1));
      const body = saveCalls[0].body as {
        intents: unknown[];
        players?: unknown;
      };
      expect(body.intents).toEqual([
        {
          kind: "swap_lineup_players",
          gameweek_number: 1,
          first_player_id: 3,
          second_player_id: 7,
        },
      ]);
      expect(body.players).toBeUndefined();
      const announcement = screen.getByTestId("swap-confirmation");
      expect(announcement).toHaveAttribute("aria-live", "polite");
      await waitFor(() =>
        expect(announcement).toHaveTextContent(
          "Swapped DEF One with DEF Five.",
        ),
      );
      expect(selectButton("DEF One")).toHaveAttribute("aria-pressed", "false");
    });

    it("sends a bench-priority swap and words the announcement for it", async () => {
      const plan = planWithTargets(targets);
      const saveCalls = mockFetch(
        plan,
        exchangeRoles(structuredClone(plan), 1, 12, 7),
      );
      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });

      fireEvent.click(selectButton("MID Five"));
      fireEvent.click(selectButton("DEF Five"));

      await waitFor(() => expect(saveCalls).toHaveLength(1));
      expect((saveCalls[0].body as { intents: unknown[] }).intents).toEqual([
        {
          kind: "swap_lineup_players",
          gameweek_number: 1,
          first_player_id: 12,
          second_player_id: 7,
        },
      ]);
      await waitFor(() =>
        expect(screen.getByTestId("swap-confirmation")).toHaveTextContent(
          "Swapped bench order of MID Five and DEF Five.",
        ),
      );
    });

    it("shows the bench in substitute-priority order, not grouped by position", async () => {
      const plan = planWithTargets(targets);
      const orders: Record<number, number> = { 2: 1, 12: 2, 15: 3, 7: 4 };
      for (const player of plan.gameweeks[0].players) {
        if (player.player_id in orders)
          player.bench_order = orders[player.player_id];
      }
      mockFetch(plan);

      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });

      expect(benchNames()).toEqual([
        "GK Two",
        "MID Five",
        "FWD Three",
        "DEF Five",
      ]);
      expect(
        screen.getByText(/ARS · MID · 5\.0 · Bench 2/),
      ).toBeInTheDocument();
    });

    it("shows the reordered bench once the swap is acknowledged", async () => {
      const plan = planWithTargets(targets);
      const saved = structuredClone(plan);
      for (const player of saved.gameweeks[0].players) {
        if (player.player_id === 7) player.bench_order = 3;
        if (player.player_id === 12) player.bench_order = 2;
      }
      mockFetch(plan, saved);
      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });
      expect(benchNames()).toEqual([
        "GK Two",
        "DEF Five",
        "MID Five",
        "FWD Three",
      ]);

      fireEvent.click(selectButton("MID Five"));
      fireEvent.click(selectButton("DEF Five"));

      await waitFor(() =>
        expect(benchNames()).toEqual([
          "GK Two",
          "MID Five",
          "DEF Five",
          "FWD Three",
        ]),
      );
    });

    it("clears the selection when another gameweek is shown", async () => {
      const plan = buildPlan([{ gameweek_number: 1 }, { gameweek_number: 2 }]);
      for (const week of plan.gameweeks) week.legal_rearrangements = targets;
      mockFetch(plan);
      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });

      fireEvent.click(selectButton("DEF One"));
      fireEvent.click(await screen.findByLabelText("Gameweek 2"));

      await waitFor(() =>
        expect(selectButton("DEF One")).toHaveAttribute(
          "aria-pressed",
          "false",
        ),
      );
      expect(
        screen.queryByRole("button", { name: "Clear selection" }),
      ).not.toBeInTheDocument();
    });

    it("drops a selection whose player has left the gameweek instead of dimming every card", async () => {
      const plan = planWithTargets(targets);
      const saved = structuredClone(plan);
      saved.gameweeks[0].players = saved.gameweeks[0].players.filter(
        (player) => player.player_id !== 3,
      );
      mockFetch(plan, saved);
      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });

      fireEvent.click(selectButton("DEF One"));
      expect(selectionState("DEF Two")).toBe("not-target");
      fireEvent.click(screen.getByLabelText("Triple Captain"));

      await waitFor(() =>
        expect(
          screen.queryByRole("button", { name: "Select DEF One" }),
        ).not.toBeInTheDocument(),
      );
      expect(selectionState("DEF Two")).toBe("idle");
      expect(selectionState("GK One")).toBe("idle");
      expect(
        screen.queryByRole("button", { name: "Clear selection" }),
      ).not.toBeInTheDocument();
    });

    async function rejectedSwapBoard() {
      const plan = buildPlan([{ gameweek_number: 1 }, { gameweek_number: 2 }]);
      for (const week of plan.gameweeks) week.legal_rearrangements = targets;
      const { posts } = plannerServer(plan, {
        apply: applySwaps,
        post: async (_envelope, call) =>
          call === 1
            ? json(
                {
                  detail: {
                    code: "formation",
                    message: "Starting XI must contain between 3 and 5 DEF",
                    diagnostics: [],
                  },
                },
                422,
              )
            : undefined,
      });
      render(<PlanBoard planId={plan.plan_id} />);
      await screen.findByRole("button", { name: "Select GK One" });

      fireEvent.click(selectButton("DEF One"));
      fireEvent.click(selectButton("DEF Five"));
      expect(
        await screen.findByText("Starting XI must contain between 3 and 5 DEF"),
      ).toBeInTheDocument();
      expect(screen.getByTestId("swap-confirmation")).toBeEmptyDOMElement();
      return posts;
    }

    const savedStatus = () =>
      waitFor(() =>
        expect(screen.getByRole("status")).toHaveTextContent("Saved"),
      );

    it("never announces a swap the server rejected after a later successful captain change", async () => {
      const posts = await rejectedSwapBoard();

      fireEvent.click(screen.getByLabelText("Make MID Two captain"));
      await waitFor(() => expect(posts).toHaveLength(2));
      await savedStatus();

      expect(screen.getByTestId("swap-confirmation")).toBeEmptyDOMElement();
      expect(screen.queryByText(/^Swapped /)).not.toBeInTheDocument();
    });

    it("never announces a swap the server rejected after a later successful horizon edit", async () => {
      const posts = await rejectedSwapBoard();

      const end = screen.getByLabelText("To GW");
      fireEvent.change(end, { target: { value: "1" } });
      fireEvent.blur(end);
      await waitFor(() => expect(posts).toHaveLength(2));
      await savedStatus();

      expect(screen.getByTestId("swap-confirmation")).toBeEmptyDOMElement();
      expect(screen.queryByText(/^Swapped /)).not.toBeInTheDocument();
    });

    it("announces an accepted swap only after the retried same edit is durably saved", async () => {
      const plan = planWithTargets(targets);
      const candidate = exchangeRoles(structuredClone(plan), 1, 3, 7);
      const { posts } = plannerServer(plan, {
        apply: applySwaps,
        post: async (_envelope, call) =>
          call === 1
            ? json(
                {
                  detail: {
                    code: "accepted_not_saved",
                    message:
                      "Accepted edit is not saved; retry the same mutation ID",
                    plan,
                    candidate,
                  },
                },
                503,
              )
            : undefined,
      });
      render(<PlanBoard planId={plan.plan_id} />);
      await screen.findByRole("button", { name: "Select GK One" });

      fireEvent.click(selectButton("DEF One"));
      fireEvent.click(selectButton("DEF Five"));
      await waitFor(() =>
        expect(screen.getByRole("status")).toHaveTextContent("Not saved"),
      );
      expect(screen.getByTestId("swap-confirmation")).toBeEmptyDOMElement();

      fireEvent.click(screen.getByRole("button", { name: "Retry Same Edit" }));
      await waitFor(() =>
        expect(screen.getByRole("status")).toHaveTextContent("Saved"),
      );
      expect(posts[1]).toEqual(posts[0]);
      expect(screen.getByTestId("swap-confirmation")).toHaveTextContent(
        "Swapped DEF One with DEF Five.",
      );
    });

    it("does not offer selection while a save is in flight", async () => {
      const gate = deferred<void>();
      const plan = planWithTargets(targets);
      vi.spyOn(global, "fetch").mockImplementation(async (_input, init) => {
        if (init?.method !== "POST") {
          return new Response(JSON.stringify(plan), { status: 200 });
        }
        const envelope = JSON.parse(String(init.body)) as Envelope;
        await gate.promise;
        return new Response(
          JSON.stringify({
            status: "committed",
            mutation_id: envelope.mutation_id,
            committed_revision: envelope.expected_revision + 1,
            plan: { ...plan, revision: envelope.expected_revision + 1 },
            candidate: null,
          }),
          { status: 200 },
        );
      });
      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });

      fireEvent.click(selectButton("DEF One"));
      fireEvent.click(selectButton("DEF Five"));

      await waitFor(() =>
        expect(selectButton("DEF One")).toHaveAttribute(
          "aria-disabled",
          "true",
        ),
      );
      expect(selectButton("GK One")).toHaveAttribute("aria-disabled", "true");
      // Never natively disabled, so a keyboard user keeps focus on the control.
      expect(selectButton("GK One")).toBeEnabled();

      gate.resolve();
      await waitFor(() =>
        expect(selectButton("GK One")).not.toHaveAttribute("aria-disabled"),
      );
    });

    it("shows the rule explanation and no confirmation when the server rejects a swap", async () => {
      const plan = planWithTargets(targets);
      vi.spyOn(global, "fetch").mockImplementation(async (_input, init) =>
        init?.method === "POST"
          ? new Response(
              JSON.stringify({
                detail: {
                  code: "formation",
                  message: "Starting XI must contain between 3 and 5 DEF",
                },
              }),
              { status: 422 },
            )
          : new Response(JSON.stringify(plan), { status: 200 }),
      );
      render(<PlanBoard planId={1} />);
      await screen.findByRole("button", { name: "Select GK One" });

      fireEvent.click(selectButton("DEF One"));
      fireEvent.click(selectButton("DEF Five"));

      expect(
        await screen.findByText("Starting XI must contain between 3 and 5 DEF"),
      ).toBeInTheDocument();
      expect(screen.getByTestId("swap-confirmation")).toBeEmptyDOMElement();
    });
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

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });

type Envelope = {
  mutation_id: string;
  expected_revision: number;
  intents: PlanIntent[];
};

function plannerServer(
  plan: PlanResponse,
  hooks: {
    apply?: (plan: PlanResponse, intents: PlanIntent[]) => PlanResponse;
    post?: (
      envelope: Envelope,
      call: number,
      server: ReturnType<typeof createPlannerFixture<PlanResponse, PlanIntent>>,
    ) => Promise<Response | undefined>;
    receipt?: (id: string) => Response | undefined;
  } = {},
) {
  const server = createPlannerFixture<PlanResponse, PlanIntent>(
    plan,
    hooks.apply ?? applyPlannerIntents,
  );
  const posts: Envelope[] = [];
  const receipts: string[] = [];
  vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST") {
      const envelope = JSON.parse(String(init.body)) as Envelope;
      posts.push(envelope);
      const override = await hooks.post?.(envelope, posts.length, server);
      if (override) return override;
      return json({
        ...server.mutate(envelope),
        mutation_id: envelope.mutation_id,
        candidate: null,
      });
    }
    if (url.includes("/mutations/")) {
      const id = url.split("/mutations/")[1];
      receipts.push(id);
      return (
        hooks.receipt?.(id) ??
        json(
          {
            detail: {
              code: "mutation_not_found",
              message: "Mutation receipt is not known",
            },
          },
          404,
        )
      );
    }
    return json(server.read());
  });
  return { server, posts, receipts };
}

const badge = (name: string): string | null =>
  screen
    .getAllByText(name)
    .map((node) => node.closest("article"))
    .find((card) => card !== null)
    ?.querySelector("span.rounded-full")?.textContent ?? null;

const statusText = () => screen.getByRole("status").textContent;

describe("PlanBoard US5 persistence", () => {
  it("keeps pending intent separate from the accepted plan and from financial flags, with no Save Gameweek", async () => {
    const plan = buildPlannerPlan(12, 13);
    plan.financial_status = { provisional: true, requires_resolution: true };
    const gate = deferred<void>();
    const { posts } = plannerServer(plan, {
      post: async (_envelope, call) => {
        if (call === 1) await gate.promise;
        return undefined;
      },
    });
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(await screen.findByLabelText("Make P4 captain"));
    await waitFor(() => expect(statusText()).toBe("Saving..."));
    expect(posts).toHaveLength(1);
    expect(badge("P10")).toBe("C");
    expect(badge("P4")).toBeNull();
    expect(screen.getByText("Requires resolution")).toBeVisible();
    expect(screen.getByText("Estimated bases")).toBeVisible();
    gate.resolve();
    await waitFor(() => expect(statusText()).toBe("Saved"));
    expect(badge("P4")).toBe("C");
    expect(badge("P10")).toBeNull();
    expect(screen.getByText("Requires resolution")).toBeVisible();
    expect(screen.queryByText(/save gameweek/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /save gameweek/i }),
    ).not.toBeInTheDocument();
  });

  it("shows a rejected edit as Saved with its reason, retains Q7 resolution context and the accepted plan", async () => {
    const plan = buildPlannerPlan(12, 13);
    plan.financial_status = {
      provisional: true,
      requires_resolution: true,
      earliest_shortfall_gameweek: 12,
      earliest_shortfall_tenths: 1,
      earliest_shortfall_reason: "Bank is £0.1m below zero in gameweek 12",
      gameweeks: [
        { gameweek_number: 12, shortfall_tenths: 1, affected_chain: [12] },
      ],
    };
    const { posts, server } = plannerServer(plan, {
      post: async () =>
        json(
          {
            detail: {
              code: "formation",
              message: "Illegal formation",
              diagnostics: [],
            },
          },
          422,
        ),
    });
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(await screen.findByLabelText("Make P4 captain"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Illegal formation",
    );
    expect(statusText()).toBe("Saved");
    expect(
      screen.queryByRole("button", { name: "Retry Same Edit" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Financial resolution" }),
    ).toBeVisible();
    expect(screen.getByText("Requires resolution")).toBeVisible();
    expect(badge("P10")).toBe("C");
    expect(badge("P4")).toBeNull();
    expect(posts).toHaveLength(1);
    expect(server.read().revision).toBe(0);
  });

  it("keeps an accepted-but-unsaved candidate across gameweek selection and retries the same ID", async () => {
    const plan = buildPlannerPlan(12, 13);
    const candidate = applyPlannerIntents(structuredClone(plan), [
      { kind: "change_captain", gameweek_number: 12, player_id: 4 },
    ]);
    const { posts, server } = plannerServer(plan, {
      post: async (_envelope, call) =>
        call === 1
          ? json(
              {
                detail: {
                  code: "accepted_not_saved",
                  message:
                    "Accepted edit is not saved; retry the same mutation ID",
                  plan,
                  candidate,
                },
              },
              503,
            )
          : undefined,
    });
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(await screen.findByLabelText("Make P4 captain"));
    await waitFor(() => expect(statusText()).toBe("Not saved"));
    expect(badge("P4")).toBe("C");
    expect(screen.getByLabelText("Make P5 captain")).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Gameweek 13"));
    fireEvent.click(screen.getByLabelText("Gameweek 12"));
    expect(statusText()).toBe("Not saved");
    expect(badge("P4")).toBe("C");
    expect(server.read().revision).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "Retry Same Edit" }));
    await waitFor(() => expect(statusText()).toBe("Saved"));
    expect(posts).toHaveLength(2);
    expect(posts[1]).toEqual(posts[0]);
    expect(server.read().revision).toBe(1);
  });

  it("reconciles a lost success with the same ID instead of posting again", async () => {
    const plan = buildPlannerPlan(12, 13);
    const { posts, receipts, server } = plannerServer(plan, {
      post: async (envelope, call, fake) => {
        if (call === 1) {
          fake.mutate(envelope);
          throw new TypeError("Network response lost");
        }
        return undefined;
      },
      receipt: (id) =>
        json({
          status: "already_committed",
          mutation_id: id,
          committed_revision: 1,
          plan: server.read(),
          candidate: null,
        }),
    });
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(await screen.findByLabelText("Make P4 captain"));
    await waitFor(() => expect(statusText()).toBe("Not saved"));
    fireEvent.click(screen.getByRole("button", { name: "Check Save Status" }));
    await waitFor(() => expect(statusText()).toBe("Saved"));
    expect(receipts).toEqual([posts[0].mutation_id]);
    expect(posts).toHaveLength(1);
    expect(badge("P4")).toBe("C");
    expect(server.read().revision).toBe(1);
  });

  it("treats an unknown receipt as inconclusive and keeps the same ID retryable", async () => {
    const plan = buildPlannerPlan(12, 13);
    const { posts, receipts } = plannerServer(plan, {
      post: async (_envelope, call) => {
        if (call === 1) throw new TypeError("Network response lost");
        return undefined;
      },
    });
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(await screen.findByLabelText("Make P4 captain"));
    await waitFor(() => expect(statusText()).toBe("Not saved"));
    fireEvent.click(screen.getByRole("button", { name: "Check Save Status" }));
    await waitFor(() => expect(receipts).toHaveLength(1));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /not confirmed/i,
    );
    expect(statusText()).toBe("Not saved");
    expect(
      screen.queryByRole("button", { name: "Revalidate With Current Data" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry Same Edit" }));
    await waitFor(() => expect(statusText()).toBe("Saved"));
    expect(posts[1]).toEqual(posts[0]);
  });

  it("stops writing and says so when the plan no longer exists", async () => {
    const plan = buildPlannerPlan(12, 13);
    const { posts } = plannerServer(plan, {
      post: async () =>
        json(
          { detail: { code: "plan_not_found", message: "Plan not found" } },
          404,
        ),
    });
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(await screen.findByLabelText("Make P4 captain"));
    await waitFor(() => expect(statusText()).toBe("Plan missing"));
    expect(screen.getByRole("alert")).toHaveTextContent(/no longer exists/i);
    expect(screen.getByLabelText("Make P5 captain")).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Retry Same Edit" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Revalidate With Current Data" }),
    ).not.toBeInTheDocument();
    expect(posts).toHaveLength(1);
  });

  it("requires explicit revalidation with a new ID after stale pending metadata", async () => {
    const plan = buildPlannerPlan(12, 13);
    const advanced = { ...structuredClone(plan), revision: 2 };
    const { posts, server } = plannerServer(advanced, {
      post: async (_envelope, call) =>
        call === 1
          ? json(
              {
                detail: {
                  code: "stale_reprepare_required",
                  message:
                    "Accepted inputs need explicit revalidation with a new ID",
                  plan: advanced,
                  candidate: null,
                },
              },
              409,
            )
          : undefined,
    });
    vi.mocked(global.fetch).mockImplementationOnce(async () => json(plan));
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(await screen.findByLabelText("Make P4 captain"));
    await waitFor(() => expect(statusText()).toBe("Needs reconciliation"));
    expect(posts).toHaveLength(1);
    fireEvent.click(
      screen.getByRole("button", { name: "Revalidate With Current Data" }),
    );
    await waitFor(() => expect(statusText()).toBe("Saved"));
    expect(posts[1].mutation_id).not.toBe(posts[0].mutation_id);
    expect(posts[1]).toMatchObject({
      expected_revision: 2,
      intents: posts[0].intents,
    });
    expect(server.read().revision).toBe(3);
  });

  it("tells the user a queued edit was not applied when its target disappeared, without stalling", async () => {
    const plan = buildPlannerPlan(12, 13);
    const gate = deferred<void>();
    const { posts } = plannerServer(plan, {
      apply: (current, intents) => {
        const next = applyPlannerIntents(current, intents);
        for (const week of next.gameweeks)
          week.players = week.players.map((player) =>
            player.player_id === 5
              ? { ...player, player_id: 205, web_name: "P205" }
              : player,
          );
        return next;
      },
      post: async (_envelope, call) => {
        if (call === 1) await gate.promise;
        return undefined;
      },
    });
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(await screen.findByLabelText("Make P4 captain"));
    fireEvent.click(screen.getByLabelText("Make P5 captain"));
    gate.resolve();
    expect(await screen.findByText(/Edit not applied/)).toHaveTextContent(
      /select the intended player again/i,
    );
    await waitFor(() => expect(statusText()).toBe("Saved"));
    expect(posts).toHaveLength(1);
  });

  it("keeps the rename editor open after Rename and closes it only when its own save is acknowledged", async () => {
    const plan = buildPlannerPlan(12, 13);
    const { posts } = plannerServer(plan);
    render(<PlanBoard planId={plan.plan_id} />);

    fireEvent.click(await screen.findByRole("button", { name: "Rename plan" }));
    const input = await screen.findByLabelText("Plan name");
    expect(input).toHaveValue(plan.name);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByLabelText("Plan name")).toBeInTheDocument();
    expect(posts).toHaveLength(0);

    fireEvent.change(input, { target: { value: "Renamed plan" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    await waitFor(() =>
      expect(screen.queryByLabelText("Plan name")).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole("heading", { name: "Renamed plan" }),
    ).toBeInTheDocument();
  });

  it("commits a horizon bound on blur only, so typing a multi-digit gameweek never saves intermediate values", async () => {
    const plan = buildPlannerPlan(8, 12);
    const { posts } = plannerServer(plan);
    render(<PlanBoard planId={plan.plan_id} />);
    const end = await screen.findByLabelText("Plan end gameweek");

    fireEvent.change(end, { target: { value: "1" } });
    fireEvent.change(end, { target: { value: "15" } });
    expect(posts).toHaveLength(0);
    expect(end).toHaveValue(15);

    fireEvent.blur(end);
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].intents).toEqual([
      { kind: "change_horizon", start_gameweek: 8, end_gameweek: 15 },
    ]);
  });

  it("puts a horizon bound the server rejected back to the saved value", async () => {
    const plan = buildPlannerPlan(8, 12);
    const { posts } = plannerServer(plan, {
      post: async () =>
        json(
          {
            detail: {
              code: "plan_horizon",
              message: "Start gameweek must not exceed end gameweek",
            },
          },
          422,
        ),
    });
    render(<PlanBoard planId={plan.plan_id} />);
    const end = await screen.findByLabelText("Plan end gameweek");

    fireEvent.change(end, { target: { value: "7" } });
    fireEvent.blur(end);

    expect(
      await screen.findByText("Start gameweek must not exceed end gameweek"),
    ).toBeInTheDocument();
    expect(posts).toHaveLength(1);
    await waitFor(() =>
      expect(screen.getByLabelText("Plan end gameweek")).toHaveValue(12),
    );
  });

  it("restores the field and says why when a horizon bound is not a whole gameweek from 1 to 38", async () => {
    const plan = buildPlannerPlan(8, 12);
    const { posts } = plannerServer(plan);
    render(<PlanBoard planId={plan.plan_id} />);
    const end = await screen.findByLabelText("Plan end gameweek");

    fireEvent.change(end, { target: { value: "39" } });
    fireEvent.blur(end);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /whole gameweek from 1 to 38/i,
    );
    expect(screen.getByLabelText("Plan end gameweek")).toHaveValue(12);
    expect(posts).toHaveLength(0);
  });

  it("guards native and in-app departure only while work is unsaved", async () => {
    const plan = buildPlannerPlan(12, 13);
    const gate = deferred<void>();
    plannerServer(plan, {
      post: async (_envelope, call) => {
        if (call === 1) await gate.promise;
        return undefined;
      },
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const link = document.createElement("a");
    link.href = "/my-team";
    link.textContent = "Elsewhere";
    const reached: boolean[] = [];
    link.addEventListener("click", (event) => {
      reached.push(event.defaultPrevented);
      event.preventDefault();
    });
    document.body.appendChild(link);
    render(<PlanBoard planId={plan.plan_id} />);
    fireEvent.click(await screen.findByLabelText("Make P4 captain"));
    await waitFor(() => expect(statusText()).toBe("Saving..."));
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    link.click();
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(reached).toEqual([]);
    const mail = document.createElement("a");
    mail.href = "mailto:support@example.com";
    mail.addEventListener("click", (event) => event.preventDefault());
    document.body.appendChild(mail);
    mail.click();
    mail.remove();
    expect(confirm).toHaveBeenCalledTimes(1);
    confirm.mockReturnValue(true);
    link.click();
    expect(reached).toEqual([false]);
    gate.resolve();
    await waitFor(() => expect(statusText()).toBe("Saved"));
    const calm = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(calm);
    expect(calm.defaultPrevented).toBe(false);
    link.click();
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(reached).toEqual([false, false]);
    link.remove();
  });

  describe("browser history departure guard (FR-038)", () => {
    const warning =
      "Your latest Planner edit is not saved yet. Leave this page anyway?";
    const popstate = (state: unknown = {}) =>
      window.dispatchEvent(new PopStateEvent("popstate", { state }));
    const sentinel = () =>
      (window.history.state as Record<string, unknown> | null)
        ?.plannerDepartureGuard;

    async function unsavedBoard() {
      const plan = buildPlannerPlan(12, 13);
      const gate = deferred<void>();
      const { posts } = plannerServer(plan, {
        post: async (_envelope, call) => {
          if (call === 1) await gate.promise;
          return undefined;
        },
      });
      render(<PlanBoard planId={plan.plan_id} />);
      await screen.findByLabelText("Make P4 captain");
      return { plan, gate, posts };
    }

    it("leaves history alone and never prompts while nothing is unsaved", async () => {
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      const back = vi.spyOn(window.history, "back");
      const go = vi.spyOn(window.history, "go");
      const length = window.history.length;
      const { gate } = await unsavedBoard();
      expect(window.history.length).toBe(length);
      expect(sentinel()).toBeUndefined();

      popstate();
      expect(confirm).not.toHaveBeenCalled();
      expect(back).not.toHaveBeenCalled();
      expect(go).not.toHaveBeenCalled();
      gate.resolve();
    });

    it("adds exactly one guard entry while work is unsaved, however many edits follow", async () => {
      const { gate } = await unsavedBoard();
      const length = window.history.length;
      fireEvent.click(screen.getByLabelText("Make P4 captain"));
      await waitFor(() => expect(statusText()).toBe("Saving..."));
      expect(sentinel()).toBe(true);
      expect(window.history.length).toBe(length + 1);

      gate.resolve();
      await waitFor(() => expect(statusText()).toBe("Saved"));
      fireEvent.click(screen.getByLabelText("Make P5 captain"));
      await waitFor(() => expect(statusText()).toBe("Saved"));
      expect(window.history.length).toBe(length + 1);
    });

    it("prompts on Back and, when the user stays, restores the entry and keeps the unsaved work", async () => {
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      const back = vi.spyOn(window.history, "back");
      const go = vi.spyOn(window.history, "go").mockImplementation(() => {});
      const { gate, posts } = await unsavedBoard();
      fireEvent.click(screen.getByLabelText("Make P4 captain"));
      await waitFor(() => expect(statusText()).toBe("Saving..."));

      popstate();

      expect(confirm).toHaveBeenCalledTimes(1);
      expect(confirm).toHaveBeenCalledWith(warning);
      expect(go).toHaveBeenCalledWith(1);
      expect(back).not.toHaveBeenCalled();
      expect(statusText()).toBe("Saving...");
      popstate({ plannerDepartureGuard: true });
      expect(confirm).toHaveBeenCalledTimes(1);

      popstate();
      expect(confirm).toHaveBeenCalledTimes(2);
      gate.resolve();
      await waitFor(() => expect(statusText()).toBe("Saved"));
      expect(posts).toHaveLength(1);
    });

    it("lets the user leave once confirmed, without a second native prompt", async () => {
      vi.spyOn(window, "confirm").mockReturnValue(true);
      const back = vi
        .spyOn(window.history, "back")
        .mockImplementation(() => {});
      const { gate } = await unsavedBoard();
      fireEvent.click(screen.getByLabelText("Make P4 captain"));
      await waitFor(() => expect(statusText()).toBe("Saving..."));

      popstate();

      expect(back).toHaveBeenCalledTimes(1);
      const unload = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(unload);
      expect(unload.defaultPrevented).toBe(false);
      popstate();
      expect(back).toHaveBeenCalledTimes(1);
      gate.resolve();
    });

    it("stops prompting once the edit is durably saved and passes Back straight through", async () => {
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      const back = vi
        .spyOn(window.history, "back")
        .mockImplementation(() => {});
      const { gate } = await unsavedBoard();
      fireEvent.click(screen.getByLabelText("Make P4 captain"));
      await waitFor(() => expect(statusText()).toBe("Saving..."));
      gate.resolve();
      await waitFor(() => expect(statusText()).toBe("Saved"));

      popstate();

      expect(confirm).not.toHaveBeenCalled();
      expect(back).toHaveBeenCalledTimes(1);
      const unload = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(unload);
      expect(unload.defaultPrevented).toBe(false);
    });

    it("still guards beforeunload while the edit is unsaved", async () => {
      const { gate } = await unsavedBoard();
      fireEvent.click(screen.getByLabelText("Make P4 captain"));
      await waitFor(() => expect(statusText()).toBe("Saving..."));
      const unload = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(unload);
      expect(unload.defaultPrevented).toBe(true);
      gate.resolve();
    });
  });
});

describe("PlanBoard with a pinned Explorer submission", () => {
  it("never replays a pinned transfer when Revalidate With Current Data is pressed", async () => {
    const plan = buildPlannerPlan(12, 14);
    const posts: string[] = [];
    vi.spyOn(global, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST") {
        posts.push(String(init.body));
        return Response.json(
          {
            detail: {
              code: "revision_conflict",
              message: "Plan revision has advanced",
            },
          },
          { status: 409 },
        );
      }
      return Response.json(plan);
    });
    render(<PlanBoard planId={plan.plan_id} />);
    await screen.findByLabelText("Gameweek 12");
    const coordinator = getPlanSaveCoordinator(plan);

    coordinator.submitPinned({
      expectedRevision: 0,
      intents: [
        {
          kind: "add_transfer",
          gameweek_number: 12,
          outgoing_player_id: 6,
          outgoing_ownership_id: plannerIdentity(1006),
          incoming_player_id: 106,
        },
      ],
    });
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Revalidate With Current Data",
      }),
    );

    await waitFor(() => expect(coordinator.getSnapshot().pinned).toBeNull());
    expect(posts).toHaveLength(1);
    expect(
      screen.queryByRole("button", { name: "Revalidate With Current Data" }),
    ).not.toBeInTheDocument();
  });
});
