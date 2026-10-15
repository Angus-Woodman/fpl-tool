import { expect, test, type Page } from "@playwright/test";

import type { PlanDecision, PlanIntent, PlanResponse } from "../../src/lib/api";
import {
  buildPlannerPlan,
  createPlannerFixture,
  deferred,
  plannerIdentity,
} from "../fixtures/planner";

test.use({ baseURL: process.env.PLANNER_BASE_URL ?? "http://127.0.0.1:3000" });

const HEADERS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "content-type",
  "access-control-allow-methods": "GET,POST,OPTIONS",
};

function startingEdit(plan: PlanResponse, intents: PlanIntent[]): PlanResponse {
  if (!plan.starting_state) throw new Error("Missing fixture boundary");
  for (const intent of intents) {
    if (intent.kind === "set_starting_transfers") {
      plan.starting_state.free_transfers = intent.value;
      plan.gameweeks[0].free_transfers_available = intent.value;
      if (plan.gameweeks[0].accounting)
        plan.gameweeks[0].accounting.free_transfers_available = intent.value;
    } else if (intent.kind === "set_starting_chips") {
      if (intent.used_chips.includes("TRIPLE_CAPTAIN"))
        throw new Error("Gameweek 18: Triple Captain is already planned");
      plan.starting_state.used_chips = intent.used_chips;
      plan.starting_state.free_hit_gameweek_19 = intent.free_hit_gameweek_19;
      for (const week of plan.gameweeks) {
        if (week.gameweek_number < 20)
          week.chip_availability.WILDCARD = intent.used_chips.includes(
            "WILDCARD",
          )
            ? {
                state: "used_before",
                reason: "Used before this plan",
                conflicting_gameweek: null,
              }
            : { state: "available", reason: null, conflicting_gameweek: null };
        if (
          plan.start_gameweek === 20 &&
          week.gameweek_number === 20 &&
          intent.free_hit_gameweek_19
        ) {
          week.chip_availability.FREE_HIT = {
            state: "rule_unavailable",
            reason: "Free Hit conflicts with gameweek 19",
            conflicting_gameweek: 19,
          };
        }
      }
    } else if (
      intent.kind === "correct_purchase_price" ||
      intent.kind === "confirm_purchase_price"
    ) {
      const player = plan.starting_state.players.find(
        (item) => item.ownership_id === intent.ownership_id,
      );
      if (!player) throw new Error("Missing fixture ownership");
      if (intent.kind === "correct_purchase_price")
        player.purchase_price_tenths = intent.price_tenths;
      if (player.provenance.basis_kind === "starting")
        player.provenance.confirmation = "user_confirmed";
    } else if (intent.kind === "change_captain") {
      const week = plan.gameweeks.find(
        (item) => item.gameweek_number === intent.gameweek_number,
      )!;
      week.players.forEach((player) => {
        player.is_captain = player.player_id === intent.player_id;
      });
    } else {
      throw new Error(`Unexpected fixture intent ${intent.kind}`);
    }
  }
  return plan;
}

