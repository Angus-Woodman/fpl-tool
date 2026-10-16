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
    const start = page.getByLabel("Plan start gameweek", { exact: true });
    await start.fill("13");
    await start.blur();
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
    const start = page.getByLabel("Plan start gameweek", { exact: true });
    await start.fill(String(target));
    await start.blur();
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
  expect(
    initial.gameweeks[2].players.find((player) => player.player_id === 105)
      ?.current_price,
  ).toBe(8);
  expect(
    initial.gameweeks[2].decisions.find(
      (decision) => decision.incoming_player_id === 105,
    )?.incoming_price_tenths,
  ).toBe(50);
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
    const sourceDecision = accepted.gameweeks[0].decisions[0];
    await page
      .getByLabel("Repair transfer GW11: 102 to 2", { exact: true })
      .selectOption(
        choice === "remove" ? "remove" : `source:${sourceDecision.decision_id}`,
      );
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
            outgoing_player_id: 113,
            outgoing_source_decision_id: sourceDecision.decision_id,
          },
    );
    if (choice === "replace") {
      expect(repair.intents[1]).not.toHaveProperty("outgoing_ownership_id");
      const repaired = await read();
      const acquisition = repaired.gameweeks[0].decisions[0];
      const downstream = repaired.gameweeks[3].decisions[0];
      expect(acquisition.decision_id).toBe(sourceDecision.decision_id);
      expect(acquisition.incoming_ownership_id).not.toBe(
        sourceDecision.incoming_ownership_id,
      );
      expect(downstream.decision_id).toBe(
        accepted.gameweeks[3].decisions[0].decision_id,
      );
      expect(downstream.outgoing_player_id).toBe(113);
      expect(downstream.outgoing_ownership_id).toBe(
        acquisition.incoming_ownership_id,
      );
      expect(acquisition.incoming_price_tenths).toBe(52);
      expect(downstream.outgoing_market_tenths).toBe(52);
      expect(downstream.incoming_price_tenths).toBe(54);
      expect(downstream.incoming_ownership_id).toBe(
        accepted.gameweeks[3].decisions[0].incoming_ownership_id,
      );
      expect(repaired.gameweeks[2].decisions).toEqual(
        accepted.gameweeks[2].decisions,
      );
      expect(repaired.gameweeks[1].decisions).toEqual([]);
      expect(repaired.gameweeks.flatMap((week) => week.decisions)).toHaveLength(
        6,
      );
    }
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
  const reopened = await read();
  expect(reopened.gameweeks[3].decisions[0].outgoing_ownership_id).toBe(
    reopened.gameweeks[0].decisions[0].incoming_ownership_id,
  );
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

