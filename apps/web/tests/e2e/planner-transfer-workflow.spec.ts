import fs from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import type { PlanResponse } from "../../src/lib/api";
import {
  buildFinancialBlockedCandidate,
  buildPlannerExplorerResponse,
  buildPlannerPreviewResponse,
  buildStructuralBlockedPreview,
  EXPLORER_RUN_ID,
} from "../fixtures/planner-explorer";
import { buildPlannerPlan } from "../fixtures/planner";

test.use({ baseURL: process.env.PLANNER_BASE_URL ?? "http://127.0.0.1:3000" });

const HEADERS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "content-type",
  "access-control-allow-methods": "GET,POST,OPTIONS",
};

const GAMEWEEK = 12;
const OUTGOING_ID = 6;

function explorerPayload(planId: number, planName: string) {
  const shift = (gameweeks: number[]) =>
    gameweeks.map((gameweek) => gameweek + (GAMEWEEK - 9));
  const payload = buildPlannerExplorerResponse();
  payload.planning_context = {
    plan_id: planId,
    gameweek: GAMEWEEK,
    revision: 0,
  };
  payload.plan = {
    ...payload.plan,
    plan_id: planId,
    name: planName,
    gameweek: GAMEWEEK,
    start_gameweek: GAMEWEEK,
    end_gameweek: GAMEWEEK + 2,
  };
  payload.projection.horizons = payload.projection.horizons.map((info) => ({
    ...info,
    requested_gameweeks: shift(info.requested_gameweeks),
    evaluated_gameweeks: shift(info.evaluated_gameweeks),
    saved_plan_gameweeks: shift(info.saved_plan_gameweeks),
    assumed_gameweeks: shift(info.assumed_gameweeks),
  }));
  const blocked = payload.candidates.find(
    (candidate) => candidate.state === "blocked_by_later_decision",
  );
  if (blocked?.conflict) {
    blocked.conflict.gameweek = GAMEWEEK + 2;
    blocked.valid_through_gameweek = GAMEWEEK + 1;
  }
  return payload;
}

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test(`US1 Planner gameweek player opens the Planner-aware Explorer list at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));

    const plan = buildPlannerPlan(GAMEWEEK, GAMEWEEK + 2);
    plan.name = "Explorer journey";
    const explorerUrls: URL[] = [];
    const methods: string[] = [];

    await page.route("http://127.0.0.1:8000/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (request.method() === "OPTIONS") {
        return route.fulfill({ status: 204, headers: HEADERS });
      }
      methods.push(request.method());
      if (url.pathname === `/plans/${plan.plan_id}`) {
        return route.fulfill({ json: plan, headers: HEADERS });
      }
      if (
        url.pathname ===
        `/plans/${plan.plan_id}/gameweeks/${GAMEWEEK}/transfers/${OUTGOING_ID}`
      ) {
        explorerUrls.push(url);
        return route.fulfill({
          json: explorerPayload(plan.plan_id, plan.name),
          headers: HEADERS,
        });
      }
      return route.fulfill({
        status: 404,
        json: { detail: { code: "unexpected", message: url.pathname } },
        headers: HEADERS,
      });
    });

    await page.goto(`/plans/${plan.plan_id}`);
    await expect(page.getByLabel("Gameweek 12", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Explore transfers for this gameweek" }),
    ).toHaveAttribute("href", `/transfers?plan=${plan.plan_id}&gw=${GAMEWEEK}`);

    await page
      .locator(
        `a[href="/transfers?plan=${plan.plan_id}&gw=${GAMEWEEK}&out=${OUTGOING_ID}"]`,
      )
      .click();

    // The list opens for the clicked player without choosing plan, gameweek
    // or player again.
    const banner = page.getByRole("region", { name: "Planner context" });
    await expect(banner).toContainText("Planner mode");
    await expect(banner).toContainText("Explorer journey");
    await expect(banner).toContainText("Gameweek 12");
    await expect(
      banner.getByRole("link", { name: "Back to plan" }),
    ).toHaveAttribute("href", `/plans/${plan.plan_id}?gw=${GAMEWEEK}`);
    await expect(page.getByText(/component_v3/)).toBeVisible();
    await expect(page).toHaveURL(
      new RegExp(`out=${OUTGOING_ID}&h=5&run=${EXPLORER_RUN_ID}$`),
    );

    for (const label of ["GW12", "GW12-14", "GW12-16"]) {
      await expect(
        page.getByRole("columnheader", {
          name: new RegExp(`Best-XI gain ${label}$`),
        }),
      ).toBeVisible();
    }
    const coverage = page.getByRole("region", { name: "Projection coverage" });
    await expect(coverage).toContainText("GW12-16 evaluated");
    await expect(coverage).toContainText("assumed continuation GW14-16");

    const table = page.getByRole("table", { name: "Replacement candidates" });
    await expect(table.locator("tr[data-state='available']")).toHaveCount(1);
    await expect(table.locator("tr[data-state='unavailable']")).toContainText(
      /Unavailable: .*money/,
    );
    await expect(
      table.locator("tr[data-state='blocked_by_later_decision']"),
    ).toContainText("Blocked by GW14 planned transfer");
    await expect(
      table.getByTestId("impact-assumed-continuation").first(),
    ).toContainText("Assumed continuation (no plan decisions)");
    for (const button of await table
      .getByRole("button", { name: /Preview/ })
      .all()) {
      await expect(button).toBeEnabled();
    }

    // The page itself must not scroll sideways (the table scrolls inside its
    // own container on narrow screens).
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);

    // Changing the horizon asks the server to rank for it, on the pinned run.
    await page.getByRole("button", { name: "1 GW", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`h=1&run=${EXPLORER_RUN_ID}$`));
    await expect
      .poll(() => explorerUrls.at(-1)?.searchParams.get("primary_horizon"))
      .toBe("1");
    expect(explorerUrls.at(-1)?.searchParams.get("projection_run_id")).toBe(
      String(EXPLORER_RUN_ID),
    );
    // First load plus the horizon change; pinning the run never refetches.
    expect(explorerUrls).toHaveLength(2);

    expect(methods.every((method) => method === "GET")).toBe(true);
    expect(pageErrors).toEqual([]);
  });
}

// ---------------------------------------------------------------------------
// US2: preview and confirmation (mocked API; the guarded real-API journeys
// follow below and run only through the guarded harness).
// ---------------------------------------------------------------------------

type MockedServer = {
  plan: PlanResponse;
  revision: number;
  incomingPriceTenths: number;
  mutations: {
    mutation_id: string;
    expected_revision: number;
    intents: Record<string, unknown>[];
  }[];
  receipts: string[];
  previewRequests: number[];
  /** Decides the reply to the Nth mutation (0-based); default commits it. */
  onMutation: (
    index: number,
  ) =>
    "commit" | "price_changed" | "conflict" | "accepted_not_saved" | "network";
  committed: number[];
};

function previewPayload(server: MockedServer, playerInId: number) {
  const base =
    playerInId === 103
      ? buildStructuralBlockedPreview()
      : buildPlannerPreviewResponse();
  const shift = GAMEWEEK - 9;
  const payload = structuredClone(base);
  payload.planning_context = {
    plan_id: server.plan.plan_id,
    gameweek: GAMEWEEK,
    revision: server.revision,
  };
  payload.plan = {
    ...payload.plan,
    plan_id: server.plan.plan_id,
    name: server.plan.name,
    gameweek: GAMEWEEK,
    revision: server.revision,
  };
  payload.gameweeks = payload.gameweeks.map((week) => ({
    ...week,
    gameweek: week.gameweek + shift,
  }));
  if (payload.conflict) payload.conflict.gameweek = GAMEWEEK + 2;
  if (payload.valid_through_gameweek !== null) {
    payload.valid_through_gameweek = GAMEWEEK + 1;
  }
  payload.candidate.price_tenths =
    playerInId === 101
      ? server.incomingPriceTenths
      : payload.candidate.price_tenths;
  if (payload.commit && payload.commit.intent.kind === "add_transfer") {
    payload.commit.intent.gameweek_number = GAMEWEEK;
    payload.commit.expected_revision = server.revision;
    payload.commit.guard.expected_incoming_price_tenths =
      server.incomingPriceTenths;
  }
  return payload;
}

async function installTransferApi(page: Page, planName: string) {
  const plan = buildPlannerPlan(GAMEWEEK, GAMEWEEK + 2);
  plan.name = planName;
  const server: MockedServer = {
    plan,
    revision: 0,
    incomingPriceTenths: 62,
    mutations: [],
    receipts: [],
    previewRequests: [],
    onMutation: () => "commit",
    committed: [],
  };
  const planAt = () => ({ ...server.plan, revision: server.revision });
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: HEADERS });
    }
    const base = `/plans/${plan.plan_id}`;
    if (request.method() === "POST" && url.pathname === `${base}/mutations`) {
      const envelope = request.postDataJSON();
      const index = server.mutations.length;
      server.mutations.push(envelope);
      const outcome = server.onMutation(index);
      if (outcome === "network") return route.abort("failed");
      if (outcome === "price_changed") {
        return route.fulfill({
          status: 422,
          json: {
            detail: {
              code: "prices_changed",
              message: "Prices changed since you previewed this transfer",
              diagnostics: [],
            },
          },
          headers: HEADERS,
        });
      }
      if (outcome === "conflict") {
        return route.fulfill({
          status: 409,
          json: {
            detail: {
              code: "revision_conflict",
              message: "The plan was changed in another tab",
              plan: planAt(),
            },
          },
          headers: HEADERS,
        });
      }
      if (outcome === "accepted_not_saved") {
        return route.fulfill({
          status: 503,
          json: {
            detail: {
              code: "accepted_not_saved",
              message: "The edit was accepted but could not be saved",
              plan: planAt(),
              candidate: null,
            },
          },
          headers: HEADERS,
        });
      }
      server.revision = envelope.expected_revision + 1;
      server.committed.push(index);
      return route.fulfill({
        json: {
          status: "committed",
          mutation_id: envelope.mutation_id,
          committed_revision: server.revision,
          plan: planAt(),
          candidate: null,
        },
        headers: HEADERS,
      });
    }
    if (url.pathname.startsWith(`${base}/mutations/`)) {
      server.receipts.push(url.pathname.split("/").pop()!);
      return route.fulfill({
        status: 404,
        json: { detail: { code: "mutation_not_found", message: "unknown" } },
        headers: HEADERS,
      });
    }
    if (url.pathname === base) {
      return route.fulfill({ json: planAt(), headers: HEADERS });
    }
    if (url.pathname.endsWith("/preview")) {
      const playerIn = Number(url.searchParams.get("player_in_id"));
      server.previewRequests.push(playerIn);
      return route.fulfill({
        json: previewPayload(server, playerIn),
        headers: HEADERS,
      });
    }
    if (url.pathname.includes("/transfers/")) {
      const payload = explorerPayload(plan.plan_id, plan.name);
      payload.planning_context.revision = server.revision;
      payload.candidates.push(buildFinancialBlockedCandidate());
      return route.fulfill({ json: payload, headers: HEADERS });
    }
    return route.fulfill({
      status: 404,
      json: { detail: { code: "unexpected", message: url.pathname } },
      headers: HEADERS,
    });
  });
  return server;
}

async function openExplorer(page: Page, server: MockedServer) {
  await page.goto(
    `/transfers?plan=${server.plan.plan_id}&gw=${GAMEWEEK}&out=${OUTGOING_ID}`,
  );
  await expect(
    page.getByRole("table", { name: "Replacement candidates" }),
  ).toBeVisible();
}

async function smallTargets(page: Page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll("button, a[href], input, select"))
      .filter((el) => {
        const box = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return (
          box.width > 0 &&
          style.visibility !== "hidden" &&
          !(el as HTMLButtonElement).disabled &&
          (box.height < 24 || box.width < 24)
        );
      })
      .map(
        (el) =>
          `${el.tagName} ${el.getAttribute("aria-label") ?? el.textContent?.trim()}`,
      ),
  );
}

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test.describe(`US2 mocked journeys at ${viewport.width}px`, () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize(viewport);
    });

    test("B3 a blocked candidate is previewable, names the clashing gameweek and cannot be confirmed", async ({
      page,
    }) => {
      const server = await installTransferApi(page, "B3 blocked");
      await openExplorer(page, server);

      await page.getByRole("button", { name: "Preview Blocked Ben" }).click();

      const panel = page.getByRole("region", { name: "Transfer preview" });
      await expect(panel.getByTestId("preview-conflict")).toContainText("GW14");
      await expect(panel.getByTestId("preview-gw-12")).toBeVisible();
      await expect(panel.getByTestId("preview-gw-14")).toContainText(
        /not valid/i,
      );
      await expect(
        panel.getByRole("button", { name: "Confirm transfer" }),
      ).toBeDisabled();
      await expect(
        panel.getByRole("button", { name: /repair|fix|remove|resolve/i }),
      ).toHaveCount(0);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);
      expect(await smallTargets(page)).toEqual([]);
      expect(server.mutations).toHaveLength(0);
    });

    test("an available preview shows saved plan and assumed continuation apart and confirms once", async ({
      page,
    }) => {
      const server = await installTransferApi(page, "Happy path");
      await openExplorer(page, server);

      await page
        .getByRole("button", { name: "Preview Available Alex" })
        .click();

      const panel = page.getByRole("region", { name: "Transfer preview" });
      await expect(
        panel.getByRole("region", { name: "Saved plan gameweeks" }),
      ).toBeVisible();
      await expect(
        panel.getByRole("region", {
          name: "Assumed continuation (no plan decisions)",
        }),
      ).toBeVisible();
      await expect(panel.getByTestId("totals-5")).toContainText("+7.5");
      expect(await smallTargets(page)).toEqual([]);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);

      await panel.getByRole("button", { name: "Confirm transfer" }).dblclick();

      await expect(page.getByTestId("commit-success")).toContainText(
        "Transfer added to your plan",
      );
      expect(server.mutations).toHaveLength(1);
      expect(server.mutations[0].expected_revision).toBe(0);
      expect(server.mutations[0].intents[0]).toMatchObject({
        kind: "add_transfer",
        gameweek_number: GAMEWEEK,
        outgoing_player_id: OUTGOING_ID,
        incoming_player_id: 101,
        expected_outgoing_market_tenths: 54,
        expected_incoming_price_tenths: 62,
      });
      await expect(page).toHaveURL(/\/transfers\?plan=/);
    });

    test("B4 a price change between preview and confirm is rejected, kept visible, re-previewed and needs a second explicit confirm", async ({
      page,
    }) => {
      const server = await installTransferApi(page, "B4 prices");
      server.onMutation = (index) => (index === 0 ? "price_changed" : "commit");
      await openExplorer(page, server);
      await page
        .getByRole("button", { name: "Preview Available Alex" })
        .click();
      const confirm = page.getByRole("button", { name: "Confirm transfer" });
      await expect(confirm).toBeEnabled();
      server.incomingPriceTenths = 64;

      await confirm.click();

      const rejection = page.getByTestId("commit-rejection");
      await expect(rejection).toContainText(
        "Prices changed since you previewed this transfer",
      );
      await expect(
        page
          .getByRole("region", { name: "Transfer preview" })
          .getByText("£6.4m"),
      ).toBeVisible();
      await expect(rejection).toBeVisible();
      expect(server.mutations).toHaveLength(1);
      expect(server.previewRequests).toEqual([101, 101]);
      expect(server.committed).toEqual([]);

      await page.getByRole("button", { name: "Confirm transfer" }).click();

      await expect(page.getByTestId("commit-success")).toBeVisible();
      expect(server.mutations).toHaveLength(2);
      expect(server.mutations[1].mutation_id).not.toBe(
        server.mutations[0].mutation_id,
      );
      expect(server.mutations[1].intents[0]).toMatchObject({
        expected_incoming_price_tenths: 64,
      });
    });

    test("B5 accepted-but-not-saved warns first, then stopping tracking shows the not-added notice and nothing is saved", async ({
      page,
    }) => {
      const server = await installTransferApi(page, "B5 pending");
      server.onMutation = () => "accepted_not_saved";
      await openExplorer(page, server);
      await page
        .getByRole("button", { name: "Preview Available Alex" })
        .click();
      await page.getByRole("button", { name: "Confirm transfer" }).click();

      const pending = page.getByTestId("commit-pending");
      await expect(pending).toContainText(
        "The server accepted this transfer but could not save it.",
      );
      await expect(
        pending.getByRole("button", { name: "Retry same transfer" }),
      ).toBeVisible();
      await expect(
        pending.getByRole("button", { name: "Check save status" }),
      ).toBeVisible();
      await expect(
        pending.getByRole("paragraph").filter({
          hasText: "If you stop tracking it",
        }),
      ).toBeVisible();
      expect(await smallTargets(page)).toEqual([]);

      await pending
        .getByRole("button", { name: "Stop tracking this transfer" })
        .click();

      const notice = page.getByTestId("not-added-notice");
      await expect(notice).toContainText(
        "Transfer not added to your plan. The server may still hold a pending record of it",
      );
      await expect(page.getByTestId("commit-success")).toHaveCount(0);
      await expect(
        page.getByRole("region", { name: "Transfer preview" }),
      ).toHaveCount(0);
      expect(server.mutations).toHaveLength(1);
      expect(server.receipts).toEqual([]);
      expect(server.committed).toEqual([]);
      expect(server.revision).toBe(0);
      expect(await page.locator("body").innerText()).not.toMatch(
        /was (saved|cancelled|deleted|removed)/i,
      );
    });

    test("B5 an unknown outcome offers a status check and the same-identity retry", async ({
      page,
    }) => {
      const server = await installTransferApi(page, "B5 unknown");
      server.onMutation = (index) => (index === 0 ? "network" : "commit");
      await openExplorer(page, server);
      await page
        .getByRole("button", { name: "Preview Available Alex" })
        .click();
      await page.getByRole("button", { name: "Confirm transfer" }).click();

      const unknown = page.getByTestId("commit-unknown");
      await expect(unknown).toBeVisible();
      await expect(
        page.getByRole("button", {
          name: /stop tracking|refresh and preview/i,
        }),
      ).toHaveCount(0);
      await unknown.getByRole("button", { name: "Check save status" }).click();
      await expect.poll(() => server.receipts.length).toBe(1);
      expect(server.receipts[0]).toBe(server.mutations[0].mutation_id);

      await page.getByRole("button", { name: "Retry same transfer" }).click();

      await expect(page.getByTestId("commit-success")).toBeVisible();
      expect(server.mutations).toHaveLength(2);
      expect(server.mutations[1].mutation_id).toBe(
        server.mutations[0].mutation_id,
      );
      expect(server.mutations[1].expected_revision).toBe(0);
    });

    test("B5 a plan changed elsewhere gives a conflict, never a submission against the newer revision", async ({
      page,
    }) => {
      const server = await installTransferApi(page, "B5 conflict");
      server.onMutation = (index) => (index === 0 ? "conflict" : "commit");
      await openExplorer(page, server);
      await page
        .getByRole("button", { name: "Preview Available Alex" })
        .click();
      const confirm = page.getByRole("button", { name: "Confirm transfer" });
      await expect(confirm).toBeEnabled();
      server.revision = 1;

      await confirm.click();

      const conflict = page.getByTestId("commit-conflict");
      await expect(conflict).toContainText(
        "The plan was changed in another tab",
      );
      expect(server.mutations).toHaveLength(1);
      expect(server.mutations[0].expected_revision).toBe(0);

      await conflict
        .getByRole("button", { name: "Refresh and preview again" })
        .click();

      await expect.poll(() => server.previewRequests).toEqual([101, 101]);
      await expect(
        page.getByRole("button", { name: "Confirm transfer" }),
      ).toBeEnabled();
      expect(server.mutations).toHaveLength(1);
      await page.getByRole("button", { name: "Confirm transfer" }).click();
      await expect(page.getByTestId("commit-success")).toBeVisible();
      expect(server.mutations[1].expected_revision).toBe(1);
      expect(server.mutations[1].mutation_id).not.toBe(
        server.mutations[0].mutation_id,
      );
    });

    test("B5 the Planner shows the unresolved submission after leaving the Explorer", async ({
      page,
    }) => {
      const server = await installTransferApi(page, "B5 return");
      server.onMutation = () => "accepted_not_saved";
      await openExplorer(page, server);
      await page
        .getByRole("button", { name: "Preview Available Alex" })
        .click();
      await page.getByRole("button", { name: "Confirm transfer" }).click();
      await expect(page.getByTestId("commit-pending")).toBeVisible();

      await page
        .getByRole("region", { name: "Planner context" })
        .getByRole("link", { name: "Back to plan" })
        .click();

      // Client-side navigation keeps the shared coordinator, so the Planner's existing
      // save-status controls act on the pinned submission; none of them replays it.
      await expect(page).toHaveURL(new RegExp(`/plans/${server.plan.plan_id}`));
      await expect(
        page.getByRole("status").filter({ hasText: "Not saved" }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Retry Same Edit" }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Check Save Status" }),
      ).toBeVisible();
      expect(server.mutations).toHaveLength(1);
      expect(server.committed).toEqual([]);
    });
  });
}

// ---------------------------------------------------------------------------
// US2 guarded real-API journeys. They run only through the guarded harness
// (apps/api/tests/repositories/test_plan_transfer_browser_journeys.py), which
// serves the real API on an isolated test schema and drives the triggers below.
// ---------------------------------------------------------------------------

const REAL_API = process.env.PLANNER_TEST_API_URL;
const REAL_PLAN_ID = process.env.PLANNER_TEST_PLAN_ID;
const REAL_GAMEWEEK = Number(process.env.PLANNER_TEST_GAMEWEEK ?? "8");
const REAL_WIDTH = Number(process.env.PLANNER_VIEWPORT ?? "1440");
const REAL_VIEWPORT = {
  width: REAL_WIDTH,
  height: REAL_WIDTH >= 1000 ? 900 : 844,
};

type SeenRequest = {
  method: string;
  path: string;
  status: number;
  body: {
    mutation_id: string;
    expected_revision: number;
    intents: unknown[];
  } | null;
};

async function forwardToRealApi(page: Page, seen: SeenRequest[]) {
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: HEADERS });
    }
    expect(["GET", "POST"]).toContain(request.method());
    const url = new URL(request.url());
    const response = await route.fetch({
      url: `${REAL_API}${url.pathname}${url.search}`,
    });
    seen.push({
      method: request.method(),
      path: url.pathname,
      status: response.status(),
      body: request.method() === "POST" ? request.postDataJSON() : null,
    });
    await route.fulfill({
      response,
      headers: { ...response.headers(), ...HEADERS },
    });
  });
}

async function readRealPlan(page: Page) {
  const response = await page.request.get(`${REAL_API}/plans/${REAL_PLAN_ID}`);
  expect(response.ok()).toBe(true);
  return (await response.json()) as PlanResponse;
}

function savedTransfers(plan: PlanResponse) {
  return plan.gameweeks.flatMap((week) =>
    week.decisions.map((decision) => ({
      gameweek: week.gameweek_number,
      out: decision.outgoing_player_id,
      in: decision.incoming_player_id,
    })),
  );
}

async function openRealExplorer(page: Page) {
  await page.goto(
    `/transfers?plan=${REAL_PLAN_ID}&gw=${REAL_GAMEWEEK}&out=${OUTGOING_ID}`,
  );
  await expect(
    page.getByRole("table", { name: "Replacement candidates" }),
  ).toBeVisible();
}

async function expectPersistedOnPlanner(page: Page) {
  await page.goto(`/plans/${REAL_PLAN_ID}`);
  await page.getByLabel(`Gameweek ${REAL_GAMEWEEK}`, { exact: true }).click();
  await expect(
    page.getByText(new RegExp(`Transfers: P${OUTGOING_ID} → P106`)),
  ).toBeVisible();
  await page.reload();
  await page.getByLabel(`Gameweek ${REAL_GAMEWEEK}`, { exact: true }).click();
  await expect(
    page.getByText(new RegExp(`Transfers: P${OUTGOING_ID} → P106`)),
  ).toBeVisible();
}

test("US2 real API confirm persists the transfer after a reload", async ({
  page,
}) => {
  test.skip(
    !REAL_API || !REAL_PLAN_ID,
    "Run through the guarded API browser regression",
  );
  await page.setViewportSize(REAL_VIEWPORT);
  const seen: SeenRequest[] = [];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await forwardToRealApi(page, seen);
  const before = await readRealPlan(page);
  expect(savedTransfers(before)).toEqual([]);

  await openRealExplorer(page);
  await page.getByRole("button", { name: "Preview P106" }).click();
  const panel = page.getByRole("region", { name: "Transfer preview" });
  await expect(
    panel.getByRole("region", { name: "Saved plan gameweeks" }),
  ).toBeVisible();
  await expect(
    panel.getByRole("region", {
      name: "Assumed continuation (no plan decisions)",
    }),
  ).toBeVisible();
  await expect(panel.getByTestId(`preview-gw-${REAL_GAMEWEEK}`)).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "Confirm transfer" }),
  ).toBeEnabled();
  expect(await smallTargets(page)).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    ),
  ).toBeLessThanOrEqual(0);

  await panel.getByRole("button", { name: "Confirm transfer" }).click();

  await expect(page.getByTestId("commit-success")).toContainText(
    `Transfer added to your plan: P${OUTGOING_ID} to P106 in GW${REAL_GAMEWEEK}`,
  );
  const posts = seen.filter((item) => item.method === "POST");
  expect(posts).toHaveLength(1);
  expect(posts[0].status).toBe(200);
  expect(posts[0].body?.expected_revision).toBe(before.revision);
  expect(posts[0].body?.intents[0]).toMatchObject({
    kind: "add_transfer",
    incoming_player_id: 106,
    outgoing_player_id: OUTGOING_ID,
  });
  const after = await readRealPlan(page);
  expect(savedTransfers(after)).toEqual([
    { gameweek: REAL_GAMEWEEK, out: OUTGOING_ID, in: 106 },
  ]);
  expect(after.revision).toBe(before.revision + 1);

  // A hard reload loses client state: the server is the only source of truth.
  await expectPersistedOnPlanner(page);
  await openRealExplorerAfterSale(page);
  expect(errors).toEqual([]);
});

async function openRealExplorerAfterSale(page: Page) {
  await page.goto(
    `/transfers?plan=${REAL_PLAN_ID}&gw=${REAL_GAMEWEEK}&out=${OUTGOING_ID}`,
  );
  await expect(
    page.locator("[role=alert]:not(#__next-route-announcer__)"),
  ).toContainText(`not in your squad for GW${REAL_GAMEWEEK}`);
}

test("US2 real API prices changed between preview and confirm is rejected then re-confirmed explicitly", async ({
  page,
}) => {
  test.skip(
    !REAL_API || !REAL_PLAN_ID,
    "Run through the guarded API browser regression",
  );
  const priceFile = process.env.PLANNER_PRICE_FILE;
  test.skip(!priceFile, "The guarded harness provides the price trigger");
  await page.setViewportSize(REAL_VIEWPORT);
  const seen: SeenRequest[] = [];
  await forwardToRealApi(page, seen);
  const before = await readRealPlan(page);

  await openRealExplorer(page);
  await page.getByRole("button", { name: "Preview P106" }).click();
  const panel = page.getByRole("region", { name: "Transfer preview" });
  await expect(panel.getByText("£5.0m").first()).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "Confirm transfer" }),
  ).toBeEnabled();
  fs.writeFileSync(
    priceFile!,
    "price of P106 rises to 5.4 before the next request",
  );

  await panel.getByRole("button", { name: "Confirm transfer" }).click();

  await expect(page.getByTestId("commit-rejection")).toContainText(/prices/i);
  await expect(
    page.getByRole("region", { name: "Transfer preview" }).getByText("£5.4m"),
  ).toBeVisible();
  let posts = seen.filter((item) => item.method === "POST");
  expect(posts).toHaveLength(1);
  expect(posts[0].status).toBe(422);
  expect(savedTransfers(await readRealPlan(page))).toEqual([]);
  await page.waitForTimeout(500);
  expect(seen.filter((item) => item.method === "POST")).toHaveLength(1);

  await page.getByRole("button", { name: "Confirm transfer" }).click();

  await expect(page.getByTestId("commit-success")).toBeVisible();
  posts = seen.filter((item) => item.method === "POST");
  expect(posts).toHaveLength(2);
  expect(posts[1].status).toBe(200);
  expect(posts[1].body?.mutation_id).not.toBe(posts[0].body?.mutation_id);
  expect(posts[1].body?.expected_revision).toBe(before.revision);
  expect(posts[1].body?.intents[0]).toMatchObject({
    expected_incoming_price_tenths: 54,
  });
  expect(savedTransfers(await readRealPlan(page))).toEqual([
    { gameweek: REAL_GAMEWEEK, out: OUTGOING_ID, in: 106 },
  ]);
  await expectPersistedOnPlanner(page);
});

test("US2 real API accepted-but-not-saved can be abandoned without a saved transfer, then added with a fresh preview", async ({
  page,
}) => {
  test.skip(
    !REAL_API || !REAL_PLAN_ID,
    "Run through the guarded API browser regression",
  );
  const faultFile = process.env.PLANNER_FAULT_FILE;
  test.skip(!faultFile, "The guarded harness provides the write-fault trigger");
  await page.setViewportSize(REAL_VIEWPORT);
  const seen: SeenRequest[] = [];
  await forwardToRealApi(page, seen);
  const before = await readRealPlan(page);

  await openRealExplorer(page);
  await page.getByRole("button", { name: "Preview P106" }).click();
  await expect(
    page.getByRole("button", { name: "Confirm transfer" }),
  ).toBeEnabled();
  fs.writeFileSync(faultFile!, "fail the canonical write after the receipt");

  await page.getByRole("button", { name: "Confirm transfer" }).click();

  const pending = page.getByTestId("commit-pending");
  await expect(pending).toContainText(
    "The server accepted this transfer but could not save it.",
  );
  await expect(page.getByTestId("commit-success")).toHaveCount(0);
  const firstPost = seen.filter((item) => item.method === "POST");
  expect(firstPost).toHaveLength(1);
  expect(firstPost[0].status).toBe(503);
  expect(savedTransfers(await readRealPlan(page))).toEqual([]);
  expect((await readRealPlan(page)).revision).toBe(before.revision);

  await pending
    .getByRole("button", { name: "Stop tracking this transfer" })
    .click();

  await expect(page.getByTestId("not-added-notice")).toContainText(
    "Transfer not added to your plan.",
  );
  expect(seen.filter((item) => item.method === "POST")).toHaveLength(1);
  expect(savedTransfers(await readRealPlan(page))).toEqual([]);
  expect((await readRealPlan(page)).revision).toBe(before.revision);
  expect(await page.locator("body").innerText()).not.toMatch(
    /was (saved|cancelled|deleted|removed)/i,
  );

  fs.unlinkSync(faultFile!);
  await page.getByRole("button", { name: "Preview P106" }).click();
  await page.getByRole("button", { name: "Confirm transfer" }).click();

  await expect(page.getByTestId("commit-success")).toBeVisible();
  const posts = seen.filter((item) => item.method === "POST");
  expect(posts).toHaveLength(2);
  expect(posts[1].status).toBe(200);
  expect(posts[1].body?.mutation_id).not.toBe(posts[0].body?.mutation_id);
  expect(savedTransfers(await readRealPlan(page))).toEqual([
    { gameweek: REAL_GAMEWEEK, out: OUTGOING_ID, in: 106 },
  ]);
  await expectPersistedOnPlanner(page);
});