async function installPlanner(
  page: Page,
  initial: PlanResponse,
  apply = startingEdit,
  options: { creation?: boolean; readGate?: Promise<void> } = {},
) {
  const server = createPlannerFixture(initial, apply);
  let created = !options.creation;
  const methods: string[] = [];
  const creations: unknown[] = [];
  let myTeamBank = 1;
  const myTeamReads: string[] = [];
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (method === "OPTIONS")
      return route.fulfill({ status: 204, headers: HEADERS });
    methods.push(method);
    if (method === "POST" && path.endsWith("/mutations")) {
      const envelope = request.postDataJSON();
      try {
        return await route.fulfill({
          json: {
            ...server.mutate(envelope),
            mutation_id: envelope.mutation_id,
            candidate: null,
          },
          headers: HEADERS,
        });
      } catch (error) {
        return route.fulfill({
          status: 422,
          json: {
            detail: { code: "chip_used_before", message: String(error) },
          },
          headers: HEADERS,
        });
      }
    }
    if (method === "POST" && path === "/plans") {
      creations.push(request.postDataJSON());
      created = true;
      return route.fulfill({
        status: 201,
        json: server.read(),
        headers: HEADERS,
      });
    }
    if (method !== "GET") throw new Error(`Unexpected writer ${method}`);
    if (path === "/plans")
      return route.fulfill({
        json: { plans: created ? [server.read()] : [] },
        headers: HEADERS,
      });
    if (path === "/players")
      return route.fulfill({
        json: {
          items: [
            {
              id: 104,
              web_name: "Replacement P104",
              position: "DEF",
              current_price: 5.2,
              status: "a",
              team_short_name: "NEW",
              first_name: "Replacement",
              second_name: "P104",
              team_name: "New Team",
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        },
        headers: HEADERS,
      });
    if (path === "/my-team") {
      myTeamReads.push(path);
      return route.fulfill({
        json: { bank: myTeamBank, free_transfers: 5, players: [] },
        headers: HEADERS,
      });
    }
    if (options.readGate) await options.readGate;
    return route.fulfill({ json: server.read(), headers: HEADERS });
  });
  return {
    ...server,
    methods,
    creations,
    myTeamReads,
    changeMyTeam: () => {
      myTeamBank = 99;
    },
  };
}

async function saved(page: Page) {
  await expect(
    page.getByRole("status").filter({ hasText: /^Saved$/ }),
  ).toBeVisible();
}