test("US4 real API pricing inspection, correction shortfall, repair and rebased basis", async ({
  page,
}, info) => {
  test.setTimeout(120_000);
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
    expect(response.status()).toBe(200);
    await route.fulfill({
      response,
      headers: { ...response.headers(), ...HEADERS },
    });
  });
  const read = async (): Promise<PlanResponse> =>
    (await page.request.get(`${api}/plans/${planId}`)).json();
  const select = async (number: number) =>
    page.getByLabel(`Gameweek ${number}`, { exact: true }).click();
  const write = async (action: () => Promise<unknown>) => {
    const response = page.waitForResponse(
      (item) =>
        item.url().endsWith("/mutations") && item.request().method() === "POST",
    );
    await action();
    expect((await response).status()).toBe(200);
    await saved(page);
  };
  const noOverflow = async () =>
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  const details = (outgoing: string, incoming: string) =>
    page.getByRole("region", {
      name: `Transfer price details: ${outgoing} to ${incoming}`,
    });
  const resolution = () =>
    page.getByRole("region", { name: "Financial resolution" });

  // Saved M54/P62 quotes, then live prices moved to 5.6/6.0 before this load.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/plans/${planId}`);
  const quote = (await read()).gameweeks[0].decisions[0];
  expect(quote).toMatchObject({
    outgoing_market_tenths: 54,
    incoming_price_tenths: 62,
    selling_price_tenths: 52,
    purchase_price_tenths: 50,
    basis_confirmation: "assumed",
    outgoing_live_market_tenths: 56,
    incoming_live_price_tenths: 60,
  });
  const inspection = details("P2", "P102");
  await expect(inspection).toContainText("Purchase basis £5.0m · Estimated");
  await expect(inspection).toContainText("Saved market assumption £5.4m");
  await expect(inspection).toContainText("Selling price used £5.2m");
  await expect(inspection).toContainText("Acquisition price paid £6.2m");
  await expect(inspection).toContainText(
    "Latest market (not used): P2 £5.6m · P102 £6.0m",
  );
  await expect(
    page.getByText(/Market refreshes do not reprice saved transfers/),
  ).toBeVisible();
  await expect(page.getByText(/Bank 0\.0 ·/)).toBeVisible();
  await expect(
    page.getByText("Estimated bases", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Requires resolution", { exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("pricing-inspection-desktop.png"),
    fullPage: true,
  });

  // Provenance correction is accepted and exposes a £0.1m shortfall in GW8.
  const before = await read();
  await write(async () => {
    const input = page.getByLabel("P2 purchase price", { exact: true });
    await input.fill("4.8");
    await input.press("Tab");
  });
  expect(mutations.at(-1)!.intents).toEqual([
    {
      kind: "correct_purchase_price",
      ownership_id: before.starting_state!.players.find(
        (player) => player.player_id === 2,
      )!.ownership_id,
      price_tenths: 48,
    },
  ]);
  const corrected = await read();
  expect(corrected.gameweeks[0].decisions[0]).toMatchObject({
    decision_id: quote.decision_id,
    outgoing_market_tenths: 54,
    incoming_price_tenths: 62,
    selling_price_tenths: 51,
    purchase_price_tenths: 48,
    basis_confirmation: "user_confirmed",
  });
  expect(corrected.gameweeks[0].accounting!.closing_bank_tenths).toBe(-1);
  expect(corrected.financial_status).toMatchObject({
    requires_resolution: true,
    earliest_shortfall_gameweek: 8,
    earliest_shortfall_tenths: 1,
  });
  await expect(inspection).toContainText("Purchase basis £4.8m · Confirmed");
  await expect(inspection).toContainText("Selling price used £5.1m");
  await expect(inspection).toContainText("Acquisition price paid £6.2m");
  await expect(
    page.getByText("Requires resolution", { exact: true }),
  ).toBeVisible();
  await expect(resolution()).toContainText("Shortfall £0.1m in GW8");
  await expect(resolution()).toContainText(
    "Dependent gameweeks: GW8, GW9, GW10, GW11",
  );
  await expect(resolution()).toContainText(
    "Saved does not mean financially valid",
  );
  await expect(page.getByText(/Bank Shortfall £0\.1m/)).toBeVisible();
  await expect(page.getByText(/Bank -0\.1/)).toHaveCount(0);
  await expect(page.getByLabel("Transfer P102", { exact: true })).toBeVisible();
  await page.screenshot({
    path: info.outputPath("pricing-shortfall-desktop.png"),
    fullPage: true,
  });

  // The flag survives reload (replay-only) and navigates to the earliest GW.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(resolution()).toContainText("Shortfall £0.1m in GW8");
  await select(11);
  await page.getByRole("button", { name: "Go to GW8", exact: true }).click();
  await expect(page.getByLabel("Gameweek 8", { exact: true })).toHaveAttribute(
    "aria-current",
    "true",
  );
  await noOverflow();
  await page.screenshot({
    path: info.outputPath("pricing-shortfall-mobile.png"),
    fullPage: true,
  });

  // Explicit edit of the completed GW8 transfer recaptures only that record.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByLabel("Transfer P102", { exact: true }).click();
  await write(() =>
    page.getByLabel("Transfer in P113", { exact: true }).click(),
  );
  expect(mutations.at(-1)!.intents).toEqual([
    {
      kind: "edit_transfer",
      decision_id: quote.decision_id,
      incoming_player_id: 113,
    },
  ]);
  const repaired = await read();
  expect(repaired.gameweeks[0].decisions[0]).toMatchObject({
    decision_id: quote.decision_id,
    outgoing_player_id: 2,
    incoming_player_id: 113,
    outgoing_market_tenths: 56,
    incoming_price_tenths: 50,
    selling_price_tenths: 52,
    purchase_price_tenths: 48,
  });
  expect(repaired.gameweeks[0].accounting!.closing_bank_tenths).toBe(12);
  expect(repaired.financial_status).toMatchObject({
    requires_resolution: false,
    earliest_shortfall_gameweek: null,
  });
  await expect(
    page.getByText("Requires resolution", { exact: true }),
  ).toHaveCount(0);
  await expect(resolution()).toHaveCount(0);
  await expect(page.getByText(/Bank 1\.2 ·/)).toBeVisible();
  await page.reload();
  await expect(resolution()).toHaveCount(0);
  await expect(details("P2", "P113")).toContainText(
    "Saved market assumption £5.6m",
  );

  // Rebase to GW9, correct the carried planned acquisition, then transfer it.
  await write(async () => {
    const input = page.getByLabel("Plan start gameweek", { exact: true });
    await input.fill("9");
    await input.blur();
  });
  await select(9);
  const carried = (await read()).starting_state!;
  expect(carried.bank_tenths).toBe(12);
  expect(
    carried.players.find((player) => player.player_id === 113),
  ).toMatchObject({
    purchase_price_tenths: 50,
    provenance: { basis_kind: "planned_acquisition", confirmation: null },
  });
  await write(async () => {
    const input = page.getByLabel("P113 purchase price", { exact: true });
    await input.fill("4.8");
    await input.press("Tab");
  });
  const rebased = (await read()).starting_state!;
  expect(rebased.bank_tenths).toBe(12);
  expect(
    rebased.players.find((player) => player.player_id === 113),
  ).toMatchObject({
    purchase_price_tenths: 48,
    provenance: {
      original_price_tenths: 50,
      basis_kind: "planned_acquisition",
    },
  });
  await page.getByLabel("Transfer P113", { exact: true }).click();
  await write(() =>
    page.getByLabel("Transfer in P102", { exact: true }).click(),
  );
  const final = await read();
  expect(final.gameweeks[0].decisions[0]).toMatchObject({
    outgoing_player_id: 113,
    incoming_player_id: 102,
    outgoing_market_tenths: 50,
    incoming_price_tenths: 60,
    selling_price_tenths: 49,
    purchase_price_tenths: 48,
    basis_kind: "planned_acquisition",
  });
  expect(final.gameweeks[0].accounting!.closing_bank_tenths).toBe(1);
  expect(final.financial_status.requires_resolution).toBe(false);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(details("P113", "P102")).toContainText(
    "Purchase basis £4.8m · Planned acquisition",
  );
  await expect(details("P113", "P102")).toContainText(
    "Selling price used £4.9m",
  );
  await expect(page.getByText(/Bank 0\.1 ·/)).toBeVisible();
  await noOverflow();
  await page.screenshot({
    path: info.outputPath("pricing-rebased-mobile.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("US5 real API persistence, failure, reconciliation, conflict, rejection and departure", async ({
  page,
}, info) => {
  test.setTimeout(150_000);
  const api = process.env.PLANNER_TEST_API_URL;
  const planId = process.env.PLANNER_TEST_PLAN_ID;
  const faultFile = process.env.PLANNER_FAULT_FILE;
  test.skip(
    !api || !planId || !faultFile,
    "Run through the guarded API browser regression",
  );
  const errors: string[] = [];
  const posts: {
    mutation_id: string;
    expected_revision: number;
    intents: PlanIntent[];
  }[] = [];
  const responses: number[] = [];
  const dialogs: { type: string; message: string }[] = [];
  let hold: Promise<void> | null = null;
  let dropNext = false;
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS")
      return route.fulfill({ status: 204, headers: HEADERS });
    expect(["GET", "POST"]).toContain(request.method());
    const post = request.method() === "POST";
    if (post) posts.push(request.postDataJSON());
    const gate = post ? hold : null;
    if (gate) {
      hold = null;
      await gate;
    }
    const url = new URL(request.url());
    const response = await route.fetch({
      url: `${api}${url.pathname}${url.search}`,
    });
    if (post) responses.push(response.status());
    expect([200, 404, 409, 422, 503]).toContain(response.status());
    if (post && dropNext) {
      dropNext = false;
      return route.abort("failed");
    }
    // The final navigation can dispose an in-flight forwarded response.
    await route
      .fulfill({ response, headers: { ...response.headers(), ...HEADERS } })
      .catch((error: Error) => {
        if (!/disposed|closed/i.test(error.message)) throw error;
      });
  });
  const fs = await import("node:fs");
  const read = async (): Promise<PlanResponse> =>
    (await page.request.get(`${api}/plans/${planId}`)).json();
  const otherTab = async (name: string) => {
    const current = await read();
    const response = await page.request.post(
      `${api}/plans/${planId}/mutations`,
      {
        data: {
          mutation_id: crypto.randomUUID(),
          expected_revision: current.revision,
          intents: [{ kind: "rename_plan", name }],
        },
      },
    );
    expect(response.status()).toBe(200);
  };
  const select = async (number: number) =>
    page.getByLabel(`Gameweek ${number}`, { exact: true }).click();
  const status = (text: string) =>
    page.getByRole("status").filter({ hasText: new RegExp(`^${text}$`) });
  const roles = async (number: number) => {
    const week = (await read()).gameweeks.find(
      (item) => item.gameweek_number === number,
    )!;
    return [
      week.players.find((player) => player.is_captain)?.player_id,
      week.players.find((player) => player.is_vice_captain)?.player_id,
    ];
  };
  const badge = (name: string) =>
    page
      .locator("article")
      .filter({ has: page.getByText(name, { exact: true }) })
      .locator("span.rounded-full");
  const noSaveButton = async () => {
    await expect(
      page.getByRole("button", { name: /save gameweek/i }),
    ).toHaveCount(0);
    await expect(page.getByText(/save gameweek/i)).toHaveCount(0);
  };
  fs.rmSync(faultFile!, { force: true });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/plans/${planId}`);
  await select(9);
  await noSaveButton();
  expect(await roles(9)).toEqual([2, 3]);

  // A: delayed captain C, vice D, immediate gameweek switch, then reload.
  let release!: () => void;
  hold = new Promise<void>((resolve) => (release = resolve));
  await page.getByLabel("Make P4 captain", { exact: true }).click();
  await page.getByLabel("Make P5 vice-captain", { exact: true }).click();
  await select(10);
  await expect(status("Saving...")).toBeVisible();
  expect(posts).toHaveLength(1);
  expect(await roles(9)).toEqual([2, 3]);
  release();
  await expect(status("Saved")).toBeVisible();
  expect(posts.map((post) => [post.expected_revision, post.intents])).toEqual([
    [0, [{ kind: "change_captain", gameweek_number: 9, player_id: 4 }]],
    [1, [{ kind: "change_vice_captain", gameweek_number: 9, player_id: 5 }]],
  ]);
  expect(posts[0].mutation_id).not.toBe(posts[1].mutation_id);
  expect(await roles(9)).toEqual([4, 5]);
  expect(await roles(10)).toEqual([2, 3]);
  await select(9);
  await expect(badge("P4")).toHaveText("C");
  await expect(badge("P5")).toHaveText("VC");
  await page.reload();
  await select(9);
  await expect(badge("P4")).toHaveText("C");
  await expect(badge("P5")).toHaveText("VC");
  await page.screenshot({
    path: info.outputPath("persistence-saved-desktop.png"),
    fullPage: true,
  });

  // B: canonical write fails after the durable receipt; retry the same ID.
  fs.writeFileSync(faultFile!, "fail");
  const beforeFailure = posts.length;
  await page.getByLabel("Make P6 captain", { exact: true }).click();
  await expect(status("Not saved")).toBeVisible();
  expect(responses.at(-1)).toBe(503);
  await expect(badge("P6")).toHaveText("C");
  expect((await read()).revision).toBe(2);
  expect(await roles(9)).toEqual([4, 5]);
  await expect(
    page.getByLabel("Make P7 captain", { exact: true }),
  ).toBeDisabled();
  await select(10);
  await select(9);
  await expect(status("Not saved")).toBeVisible();
  await expect(badge("P6")).toHaveText("C");
  await page.screenshot({
    path: info.outputPath("persistence-not-saved-desktop.png"),
    fullPage: true,
  });
  fs.rmSync(faultFile!, { force: true });
  await page
    .getByRole("button", { name: "Retry Same Edit", exact: true })
    .click();
  await expect(status("Saved")).toBeVisible();
  expect(posts.slice(beforeFailure)).toHaveLength(2);
  expect(posts[beforeFailure + 1]).toEqual(posts[beforeFailure]);
  expect((await read()).revision).toBe(3);
  expect(await roles(9)).toEqual([6, 5]);

  // C: success is lost, another tab advances the plan, then reconcile by ID.
  dropNext = true;
  const beforeLost = posts.length;
  await page.getByLabel("Make P7 captain", { exact: true }).click();
  await expect(status("Not saved")).toBeVisible();
  expect((await read()).revision).toBe(4);
  await otherTab("Other tab");
  await page
    .getByRole("button", { name: "Check Save Status", exact: true })
    .click();
  await expect(status("Saved")).toBeVisible();
  expect(posts).toHaveLength(beforeLost + 1);
  await expect(
    page.getByRole("heading", { name: "Other tab", exact: true }),
  ).toBeVisible();
  await expect(badge("P7")).toHaveText("C");
  expect((await read()).revision).toBe(5);

  // D: stale revision conflict, explicit revalidation with a new ID.
  await otherTab("Second tab");
  const beforeStale = posts.length;
  await page.getByLabel("Make P8 captain", { exact: true }).click();
  await expect(status("Needs reconciliation")).toBeVisible();
  expect(responses.at(-1)).toBe(409);
  await expect(
    page.getByRole("heading", { name: "Second tab", exact: true }),
  ).toBeVisible();
  expect((await read()).revision).toBe(6);
  await page
    .getByRole("button", { name: "Revalidate With Current Data", exact: true })
    .click();
  await expect(status("Saved")).toBeVisible();
  const [stale, retried] = posts.slice(beforeStale);
  expect(retried.mutation_id).not.toBe(stale.mutation_id);
  expect([stale.expected_revision, retried.expected_revision]).toEqual([5, 6]);
  expect(retried.intents).toEqual(stale.intents);
  expect((await read()).revision).toBe(7);
  expect(await roles(9)).toEqual([8, 5]);

  // E: a new rule violation is rejected, shown as saved, and leaves retry state intact.
  await page.getByLabel("Transfer P2", { exact: true }).click();
  await page.getByLabel("Transfer in P102", { exact: true }).click();
  await expect(
    page.locator("p[role=alert]").filter({ hasText: /shortfall/i }),
  ).toBeVisible();
  expect(responses.at(-1)).toBe(422);
  await expect(status("Saved")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Retry Same Edit" }),
  ).toHaveCount(0);
  expect((await read()).revision).toBe(7);
  expect((await read()).gameweeks.flatMap((week) => week.decisions)).toEqual(
    [],
  );
  expect(await roles(9)).toEqual([8, 5]);
  await page.getByLabel("Make P9 vice-captain", { exact: true }).click();
  await expect(status("Saved")).toBeVisible();
  expect((await read()).revision).toBe(8);
  expect(await roles(9)).toEqual([8, 9]);

  // F: departure is guarded only while the latest edit is unsaved.
  page.on("dialog", async (dialog) => {
    dialogs.push({ type: dialog.type(), message: dialog.message() });
    await dialog.dismiss();
  });
  let unblock!: () => void;
  hold = new Promise<void>((resolve) => (unblock = resolve));
  await page.getByLabel("Make P10 captain", { exact: true }).click();
  await expect(status("Saving...")).toBeVisible();
  expect(
    await page.evaluate(() => {
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    }),
  ).toBe(true);
  const nav = page.getByRole("navigation", { name: "Primary" });
  await nav.getByRole("link", { name: "Players", exact: true }).click();
  await expect.poll(() => dialogs.length).toBe(1);
  expect(dialogs[0].type).toBe("confirm");
  expect(dialogs[0].message).toMatch(/not saved/i);
  await expect(page).toHaveURL(new RegExp(`/plans/${planId}$`));
  unblock();
  await expect(status("Saved")).toBeVisible();
  expect(
    await page.evaluate(() => {
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    }),
  ).toBe(false);
  expect((await read()).revision).toBe(9);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(badge("P10")).toHaveText("C");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("persistence-saved-mobile.png"),
    fullPage: true,
  });
  await nav.getByRole("link", { name: "Players", exact: true }).click();
  await expect(page).toHaveURL(/\/players$/);
  expect(dialogs).toHaveLength(1);
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
  const first = page.getByLabel("Plan start gameweek", { exact: true });
  await first.fill("1");
  await first.blur();
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

test("US6 real API rearrangement parity between My Team and the Planner", async ({
  page,
}, info) => {
  test.setTimeout(150_000);
  const api = process.env.PLANNER_TEST_API_URL;
  const planId = process.env.PLANNER_TEST_PLAN_ID;
  test.skip(!api || !planId, "Run through the guarded API browser regression");
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const cors = {
    ...HEADERS,
    "access-control-allow-methods": "GET,POST,PUT,OPTIONS",
  };
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS")
      return route.fulfill({ status: 204, headers: cors });
    const url = new URL(request.url());
    const response = await route.fetch({
      url: `${api}${url.pathname}${url.search}`,
    });
    await route
      .fulfill({ response, headers: { ...response.headers(), ...cors } })
      .catch((error: Error) => {
        if (!/disposed|closed/i.test(error.message)) throw error;
      });
  });

  type Roles = [boolean, number | null, boolean, boolean];
  const names = Array.from({ length: 15 }, (_, index) => `P${index + 1}`);
  const select = (name: string) =>
    page.getByRole("button", { name: `Select ${name}`, exact: true });
  const states = async (): Promise<Record<string, string>> =>
    page.$$eval("article[data-selection-state]", (cards) =>
      Object.fromEntries(
        cards.map((card) => [
          card.querySelector("p.font-semibold")!.textContent!.trim(),
          card.getAttribute("data-selection-state")!,
        ]),
      ),
    );
  const targetsOf = async (name: string): Promise<string[]> => {
    await select(name).click();
    const marked = await states();
    expect(marked[name]).toBe("selected");
    await select(name).click();
    expect(Object.values(await states()).every((s) => s === "idle")).toBe(true);
    return Object.entries(marked)
      .filter(([, value]) => value === "target")
      .map(([key]) => key)
      .sort();
  };
  const allTargets = async (): Promise<Record<string, string[]>> => {
    const found: Record<string, string[]> = {};
    for (const name of names) found[name] = await targetsOf(name);
    return found;
  };
  const benchOrder = async (): Promise<string[]> =>
    page.evaluate(() => {
      const heading = Array.from(document.querySelectorAll("h3")).find(
        (item) => item.textContent?.trim() === "Bench",
      )!;
      return Array.from(
        heading.parentElement!.querySelectorAll("article p.font-semibold"),
      ).map((item) => item.textContent!.trim());
    });
  const confirmation = page.getByTestId("swap-confirmation");
  const myTeamLineup = async (): Promise<Record<string, Roles>> => {
    const body = await (await page.request.get(`${api}/my-team`)).json();
    return Object.fromEntries(
      body.players.map(
        (player: {
          web_name: string;
          is_starting: boolean;
          bench_order: number | null;
          is_captain: boolean;
          is_vice_captain: boolean;
        }): [string, Roles] => [
          player.web_name,
          [
            player.is_starting,
            player.bench_order,
            player.is_captain,
            player.is_vice_captain,
          ],
        ],
      ),
    );
  };
  const planLineup = async (number: number): Promise<Record<string, Roles>> => {
    const plan: PlanResponse = await (
      await page.request.get(`${api}/plans/${planId}`)
    ).json();
    const week = plan.gameweeks.find(
      (item) => item.gameweek_number === number,
    )!;
    return Object.fromEntries(
      week.players.map((player): [string, Roles] => [
        player.web_name,
        [
          player.is_starting,
          player.bench_order,
          player.is_captain,
          player.is_vice_captain,
        ],
      ]),
    );
  };
  const initial = await myTeamLineup();
  expect(await planLineup(9)).toEqual(initial);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/my-team");
  await expect(select("P1")).toBeVisible();
  const mine = await allTargets();
  await page.screenshot({
    path: info.outputPath("us6-my-team-before.png"),
    fullPage: true,
  });

  await page.goto(`/plans/${planId}`);
  await page.getByLabel("Gameweek 9", { exact: true }).click();
  await expect(select("P1")).toBeVisible();
  const planned = await allTargets();
  await page.screenshot({
    path: info.outputPath("us6-planner-before.png"),
    fullPage: true,
  });

  expect(planned).toEqual(mine);
  expect(mine.P1).toEqual(["P12"]);
  expect(mine.P12).toEqual(["P1"]);
  const bench = new Set(["P12", "P13", "P14", "P15"]);
  for (const name of names.slice(0, 11))
    expect(mine[name].every((target) => bench.has(target))).toBe(true);
  expect(mine.P13).toEqual(expect.arrayContaining(["P14", "P15"]));
  expect(mine.P13).not.toContain("P12");
  expect(mine.P14).not.toContain("P12");
  expect(mine.P15).not.toContain("P12");
  expect(await benchOrder()).toEqual(["P12", "P13", "P14", "P15"]);

  await select("P3").click();
  await select("P4").click();
  await expect(select("P4")).toHaveAttribute("aria-pressed", "true");
  await expect(select("P3")).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("button", { name: "Clear selection" }).click();
  expect(Object.values(await states()).every((s) => s === "idle")).toBe(true);
  expect(await planLineup(9)).toEqual(initial);

  const swapOn = async (first: string, second: string, message: string) => {
    await select(first).click();
    await select(second).click();
    await expect(confirmation).toHaveText(message);
  };
  const saved = page.getByRole("status").filter({ hasText: /^Saved$/ });
  await swapOn("P2", "P14", "Swapped P2 with P14.");
  await expect(saved).toBeVisible();
  await expect.poll(async () => (await planLineup(9)).P14[2]).toBe(true);
  await swapOn("P13", "P15", "Swapped bench order of P13 and P15.");
  await expect.poll(async () => (await planLineup(9)).P15[1]).toBe(2);
  expect(await benchOrder()).toEqual(["P12", "P15", "P2", "P13"]);
  expect(await targetsOf("P12")).toEqual(["P1"]);
  await page.screenshot({
    path: info.outputPath("us6-planner-after.png"),
    fullPage: true,
  });

  await page.goto("/my-team");
  await expect(select("P1")).toBeVisible();
  await swapOn("P2", "P14", "Swapped P2 with P14.");
  await expect.poll(async () => (await myTeamLineup()).P14[2]).toBe(true);
  await swapOn("P13", "P15", "Swapped bench order of P13 and P15.");
  await expect.poll(async () => (await myTeamLineup()).P15[1]).toBe(2);
  expect(await benchOrder()).toEqual(["P12", "P15", "P2", "P13"]);
  expect(await targetsOf("P12")).toEqual(["P1"]);
  await page.screenshot({
    path: info.outputPath("us6-my-team-after.png"),
    fullPage: true,
  });

  const mineAfter = await myTeamLineup();
  expect(mineAfter).toEqual(await planLineup(9));
  expect(mineAfter.P14).toEqual([true, null, true, false]);
  expect(mineAfter.P2).toEqual([false, 3, false, false]);
  expect(mineAfter.P3).toEqual([true, null, false, true]);
  expect(await planLineup(8)).toEqual(initial);
  expect(await planLineup(10)).toEqual(initial);

  await page.goto(`/plans/${planId}`);
  await page.getByLabel("Gameweek 9", { exact: true }).click();
  await expect(select("P1")).toBeVisible();
  expect(await benchOrder()).toEqual(["P12", "P15", "P2", "P13"]);
  await page.getByLabel("Gameweek 10", { exact: true }).click();
  expect(await benchOrder()).toEqual(["P12", "P13", "P14", "P15"]);

  await page.setViewportSize({ width: 390, height: 844 });
  const noOverflow = () =>
    page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
  await select("P13").click();
  expect((await states()).P14).toBe("target");
  expect(await noOverflow()).toBe(true);
  await page.screenshot({
    path: info.outputPath("us6-planner-mobile-selected.png"),
    fullPage: true,
  });
  await page.goto("/my-team");
  await expect(select("P1")).toBeVisible();
  await select("P13").click();
  expect((await states()).P14).toBe("target");
  expect(await noOverflow()).toBe(true);
  await page.screenshot({
    path: info.outputPath("us6-my-team-mobile-selected.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("Phase 9 rendered states at 1440x900 and 390x844: layout, keyboard, tap targets, console and requests", async ({
  page,
}, info) => {
  test.setTimeout(150_000);
  const longName = "Extraordinarily-Long-Surname Mc'Fadyen-Smythe";
  const plan = buildPlannerPlan(12, 14);
  plan.name =
    "A very long plan name that must wrap instead of clipping at narrow widths 2026/27";
  for (const week of plan.gameweeks)
    for (const player of week.players)
      if ([4, 12].includes(player.player_id)) player.web_name = longName;
  plan.gameweeks[1].chip = "WILDCARD";
  plan.gameweeks[1].chip_availability.WILDCARD = {
    state: "planned_here",
    reason: null,
    conflicting_gameweek: null,
  };
  plan.gameweeks[1].chip_availability.FREE_HIT = {
    state: "planned_elsewhere",
    reason: "Planned for gameweek 12",
    conflicting_gameweek: 12,
  };
  plan.gameweeks[1].chip_availability.BENCH_BOOST = {
    state: "used_before",
    reason: "Used before this plan",
    conflicting_gameweek: null,
  };

  const consoleErrors: string[] = [];
  const requests: string[] = [];
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  let mode: "ok" | "error" | "missing" | "slow" | "write-fails" = "ok";
  const held: (() => void)[] = [];
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "OPTIONS")
      return route.fulfill({ status: 204, headers: HEADERS });
    requests.push(`${request.method()} ${url.pathname}`);
    if (request.method() === "POST") {
      if (mode === "write-fails") return route.abort("failed");
      return route.fulfill({
        status: 422,
        json: { detail: { code: "x", message: "unexpected" } },
        headers: HEADERS,
      });
    }
    if (mode === "error")
      return route.fulfill({
        status: 500,
        json: { detail: "boom" },
        headers: HEADERS,
      });
    if (mode === "missing")
      return route.fulfill({
        status: 404,
        json: { detail: "missing" },
        headers: HEADERS,
      });
    if (mode === "slow")
      await new Promise<void>((resolve) => held.push(resolve));
    return route.fulfill({ json: plan, headers: HEADERS });
  });

  const overflow = () =>
    page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
  const smallTargets = async () =>
    page.evaluate(() =>
      Array.from(document.querySelectorAll("button, a[href], input, select"))
        .filter((el) => {
          const box = el.getBoundingClientRect();
          const style = getComputedStyle(el);
          return (
            box.width > 0 &&
            style.visibility !== "hidden" &&
            !(el as HTMLButtonElement).disabled &&
            (box.height < 24 || box.width < 24) &&
            !(
              el instanceof HTMLInputElement &&
              ["checkbox", "radio"].includes(el.type)
            )
          );
        })
        .map(
          (el) =>
            `${el.tagName} ${el.getAttribute("aria-label") ?? el.textContent?.trim()}`,
        ),
    );
  const status = page.getByRole("status");

  for (const viewport of [
    { name: "desktop", width: 1440, height: 900 },
    { name: "mobile", width: 390, height: 844 },
  ]) {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    const shot = (name: string) =>
      page.screenshot({
        path: info.outputPath(`p9-${viewport.name}-${name}.png`),
        fullPage: true,
      });

    mode = "slow";
    const before = requests.length;
    const loading = page.goto(`/plans/${plan.plan_id}`);
    await expect(
      page.getByText("Loading plan...", { exact: true }),
    ).toBeVisible();
    await shot("loading");
    await expect.poll(() => held.length).toBeGreaterThan(0);
    mode = "ok";
    held.splice(0).forEach((resolve) => resolve());
    await loading;
    mode = "ok";
    await expect(
      page.getByRole("button", { name: "Select P1", exact: true }),
    ).toBeVisible();
    expect(
      requests.slice(before).filter((r) => r.startsWith("GET /plans/")).length,
    ).toBeLessThanOrEqual(2);

    await page.getByLabel("Gameweek 13", { exact: true }).click();
    await expect(page.getByRole("heading", { name: plan.name })).toBeVisible();
    expect(await overflow()).toBe(true);
    await shot("plan-chips-long-names");
    expect(await smallTargets()).toEqual([]);

    const select = page
      .getByRole("button", { name: `Select ${longName}`, exact: true })
      .first();
    await select.scrollIntoViewIfNeeded();
    await select.focus();
    await expect(select).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(select).toHaveAttribute("aria-pressed", "true");
    await expect(
      page.getByRole("button", { name: "Clear selection" }),
    ).toBeVisible();
    expect(await overflow()).toBe(true);
    await shot("selected-long-name");
    await page.keyboard.press("Enter");
    await expect(select).toHaveAttribute("aria-pressed", "false");

    mode = "write-fails";
    await page.getByLabel("Make P5 captain", { exact: true }).click();
    await expect(status.filter({ hasText: /^Not saved$/ })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Retry Same Edit" }),
    ).toBeVisible();
    expect(await overflow()).toBe(true);
    await shot("not-saved");
    mode = "ok";

    for (const [state, text] of [
      ["error", /boom|Failed|500|error/i],
      ["missing", /no longer exists/i],
    ] as const) {
      mode = state;
      await page.goto(`/plans/${plan.plan_id}`);
      await expect(page.getByText(text).first()).toBeVisible();
      expect(await overflow()).toBe(true);
      await shot(state);
    }
    mode = "ok";
  }
  expect(
    consoleErrors.filter(
      (entry) =>
        !/Failed to load resource|net::ERR|status of (404|500)/i.test(entry),
    ),
  ).toEqual([]);
});
