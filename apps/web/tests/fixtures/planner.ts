import type { PlanChip, PlanIntent, PlanResponse } from "@/lib/api";

export function plannerIdentity(value: number): string {
  return `00000000-0000-0000-0000-${value.toString(16).padStart(12, "0")}`;
}

export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

export const frozenPlannerQuote = {
  outgoing_market_tenths: 54,
  incoming_price_tenths: 50,
  source: "stored_player_observation",
  observed_at: "2026-10-14T12:00:00+00:00",
  origin: "captured",
} as const;

let nextPlanId = 100;

export function buildPlannerPlan(start = 12, end = 14): PlanResponse {
  const positions = [
    "GK",
    "DEF",
    "DEF",
    "DEF",
    "DEF",
    "MID",
    "MID",
    "MID",
    "MID",
    "FWD",
    "FWD",
    "GK",
    "DEF",
    "MID",
    "FWD",
  ] as const;
  const players = positions.map((position, index) => ({
    player_id: index + 1,
    web_name: `P${index + 1}`,
    team_short_name: `T${index + 1}`,
    position,
    current_price: 5,
    status: "a",
    is_starting: index < 11,
    bench_order: index < 11 ? null : index - 10,
    is_captain: index === 9,
    is_vice_captain: index === 10,
    projected_points: 2,
    fixtures: [],
    slot_id: plannerIdentity(index + 1),
    ownership_id: plannerIdentity(index + 1001),
    source_decision_id: null,
    purchase_price_tenths: 50,
    provenance: {
      source: "my_team_stored_market",
      original_price_tenths: 50,
      basis_kind: "starting" as const,
      confirmation: "assumed" as const,
    },
  }));
  const chips: PlanChip[] = [
    "WILDCARD",
    "FREE_HIT",
    "BENCH_BOOST",
    "TRIPLE_CAPTAIN",
  ];
  return {
    plan_id: nextPlanId++,
    name: "Starting state",
    start_gameweek: start,
    end_gameweek: end,
    initial_bank: 1,
    initial_free_transfers: 1,
    total_points: 72,
    total_points_hit: 0,
    revision: 0,
    evaluator_version: "planner-foundations-1",
    foundation_state: "ready",
    starting_state: {
      players: players.map((player) => ({
        slot_id: player.slot_id,
        ownership_id: player.ownership_id,
        player_id: player.player_id,
        web_name: player.web_name,
        purchase_price_tenths: 50,
        provenance: player.provenance,
      })),
      lineup: players.map(
        ({
          slot_id,
          is_starting,
          bench_order,
          is_captain,
          is_vice_captain,
        }) => ({
          slot_id,
          is_starting,
          bench_order,
          is_captain,
          is_vice_captain,
        }),
      ),
      bank_tenths: 10,
      free_transfers: start === 1 ? null : 1,
      used_chips: [],
      free_hit_gameweek_19: false,
      origin: "my_team_capture",
      bank_assumptions: [],
    },
    financial_status: {
      provisional: true,
      requires_resolution: false,
      earliest_shortfall_gameweek: null,
    },
    decision_errors: [],
    initialization: { ready: true, boundary_origin: "my_team_capture" },
    gameweeks: Array.from({ length: end - start + 1 }, (_, index) => ({
      gameweek_number: start + index,
      chip: null,
      bank: 1,
      free_transfers_available:
        index === 0 && start === 1 ? null : ([1, 2, 3, 4, 5][index] ?? 5),
      unlimited_transfers: index === 0 && start === 1,
      transfers_made: 0,
      points_hit: 0,
      starting_points: 22,
      bench_points: 0,
      captain_bonus_points: 2,
      total_points: 24,
      players: structuredClone(players),
      transfers_in: [],
      transfers_out: [],
      decisions: [],
      accounting: {
        starting_bank_tenths: 10,
        closing_bank_tenths: 10,
        free_transfers_available:
          index === 0 && start === 1 ? null : ([1, 2, 3, 4, 5][index] ?? 5),
        next_free_transfers: [2, 3, 4, 5][index] ?? 5,
        unlimited_transfers: index === 0 && start === 1,
        transfers_made: 0,
        points_hit: 0,
      },
      chip_availability: Object.fromEntries(
        chips.map((chip) => [
          chip,
          { state: "available", reason: null, conflicting_gameweek: null },
        ]),
      ),
      legal_rearrangements: [
        { first_player_id: 1, second_player_id: 12, kind: "substitution" },
        { first_player_id: 2, second_player_id: 13, kind: "substitution" },
      ],
      evaluation_status: "complete",
    })),
  };
}

export function createPlannerFixture<Plan extends { revision: number }, Intent>(
  initial: Plan,
  apply: (plan: Plan, intents: Intent[]) => Plan,
) {
  let plan = structuredClone(initial);
  const receipts = new Map<
    string,
    {
      digest: string;
      status: "validated_pending" | "committed";
      committed_revision?: number;
    }
  >();
  const requests: {
    mutation_id: string;
    expected_revision: number;
    intents: Intent[];
  }[] = [];
  return {
    receipts,
    requests,
    read: () => structuredClone(plan),
    mutate(envelope: (typeof requests)[number]) {
      requests.push(structuredClone(envelope));
      const digest = JSON.stringify(envelope);
      const prior = receipts.get(envelope.mutation_id);
      if (prior && prior.digest !== digest)
        throw new Error("mutation_id_reused");
      if (prior?.status === "committed") {
        return {
          status: "already_committed" as const,
          committed_revision: prior.committed_revision ?? null,
          plan,
        };
      }
      if (envelope.expected_revision !== plan.revision)
        throw new Error("revision_conflict");
      receipts.set(envelope.mutation_id, {
        digest,
        status: "validated_pending",
      });
      plan = {
        ...apply(structuredClone(plan), envelope.intents),
        revision: plan.revision + 1,
      };
      receipts.set(envelope.mutation_id, {
        digest,
        status: "committed",
        committed_revision: plan.revision,
      });
      return {
        status: "committed" as const,
        committed_revision: plan.revision,
        plan: structuredClone(plan),
      };
    },
  };
}

export function applyPlannerIntents(
  plan: PlanResponse,
  intents: PlanIntent[],
): PlanResponse {
  for (const intent of intents) {
    if (intent.kind === "rename_plan") plan.name = intent.name;
    if (intent.kind === "remove_transfer")
      for (const week of plan.gameweeks)
        week.decisions = week.decisions.filter(
          (decision) => decision.decision_id !== intent.decision_id,
        );
    if (
      intent.kind !== "change_captain" &&
      intent.kind !== "change_vice_captain"
    )
      continue;
    const week = plan.gameweeks.find(
      (item) => item.gameweek_number === intent.gameweek_number,
    )!;
    for (const player of week.players) {
      if (intent.kind === "change_captain")
        player.is_captain = player.player_id === intent.player_id;
      else player.is_vice_captain = player.player_id === intent.player_id;
    }
  }
  return plan;
}