async function editNumber(page: Page, label: string, value: string) {
  await page.getByLabel(label, { exact: true }).fill(value);
  await page.getByLabel(label, { exact: true }).press("Tab");
  await saved(page);
}

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test(`US1 create, edit and reopen an independent starting state at ${viewport.width}px`, async ({
    page,
  }, info) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const initial = buildPlannerPlan(12, 21);
    initial.name = "US1 independent capture";
    initial.gameweeks[6].chip = "TRIPLE_CAPTAIN";
    for (const week of initial.gameweeks.slice(0, 8)) {
      week.chip_availability.TRIPLE_CAPTAIN = {
        state:
          week.gameweek_number === 18 ? "planned_here" : "planned_elsewhere",
        reason: week.gameweek_number === 18 ? null : "Planned for gameweek 18",
        conflicting_gameweek: week.gameweek_number === 18 ? null : 18,
      };
    }
    const server = await installPlanner(page, initial, startingEdit, {
      creation: true,
    });
    await page.goto("/plans");
    await page.getByLabel("Plan name", { exact: true }).fill(initial.name);
    await page.getByLabel("Start gameweek", { exact: true }).fill("12");
    await page.getByLabel("End gameweek", { exact: true }).fill("21");
    await page
      .getByRole("button", { name: "Create Plan", exact: true })
      .click();
    await page.getByRole("link", { name: initial.name, exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Starting state at GW12" }),
    ).toBeVisible();
    await expect(page.getByText("Estimated", { exact: true })).toHaveCount(15);
    await editNumber(page, "Starting free transfers", "3");
    await page
      .getByLabel("Wildcard used before this plan", { exact: true })
      .click();
    await saved(page);
    await expect(
      page.getByRole("button", { name: "Wildcard", exact: true }),
    ).toBeDisabled();
    await expect(
      page.getByText("Used before this plan", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Planned for gameweek 18", { exact: true }),
    ).toBeVisible();
    await page
      .getByLabel("Triple Captain used before this plan", { exact: true })
      .click();
    await expect(
      page.getByRole("alert").filter({ hasText: "Gameweek 18" }),
    ).toBeVisible();
    await expect(
      page.getByLabel("Triple Captain used before this plan", { exact: true }),
    ).not.toBeChecked();
    await expect(page.getByLabel("Gameweek 18", { exact: true })).toContainText(
      "TRIPLE_CAPTAIN",
    );
    await editNumber(page, "P1 purchase price", "4.8");
    await page
      .getByRole("button", { name: "Confirm P2 purchase price", exact: true })
      .click();
    await saved(page);
    await expect(page.getByText("Estimated", { exact: true })).toHaveCount(13);
    await page.getByLabel("Gameweek 20", { exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Wildcard", exact: true }),
    ).toBeEnabled();
    await page
      .getByRole("button", { name: "Make P4 captain", exact: true })
      .click();
    await saved(page);
    server.changeMyTeam();
    await page.reload();
    await expect(
      page.getByLabel("Starting free transfers", { exact: true }),
    ).toHaveValue("3");
    await expect(
      page.getByLabel("Wildcard used before this plan", { exact: true }),
    ).toBeChecked();
    await expect(
      page.getByLabel("P1 purchase price", { exact: true }),
    ).toHaveValue("4.8");
    await expect(page.getByText("Estimated", { exact: true })).toHaveCount(13);
    await expect(
      page.getByRole("button", { name: "Save Gameweek", exact: true }),
    ).toHaveCount(0);
    expect(server.creations).toEqual([
      { name: initial.name, start_gameweek: 12, end_gameweek: 21 },
    ]);
    expect(server.read().starting_state?.bank_tenths).toBe(10);
    expect(
      server.read().starting_state?.players[0].provenance.original_price_tenths,
    ).toBe(50);
    expect(server.myTeamReads).toEqual([]);
    expect(server.methods).not.toContain("PATCH");
    expect(server.methods).not.toContain("PUT");
    expect(errors).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: info.outputPath("starting-state.png"),
      fullPage: true,
    });
  });

  test(`US1 rebase, correct and edit the retained acquisition at ${viewport.width}px`, async ({
    page,
  }, info) => {
    await page.setViewportSize(viewport);
    const initial = buildPlannerPlan(12, 14);
    initial.name = "Legacy assumed plan";
    initial.starting_state!.origin = "legacy_first_gameweek_assumed";
    const prefixId = plannerIdentity(2001);
    const retainedId = plannerIdentity(2002);
    const provenance = {
      source: `decision:${prefixId}:stored_player_observation`,
      original_price_tenths: 50,
      basis_kind: "planned_acquisition" as const,
      confirmation: null,
    };
    const decision = (
      id: string,
      outgoing: number,
      incoming: number,
      ownership: number,
      acquisition: number,
    ): PlanDecision => ({
      decision_id: id,
      outgoing_player_id: outgoing,
      outgoing_ownership_id: plannerIdentity(ownership),
      incoming_player_id: incoming,
      incoming_ownership_id: plannerIdentity(acquisition),
      outgoing_market_tenths: 50,
      incoming_price_tenths: 50,
      observation_source: "stored_player_observation",
      observed_at: "2026-10-14T12:00:00+00:00",
      origin: "captured",
      selling_price_tenths: 50,
    });
    initial.gameweeks[0].decisions = [decision(prefixId, 2, 102, 1002, 3001)];
    initial.gameweeks[0].decisions[0].outgoing_market_tenths = 54;
    initial.gameweeks[1].decisions = [
      decision(retainedId, 102, 103, 3001, 3002),
    ];
    for (const week of initial.gameweeks) {
      week.players[1] = {
        ...week.players[1],
        player_id: week.gameweek_number === 12 ? 102 : 103,
        web_name: week.gameweek_number === 12 ? "P102" : "P103",
        ownership_id: plannerIdentity(
          week.gameweek_number === 12 ? 3001 : 3002,
        ),
        source_decision_id: week.gameweek_number === 12 ? prefixId : retainedId,
        provenance,
      };
    }
    const rebased = structuredClone(initial);
    rebased.start_gameweek = 13;
    rebased.gameweeks = rebased.gameweeks.slice(1);
    rebased.starting_state!.origin = "rebased_plan";
    rebased.starting_state!.bank_tenths = 12;
    rebased.starting_state!.bank_assumptions = [plannerIdentity(1002)];
    rebased.starting_state!.players[1] = {
      ...rebased.starting_state!.players[1],
      player_id: 102,
      web_name: "P102",
      ownership_id: plannerIdentity(3001),
      provenance,
    };
    const server = await installPlanner(page, initial, (plan, intents) => {
      const intent = intents[0];
      if (intent.kind === "change_horizon")
        return { ...structuredClone(rebased), revision: plan.revision };
      if (intent.kind === "edit_transfer") {
        if (intent.decision_id !== retainedId)
          throw new Error("Wrong acquisition edited");
        plan.gameweeks[0].decisions[0] = {
          ...plan.gameweeks[0].decisions[0],
          incoming_player_id: 104,
          outgoing_market_tenths: 56,
          incoming_price_tenths: 52,
        };
        plan.gameweeks.forEach((week) => {
          week.players[1] = {
            ...week.players[1],
            player_id: 104,
            web_name: "Replacement P104",
          };
        });
        return plan;
      }
      return startingEdit(plan, intents);
    });
    await page.goto(`/plans/${initial.plan_id}`);
    await page.getByLabel("Plan start gameweek", { exact: true }).fill("13");
    await expect(
      page.getByRole("heading", { name: "Starting state at GW13" }),
    ).toBeVisible();
    await expect(page.getByLabel("Gameweek 12", { exact: true })).toHaveCount(
      0,
    );
    await expect(
      page.getByRole("button", {
        name: "Confirm P102 purchase price",
        exact: true,
      }),
    ).toHaveCount(0);
    const row = page
      .getByLabel("P102 purchase price", { exact: true })
      .locator("xpath=ancestor::li");
    await expect(row).toContainText("Planned acquisition");
    await expect(row).toContainText("Original 5.0");
    await editNumber(page, "P102 purchase price", "4.8");
    await editNumber(page, "Starting free transfers", "0");
    await page
      .getByLabel("Wildcard used before this plan", { exact: true })
      .click();
    await saved(page);
    await page
      .getByRole("button", { name: "Transfer P103", exact: true })
      .click();
    await page.getByRole("button", { name: /Replacement P104/ }).click();
    await saved(page);
    expect(server.requests.at(-1)?.intents).toEqual([
      {
        kind: "edit_transfer",
        decision_id: retainedId,
        incoming_player_id: 104,
      },
    ]);
    expect(server.read().starting_state?.bank_tenths).toBe(12);
    expect(server.read().starting_state?.players[1].provenance).toEqual(
      provenance,
    );
    expect(server.read().gameweeks[0].decisions[0].incoming_ownership_id).toBe(
      plannerIdentity(3002),
    );
    expect(
      server.read().gameweeks[0].players.map((player) => player.slot_id),
    ).toEqual(initial.gameweeks[1].players.map((player) => player.slot_id));
    await page.reload();
    await expect(
      page.getByLabel("P102 purchase price", { exact: true }),
    ).toHaveValue("4.8");
    await expect(
      page.getByLabel("Starting free transfers", { exact: true }),
    ).toHaveValue("0");
    await expect(
      page.getByRole("button", {
        name: "Transfer Replacement P104",
        exact: true,
      }),
    ).toBeEnabled();
    await expect(
      page.getByLabel("Wildcard used before this plan", { exact: true }),
    ).toBeChecked();
    expect(server.methods).not.toContain("PATCH");
    expect(server.methods).not.toContain("PUT");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: info.outputPath("rebased-starting-state.png"),
      fullPage: true,
    });
  });
}

for (const start of [1, 20, 25]) {
  test(`US1 boundary controls and FT0 at GW${start}`, async ({ page }) => {
    const initial = buildPlannerPlan(start, start + 1);
    if (start === 1)
      for (const chip of ["WILDCARD", "FREE_HIT"] as const) {
        initial.gameweeks[0].chip_availability[chip] = {
          state: "rule_unavailable",
          reason: `${chip} is unavailable in gameweek 1`,
          conflicting_gameweek: null,
        };
      }
    await installPlanner(page, initial);
    await page.goto(`/plans/${initial.plan_id}`);
    await expect(
      page.getByRole("heading", { name: `Starting state at GW${start}` }),
    ).toBeVisible();
    if (start === 1) {
      await expect(
        page.getByText("Free transfers: N/A (unlimited)"),
      ).toBeVisible();
      await expect(
        page.getByLabel("Starting free transfers", { exact: true }),
      ).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: "Wildcard", exact: true }),
      ).toBeDisabled();
      await expect(
        page.getByRole("button", { name: "Free Hit", exact: true }),
      ).toBeDisabled();
    } else {
      await editNumber(page, "Starting free transfers", "0");
      await expect(page.getByText(/Bank 1.0 · Free transfers 0/)).toBeVisible();
    }
    if (start === 20) {
      await expect(
        page.getByLabel("Wildcard used before this plan", { exact: true }),
      ).toHaveCount(0);
      await page.getByLabel("Free Hit used in GW19", { exact: true }).click();
      await saved(page);
      await expect(
        page.getByRole("button", { name: "Free Hit", exact: true }),
      ).toBeDisabled();
      await expect(
        page.getByText("Free Hit conflicts with gameweek 19", { exact: true }),
      ).toBeVisible();
    }
    if (start === 25)
      await expect(
        page.getByRole("group", { name: "Chips used before GW25 (GW20-38)" }),
      ).toBeVisible();
  });
}

test("US1 real API horizon changes never reinterpret chip history", async ({
  page,
}, info) => {
  const api = process.env.PLANNER_TEST_API_URL;
  const planId = process.env.PLANNER_TEST_PLAN_ID;
  test.skip(!api || !planId, "Run through the guarded API browser regression");
  const horizons: PlanIntent[] = [];
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS")
      return route.fulfill({ status: 204, headers: HEADERS });
    expect(["GET", "POST"]).toContain(request.method());
    if (request.method() === "POST") {
      for (const intent of request.postDataJSON().intents as PlanIntent[])
        if (intent.kind === "change_horizon") horizons.push(intent);
    }
    const url = new URL(request.url());
    const response = await route.fetch({
      url: `${api}${url.pathname}${url.search}`,
    });
    await route.fulfill({
      response,
      headers: { ...response.headers(), ...HEADERS },
    });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/plans/${planId}`);
  const used = page.getByLabel("Wildcard used before this plan", {
    exact: true,
  });
  await expect(used).toBeChecked();
  for (const target of [19, 25, 19]) {
    if (target === 19 && horizons.length > 0) {
      await page.setViewportSize({ width: 390, height: 844 });
      await used.click();
      await saved(page);
    }
    await page
      .getByLabel("Plan start gameweek", { exact: true })
      .fill(String(target));
    await expect(
      page.getByRole("heading", {
        name: `Starting state at GW${target}`,
        exact: true,
      }),
    ).toBeVisible();
    await saved(page);
    await expect(used).not.toBeChecked();
    await page.reload();
    await expect(used).not.toBeChecked();
    if (target === 19 && horizons.length === 1) {
      await used.click();
      await saved(page);
    }
  }
  expect(horizons).toEqual(
    [19, 25, 19].map((start_gameweek) => ({
      kind: "change_horizon",
      start_gameweek,
      end_gameweek: 26,
    })),
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("real-api-earlier-horizon.png"),
    fullPage: true,
  });
});

test("US3 real API transfers accounting, no phantom moves and explicit atomic repair", async ({
  page,
}, info) => {
  test.setTimeout(90_000);
  const api = process.env.PLANNER_TEST_API_URL;
  const planId = process.env.PLANNER_TEST_PLAN_ID;
  test.skip(!api || !planId, "Run through the guarded API browser regression");
  const errors: string[] = [];
  const mutations: { intents: PlanIntent[]; expected_revision: number }[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS")
      return route.fulfill({ status: 204, headers: HEADERS });
    expect(["GET", "POST"]).toContain(request.method());
    if (request.method() === "POST") mutations.push(request.postDataJSON());
    const url = new URL(request.url());
    const response = await route.fetch({
      url: `${api}${url.pathname}${url.search}`,
    });
    expect([200, 422]).toContain(response.status());
    await route.fulfill({
      response,
      headers: { ...response.headers(), ...HEADERS },
    });
  });
  const read = async (): Promise<PlanResponse> =>
    (await page.request.get(`${api}/plans/${planId}`)).json();
  const select = async (number: number) =>
    page.getByLabel(`Gameweek ${number}`, { exact: true }).click();
  const write = async (action: () => Promise<unknown>, status = 200) => {
    const response = page.waitForResponse(
      (item) =>
        item.url().endsWith("/mutations") && item.request().method() === "POST",
    );
    await action();
    expect((await response).status()).toBe(status);
    if (status === 200) await saved(page);
  };
  const transfer = async (outgoing: number, incoming: number, status = 200) => {
    await page.getByLabel(`Transfer P${outgoing}`, { exact: true }).click();
    await write(
      () =>
        page.getByLabel(`Transfer in P${incoming}`, { exact: true }).click(),
      status,
    );
  };
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/plans/${planId}`);
  await expect(
    page.getByText(
      /Bank 1.2 · Free transfers 2 · Transfers made 1 · Next FT 2/,
    ),
  ).toBeVisible();
  const initial = await read();
  expect(
    initial.gameweeks.map((week) => [
      week.free_transfers_available,
      week.transfers_made,
      week.points_hit,
      week.accounting?.next_free_transfers,
      week.bank,
    ]),
  ).toEqual([
    [2, 1, 0, 2, 1.2],
    [2, 0, 0, 3, 1.2],
    [3, 4, 4, 1, 2],
    [1, 0, 0, 2, 2],
    [2, 0, 0, 3, 2],
  ]);
  const frozen = initial.gameweeks.flatMap((week) => week.decisions);
  await write(() =>
    page.getByRole("button", { name: "Free Hit", exact: true }).click(),
  );
  let current = await read();
  expect(
    current.gameweeks[1].players.map((player) => player.player_id),
  ).toContain(2);
  expect(current.gameweeks[1].decisions).toEqual([]);
  expect(current.gameweeks[1].transfers_made).toBe(0);
  await write(() =>
    page.getByRole("button", { name: "Free Hit", exact: true }).click(),
  );
  expect(
    (await read()).gameweeks[1].players.map((player) => player.player_id),
  ).toContain(102);
  for (const [number, chip] of [
    [8, "Wildcard"],
    [12, "Free Hit"],
    [12, "Wildcard"],
  ] as const) {
    await select(number);
    await write(() =>
      page.getByRole("button", { name: chip, exact: true }).click(),
    );
    await write(() =>
      page.getByRole("button", { name: chip, exact: true }).click(),
    );
  }
  expect((await read()).gameweeks.flatMap((week) => week.decisions)).toEqual(
    frozen,
  );
  await select(11);
  await write(() =>
    page.getByLabel("Make P104 captain", { exact: true }).click(),
  );
  await transfer(102, 2);
  for (const choice of ["remove", "replace"] as const) {
    if (choice === "replace")
      await page.setViewportSize({ width: 390, height: 844 });
    await select(8);
    const accepted = await read();
    await transfer(102, 113, 422);
    await expect(
      page.getByLabel("Transfer P102", { exact: true }),
    ).toBeVisible();
    expect(await read()).toEqual(accepted);
    const panel = page.getByRole("region", { name: "Transfer diagnostics" });
    await expect(panel).toContainText("102");
    await page.screenshot({
      path: info.outputPath(
        `transfers-${choice}-${choice === "remove" ? "desktop" : "mobile"}.png`,
      ),
      fullPage: true,
    });
    const replacement = accepted.gameweeks[3].players.find(
      (player) => player.player_id === 13,
    )!;
    await page
      .getByLabel("Repair transfer GW11: 102 to 2", { exact: true })
      .selectOption(choice === "remove" ? "remove" : replacement.ownership_id!);
    await write(() =>
      page
        .getByRole("button", { name: "Apply transfer repair", exact: true })
        .click(),
    );
    const repair = mutations.at(-1)!;
    expect(repair.expected_revision).toBe(accepted.revision);
    expect(repair.intents).toHaveLength(2);
    expect(repair.intents[0]).toMatchObject({
      kind: "edit_transfer",
      decision_id: accepted.gameweeks[0].decisions[0].decision_id,
      incoming_player_id: 113,
    });
    expect(repair.intents[1]).toMatchObject(
      choice === "remove"
        ? {
            kind: "remove_transfer",
            decision_id: accepted.gameweeks[3].decisions[0].decision_id,
          }
        : {
            kind: "edit_transfer",
            decision_id: accepted.gameweeks[3].decisions[0].decision_id,
            outgoing_player_id: 13,
            outgoing_ownership_id: replacement.ownership_id,
          },
    );
    if (choice === "remove") {
      await transfer(113, 102);
      await select(11);
      await transfer(102, 2);
    }
  }
  current = await read();
  expect(
    current.gameweeks[1].players.find((player) => player.is_captain)?.player_id,
  ).toBe(113);
  expect(
    current.gameweeks[3].players.find((player) => player.is_captain)?.player_id,
  ).toBe(104);
  expect(current.total_points_hit).toBe(4);
  expect(current.decision_errors).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await select(11);
  await expect(page.getByText(/Next FT 1/)).toBeVisible();
  await expect(page.getByText(/Hits taken: 4/)).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("transfers-mobile.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("US2 real API chips across periods, clear/move and frozen FH/WC toggles", async ({
  page,
}, info) => {
  const api = process.env.PLANNER_TEST_API_URL;
  const planId = process.env.PLANNER_TEST_PLAN_ID;
  test.skip(!api || !planId, "Run through the guarded API browser regression");
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS")
      return route.fulfill({ status: 204, headers: HEADERS });
    expect(["GET", "POST"]).toContain(request.method());
    const url = new URL(request.url());
    const response = await route.fetch({
      url: `${api}${url.pathname}${url.search}`,
    });
    expect(response.ok()).toBe(true);
    await route.fulfill({
      response,
      headers: { ...response.headers(), ...HEADERS },
    });
  });
  const read = async (): Promise<PlanResponse> => {
    const response = await page.request.get(`${api}/plans/${planId}`);
    expect(response.ok()).toBe(true);
    return response.json();
  };
  const initial = await read();
  const frozen = initial.gameweeks[1].decisions;
  const preserved = async () => {
    const current = await read();
    expect(
      current.gameweeks.find((week) => week.gameweek_number === 18)!.decisions,
    ).toEqual(frozen);
    expect(current.gameweeks.flatMap((week) => week.decisions)).toHaveLength(1);
  };
  const select = async (number: number) =>
    page.getByLabel(`Gameweek ${number}`, { exact: true }).click();
  const chipButton = (name: string) =>
    page.getByRole("button", { name, exact: true });
  const toggle = async (name: string) => {
    const response = page.waitForResponse(
      (item) =>
        item.url().endsWith("/mutations") && item.request().method() === "POST",
    );
    await chipButton(name).click();
    expect((await response).status()).toBe(200);
    await saved(page);
    await preserved();
  };
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/plans/${planId}`);
  await expect(
    page.getByText("Used before this plan", { exact: true }),
  ).toBeVisible();
  await expect(chipButton("Free Hit")).toBeDisabled();
  await select(18);
  await toggle("Wildcard");
  await expect(chipButton("Wildcard")).toHaveAttribute("aria-pressed", "true");
  await select(17);
  await expect(
    page.getByText("Planned for gameweek 18", { exact: true }),
  ).toBeVisible();
  await expect(chipButton("Wildcard")).toBeDisabled();
  await page.screenshot({
    path: info.outputPath("chips-desktop.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", {
      name: "Move Wildcard from GW18 to GW17",
      exact: true,
    })
    .click();
  await expect(chipButton("Wildcard")).toHaveAttribute("aria-pressed", "true");
  await saved(page);
  await toggle("Wildcard");
  await expect(
    page.getByText("Planned for gameweek 18", { exact: true }),
  ).toHaveCount(0);
  await select(18);
  await toggle("Wildcard");
  await select(20);
  await expect(chipButton("Wildcard")).toBeEnabled();
  await expect(chipButton("Free Hit")).toBeEnabled();
  await toggle("Wildcard");
  await select(18);
  await toggle("Wildcard");
  await select(20);
  await toggle("Wildcard");
  await page
    .getByLabel("Free Hit used before this plan", { exact: true })
    .click();
  await saved(page);
  await select(18);
  await toggle("Free Hit");
  expect(
    (await read()).gameweeks
      .find((week) => week.gameweek_number === 19)!
      .players.map((player) => player.player_id),
  ).toContain(2);
  await toggle("Free Hit");
  expect(
    (await read()).gameweeks
      .find((week) => week.gameweek_number === 19)!
      .players.map((player) => player.player_id),
  ).toContain(102);
  await toggle("Wildcard");
  await toggle("Wildcard");
  await page.setViewportSize({ width: 390, height: 844 });
  await select(19);
  await toggle("Free Hit");
  await select(20);
  await expect(chipButton("Free Hit")).toBeDisabled();
  await expect(
    page.getByText("Free Hit conflicts with gameweek 19", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("chips-mobile.png"),
    fullPage: true,
  });
  await select(19);
  await toggle("Free Hit");
  await select(20);
  await toggle("Free Hit");
  await select(19);
  await expect(chipButton("Free Hit")).toBeDisabled();
  await expect(
    page.getByText("Free Hit conflicts with gameweek 20", { exact: true }),
  ).toBeVisible();
  await select(20);
  await toggle("Free Hit");
  await page.getByLabel("Plan start gameweek", { exact: true }).fill("1");
  await expect(
    page.getByRole("heading", { name: "Starting state at GW1", exact: true }),
  ).toBeVisible();
  await select(1);
  await expect(chipButton("Wildcard")).toBeDisabled();
  await expect(chipButton("Free Hit")).toBeDisabled();
  await toggle("Bench Boost");
  await toggle("Bench Boost");
  await toggle("Triple Captain");
  await toggle("Triple Captain");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Starting state at GW1", exact: true }),
  ).toBeVisible();
  await preserved();
  expect((await read()).gameweeks.every((week) => week.chip === null)).toBe(
    true,
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("foundation loading and uninitialized plans remain read-only", async ({
  page,
}) => {
  const gate = deferred<void>();
  const initial = buildPlannerPlan();
  initial.foundation_state = "legacy_pending";
  initial.starting_state = null;
  initial.initialization = {
    ready: false,
    reason: "Explicit legacy initialization required",
  };
  const server = await installPlanner(page, initial, startingEdit, {
    readGate: gate.promise,
  });
  await page.goto(`/plans/${initial.plan_id}`);
  await expect(
    page.getByText("Loading plan...", { exact: true }),
  ).toBeVisible();
  gate.resolve();
  await expect(
    page.getByRole("status").filter({ hasText: /^Initialization required$/ }),
  ).toBeVisible();
  await expect(
    page.getByText("Explicit legacy initialization required"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Make P4 captain", exact: true }),
  ).toBeDisabled();
  expect(server.requests).toEqual([]);
});
