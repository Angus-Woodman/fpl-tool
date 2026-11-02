import fs from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import type { PlanExplorerCandidate, PlanResponse } from "../../src/lib/api";
import {
  buildFinancialBlockedCandidate,
  buildPlannerExplorerResponse,
  buildPlannerPreviewResponse,
  buildRealisticCandidatePool,
  buildStructuralBlockedPreview,
  EXPLORER_RUN_ID,
} from "../fixtures/planner-explorer";
import { buildPlannerPlan, plannerIdentity } from "../fixtures/planner";

test.use({ baseURL: process.env.PLANNER_BASE_URL ?? "http://127.0.0.1:3000" });

const HEADERS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "content-type",
  "access-control-allow-methods": "GET,POST,OPTIONS",
};

const GAMEWEEK = 12;
const OUTGOING_ID = 6;

function explorerPayload(
  planId: number,
  planName: string,
  gameweek = GAMEWEEK,
) {
  const shift = (gameweeks: number[]) =>
    gameweeks.map((week) => week + (gameweek - 9));
  const payload = buildPlannerExplorerResponse();
  payload.planning_context = {
    plan_id: planId,
    gameweek,
    revision: 0,
  };
  payload.plan = {
    ...payload.plan,
    plan_id: planId,
    name: planName,
    gameweek,
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
    blocked.conflict.gameweek = gameweek + 2;
    blocked.valid_through_gameweek = gameweek + 1;
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
  latestRun: number;
  gameweek: number;
  /** Replaces the default three candidates; fixtures are shifted to the selected gameweek. */
  pool: PlanExplorerCandidate[] | null;
  listRequests: URL[];
  /** When set, mutations wait for it before the server answers. */
  hold: Promise<void> | null;
  myTeamRequests: number;
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

function previewPayload(
  server: MockedServer,
  playerInId: number,
  runId: number,
) {
  const base =
    playerInId === 103
      ? buildStructuralBlockedPreview()
      : buildPlannerPreviewResponse();
  const gameweek = server.gameweek;
  const shift = gameweek - 9;
  const payload = structuredClone(base);
  payload.projection.run_id = runId;
  payload.planning_context = {
    plan_id: server.plan.plan_id,
    gameweek,
    revision: server.revision,
  };
  payload.plan = {
    ...payload.plan,
    plan_id: server.plan.plan_id,
    name: server.plan.name,
    gameweek,
    revision: server.revision,
  };
  payload.gameweeks = payload.gameweeks.map((week) => ({
    ...week,
    gameweek: week.gameweek + shift,
  }));
  if (payload.conflict) payload.conflict.gameweek = gameweek + 2;
  if (payload.valid_through_gameweek !== null) {
    payload.valid_through_gameweek = gameweek + 1;
  }
  const pooled = server.pool?.find(
    (candidate) => candidate.player_id === playerInId,
  );
  if (pooled && ![101, 103].includes(playerInId)) {
    payload.candidate = {
      player_id: pooled.player_id,
      web_name: pooled.web_name,
      team_short_name: pooled.team_short_name,
      position: pooled.position,
      status: pooled.status,
      price_tenths: pooled.price_tenths,
    };
  }
  payload.candidate.price_tenths =
    playerInId === 101
      ? server.incomingPriceTenths
      : payload.candidate.price_tenths;
  if (payload.commit && payload.commit.intent.kind === "add_transfer") {
    payload.commit.intent.gameweek_number = gameweek;
    payload.commit.expected_revision = server.revision;
    payload.commit.guard.expected_incoming_price_tenths =
      server.incomingPriceTenths;
  }
  return payload;
}

function applyTransfer(server: MockedServer) {
  for (const week of server.plan.gameweeks) {
    if (week.gameweek_number < server.gameweek) continue;
    week.players = week.players.map((player) =>
      player.player_id === OUTGOING_ID
        ? {
            ...player,
            player_id: 101,
            web_name: "Available Alex",
            team_short_name: "LIV",
            ownership_id: plannerIdentity(2101),
            purchase_price_tenths: 62,
          }
        : player,
    );
    if (week.total_points !== null) week.total_points += 2.5;
    if (week.gameweek_number === server.gameweek) {
      week.transfers_out = [{ player_id: OUTGOING_ID, web_name: "P6" }];
      week.transfers_in = [{ player_id: 101, web_name: "Available Alex" }];
    }
  }
}

async function installTransferApi(
  page: Page,
  planName: string,
  options: { gameweek?: number; pool?: PlanExplorerCandidate[] } = {},
) {
  const plan = buildPlannerPlan(GAMEWEEK, GAMEWEEK + 2);
  plan.name = planName;
  const server: MockedServer = {
    plan,
    revision: 0,
    incomingPriceTenths: 62,
    latestRun: EXPLORER_RUN_ID,
    gameweek: options.gameweek ?? GAMEWEEK,
    pool: options.pool ?? null,
    listRequests: [],
    hold: null,
    myTeamRequests: 0,
    mutations: [],
    receipts: [],
    previewRequests: [],
    onMutation: () => "commit",
    committed: [],
  };
  const planAt = () => ({ ...server.plan, revision: server.revision });
  // On the context so a second tab shares the same server.
  await page.context().route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: HEADERS });
    }
    if (url.pathname.startsWith("/my-team")) server.myTeamRequests += 1;
    const base = `/plans/${plan.plan_id}`;
    if (request.method() === "POST" && url.pathname === `${base}/mutations`) {
      const envelope = request.postDataJSON();
      const index = server.mutations.length;
      server.mutations.push(envelope);
      if (server.hold) await server.hold;
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
      applyTransfer(server);
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
        json: previewPayload(
          server,
          playerIn,
          Number(url.searchParams.get("projection_run_id") ?? server.latestRun),
        ),
        headers: HEADERS,
      });
    }
    if (url.pathname.includes("/transfers/")) {
      const payload = explorerPayload(plan.plan_id, plan.name, server.gameweek);
      payload.planning_context.revision = server.revision;
      payload.projection.run_id = Number(
        url.searchParams.get("projection_run_id") ?? server.latestRun,
      );
      payload.projection.newer_run_available =
        payload.projection.run_id !== server.latestRun;
      server.listRequests.push(url);
      if (server.pool) {
        const shift = server.gameweek - 9;
        payload.candidates = structuredClone(server.pool).map((candidate) => {
          candidate.fixtures.forEach((fixture) => (fixture.gameweek += shift));
          if (candidate.conflict) {
            candidate.conflict.gameweek += shift;
            if (candidate.valid_through_gameweek !== null) {
              candidate.valid_through_gameweek += shift;
            }
          }
          return candidate;
        });
      } else {
        payload.candidates.push(buildFinancialBlockedCandidate());
      }
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
    `/transfers?plan=${server.plan.plan_id}&gw=${server.gameweek}&out=${OUTGOING_ID}`,
  );
  await expect(
    page.getByRole("table", { name: "Replacement candidates" }),
  ).toBeVisible();
}

// The pinned notice stays in view beside the highlighted card, without covering it.
async function expectNoticeBesideHighlight(page: Page, playerId: number) {
  const notice = page.getByTestId("transfer-notice");
  const card = page.locator(
    `[data-player-id="${playerId}"][data-highlighted="true"]`,
  );
  await expect(card).toBeInViewport();
  await expect(notice).toBeInViewport({ ratio: 1 });
  await expect
    .poll(async () => {
      const [a, b] = await Promise.all([
        notice.boundingBox(),
        card.boundingBox(),
      ]);
      if (!a || !b) return "missing";
      const overlaps =
        a.x < b.x + b.width &&
        b.x < a.x + a.width &&
        a.y < b.y + b.height &&
        b.y < a.y + a.height;
      return overlaps ? "overlap" : "clear";
    })
    .toBe("clear");
}

async function expectReturnedToPlanner(
  page: Page,
  server: MockedServer,
  incomingId = 101,
  incomingName = "Available Alex",
) {
  await expect(page).toHaveURL(
    new RegExp(
      `/plans/${server.plan.plan_id}\\?gw=${server.gameweek}&highlight=${incomingId}$`,
    ),
  );
  await expect(page.getByTestId("transfer-notice")).toContainText(
    `Transferred P${OUTGOING_ID} for ${incomingName} in GW${server.gameweek}`,
  );
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

      await expectReturnedToPlanner(page, server);
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

      await expectReturnedToPlanner(page, server);
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

      await expectReturnedToPlanner(page, server);
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
      await expectReturnedToPlanner(page, server);
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
      page.on("dialog", (dialog) => void dialog.accept());
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

    test("a preview made on one projection run cannot be confirmed on another", async ({
      page,
    }) => {
      const server = await installTransferApi(page, "Run switch");
      await openExplorer(page, server);
      await page
        .getByRole("button", { name: "Preview Available Alex" })
        .click();
      await expect(
        page.getByRole("button", { name: "Confirm transfer" }),
      ).toBeEnabled();
      server.latestRun = EXPLORER_RUN_ID + 35;
      // A horizon change keeps the run and the open preview.
      await page.getByRole("button", { name: "3 GWs", exact: true }).click();
      const notice = page.getByTestId("newer-run-notice");
      await expect(notice).toBeVisible();
      await expect(
        page.getByRole("region", { name: "Transfer preview" }),
      ).toBeVisible();
      expect(server.previewRequests).toEqual([101]);

      await notice.getByRole("button", { name: "Use the latest run" }).click();

      await expect(page).toHaveURL(new RegExp(`run=${EXPLORER_RUN_ID + 35}$`));
      await expect(
        page.getByRole("table", { name: "Replacement candidates" }),
      ).toBeVisible();
      await expect(
        page.getByRole("region", { name: "Transfer preview" }),
      ).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: "Confirm transfer" }),
      ).toHaveCount(0);
      expect(server.mutations).toHaveLength(0);

      await page
        .getByRole("button", { name: "Preview Available Alex" })
        .click();
      await expect(
        page.getByRole("button", { name: "Confirm transfer" }),
      ).toBeEnabled();
      expect(server.previewRequests).toEqual([101, 101]);
    });

    test("B5 an unresolved submission keeps its own region when another candidate is previewed", async ({
      page,
    }) => {
      const server = await installTransferApi(page, "B5 switch");
      server.onMutation = () => "accepted_not_saved";
      await openExplorer(page, server);
      await page
        .getByRole("button", { name: "Preview Available Alex" })
        .click();
      await page.getByRole("button", { name: "Confirm transfer" }).click();
      const region = page.getByRole("region", {
        name: "Unresolved transfer confirmation",
      });
      await expect(region).toContainText(
        `P${OUTGOING_ID} to Available Alex in GW${GAMEWEEK}`,
      );

      await page.getByRole("button", { name: "Preview Blocked Ben" }).click();

      const panel = page.getByRole("region", { name: "Transfer preview" });
      await expect(
        panel.getByRole("heading", { name: /for Blocked Ben/ }),
      ).toBeVisible();
      await expect(panel.getByTestId("commit-pending")).toHaveCount(0);
      await expect(
        panel.getByRole("button", { name: "Confirm transfer" }),
      ).toBeDisabled();
      await expect(panel.getByTestId("confirm-disabled-reason")).toContainText(
        "Available Alex",
      );
      await expect(
        region.getByRole("button", { name: "Stop tracking this transfer" }),
      ).toBeVisible();
      await expect(
        region.getByRole("button", { name: "Retry same transfer" }),
      ).toBeVisible();
      expect(await smallTargets(page)).toEqual([]);
      expect(server.mutations).toHaveLength(1);
    });
  });
}

// ---------------------------------------------------------------------------
// US3: return to the plan, history, deep links and departure protection
// (mocked API).
// ---------------------------------------------------------------------------

const DEPARTURE_WARNING =
  "Your latest Planner edit is not saved yet. Leave this page anyway?";

type ScrollRecord = { id: string | null; behavior?: string };

async function recordScrolls(page: Page) {
  await page.addInitScript(() => {
    const scrolls: ScrollRecord[] = [];
    (window as unknown as { __scrolls: ScrollRecord[] }).__scrolls = scrolls;
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (
      arg?: boolean | ScrollIntoViewOptions,
    ) {
      scrolls.push({
        id: this.getAttribute("data-player-id"),
        behavior: typeof arg === "object" ? arg?.behavior : undefined,
      });
      return original.call(this, arg as ScrollIntoViewOptions);
    };
  });
}

const scrolls = (page: Page) =>
  page.evaluate(
    () => (window as unknown as { __scrolls: ScrollRecord[] }).__scrolls,
  );

function answerDialogs(page: Page) {
  const state = { accept: false, messages: [] as string[] };
  page.on("dialog", async (dialog) => {
    state.messages.push(dialog.message());
    if (state.accept) await dialog.accept();
    else await dialog.dismiss();
  });
  return state;
}

const backToPlanLink = (page: Page) =>
  page
    .getByRole("region", { name: "Planner context" })
    .getByRole("link", { name: "Back to plan" });

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test.describe(`US3 mocked journeys at ${viewport.width}px`, () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize(viewport);
    });

    test("B1 explore, preview, confirm and return: same gameweek, highlighted player in view, notice, later gameweeks changed, My Team untouched", async ({
      page,
    }) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      const server = await installTransferApi(page, "B1 loop", {
        gameweek: 13,
      });
      await recordScrolls(page);
      await page.goto(`/plans/${server.plan.plan_id}`);
      await page.getByLabel("Gameweek 13", { exact: true }).click();

      await page
        .getByRole("link", { name: `Explore transfers for P${OUTGOING_ID}` })
        .click();

      await expect(page).toHaveURL(
        new RegExp(
          `/transfers\\?plan=${server.plan.plan_id}&gw=13&out=${OUTGOING_ID}`,
        ),
      );
      await expect(
        page.getByRole("region", { name: "Planner context" }),
      ).toContainText("Gameweek 13");
      await page
        .getByRole("button", { name: "Preview Available Alex" })
        .click();
      await page.getByRole("button", { name: "Confirm transfer" }).click();

      await expectReturnedToPlanner(page, server);
      await expect(
        page.getByLabel("Gameweek 13", { exact: true }),
      ).toHaveAttribute("aria-current", "true");
      const card = page.locator('[data-player-id="101"]');
      await expect(card).toHaveAttribute("data-highlighted", "true");
      await expect(card).toContainText("Just transferred in");
      await expect(card).toBeInViewport();
      await expectNoticeBesideHighlight(page, 101);
      expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
      expect(await scrolls(page)).toEqual([{ id: "101", behavior: "smooth" }]);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth - window.innerWidth,
        ),
      ).toBeLessThanOrEqual(0);
      expect(await smallTargets(page)).toEqual([]);

      // Later gameweeks carry the transfer; the earlier one does not.
      await page.getByLabel("Gameweek 14", { exact: true }).click();
      await expect(page.locator('[data-player-id="101"]')).toHaveCount(1);
      await expect(
        page.locator('[data-player-id="101"][data-highlighted]'),
      ).toHaveCount(0);
      await expect(
        page.locator(`[data-player-id="${OUTGOING_ID}"]`),
      ).toHaveCount(0);
      await page.getByLabel("Gameweek 12", { exact: true }).click();
      await expect(
        page.locator(`[data-player-id="${OUTGOING_ID}"]`),
      ).toHaveCount(1);
      expect(await scrolls(page)).toHaveLength(1);

      // The notice is one-shot.
      await page.reload();
      await expect(
        page.getByLabel("Gameweek 13", { exact: true }),
      ).toBeVisible();
      await expect(page.getByTestId("transfer-notice")).toHaveCount(0);
      expect(server.myTeamRequests).toBe(0);
      expect(server.mutations).toHaveLength(1);
      expect(errors).toEqual([]);
    });

    test("B2 Back returns to the selected gameweek, Forward and reload restore the Explorer, a new tab opens the same context", async ({
      page,
    }) => {
      const server = await installTransferApi(page, "B2 history", {
        gameweek: 13,
      });
      await page.goto(`/plans/${server.plan.plan_id}`);
      await page.getByLabel("Gameweek 13", { exact: true }).click();
      await page
        .getByRole("link", { name: `Explore transfers for P${OUTGOING_ID}` })
        .click();
      const explorerUrl = new RegExp(
        `/transfers\\?plan=${server.plan.plan_id}&gw=13&out=${OUTGOING_ID}&h=5&run=${EXPLORER_RUN_ID}$`,
      );
      await expect(page).toHaveURL(explorerUrl);
      await expect(
        page.getByRole("table", { name: "Replacement candidates" }),
      ).toBeVisible();

      await page.goBack();

      await expect(page).toHaveURL(
        new RegExp(`/plans/${server.plan.plan_id}\\?gw=13$`),
      );
      await expect(
        page.getByLabel("Gameweek 13", { exact: true }),
      ).toHaveAttribute("aria-current", "true");
      expect(server.mutations).toHaveLength(0);

      await page.goForward();

      await expect(page).toHaveURL(explorerUrl);
      await expect(
        page.getByRole("region", { name: "Planner context" }),
      ).toContainText("Planner mode");
      await expect(
        page.getByRole("table", { name: "Replacement candidates" }),
      ).toBeVisible();

      await page.reload();
      await expect(page).toHaveURL(explorerUrl);
      await expect(
        page.getByRole("region", { name: "Planner context" }),
      ).toContainText("Gameweek 13");
      await expect(
        page.getByRole("table", { name: "Replacement candidates" }),
      ).toBeVisible();

      const tab = await page.context().newPage();
      await tab.setViewportSize(viewport);
      await tab.goto(page.url());
      await expect(
        tab.getByRole("region", { name: "Planner context" }),
      ).toContainText("Planner mode");
      await expect(
        tab.getByRole("table", { name: "Replacement candidates" }),
      ).toBeVisible();
      await tab.close();

      // Horizon and player switches keep their context through history.
      await page.getByRole("button", { name: "3 GWs", exact: true }).click();
      await expect(page).toHaveURL(/out=6&h=3&run=42$/);
      await page
        .getByRole("link", { name: "Choose a different player" })
        .click();
      await expect(page).toHaveURL(
        new RegExp(`gw=13&h=3&run=${EXPLORER_RUN_ID}$`),
      );
      await expect(
        page.getByRole("combobox", { name: "Outgoing player" }),
      ).toBeVisible();
      await page.goBack();
      await expect(page).toHaveURL(/out=6&h=3&run=42$/);
      await page.goForward();
      await expect(
        page.getByRole("combobox", { name: "Outgoing player" }),
      ).toBeVisible();
    });

    test("B5 an unresolved submission survives declined and accepted departures and can be retried on return", async ({
      page,
    }) => {
      const server = await installTransferApi(page, "B5 depart", {
        gameweek: 13,
      });
      server.onMutation = (index) =>
        index === 0 ? "accepted_not_saved" : "commit";
      const dialogs = answerDialogs(page);
      await openExplorer(page, server);
      await page
        .getByRole("button", { name: "Preview Available Alex" })
        .click();
      await page.getByRole("button", { name: "Confirm transfer" }).click();
      await expect(page.getByTestId("commit-pending")).toBeVisible();
      const original = server.mutations[0].mutation_id;

      // Declined: the user stays and the submission is intact.
      await backToPlanLink(page).click();
      await expect.poll(() => dialogs.messages).toEqual([DEPARTURE_WARNING]);
      await expect(page).toHaveURL(/\/transfers\?/);
      await expect(page.getByTestId("commit-pending")).toBeVisible();

      // Accepted: client-side navigation keeps the shared coordinator.
      dialogs.accept = true;
      await backToPlanLink(page).click();
      await expect(page).toHaveURL(
        new RegExp(`/plans/${server.plan.plan_id}\\?gw=13$`),
      );
      await expect(
        page.getByRole("status").filter({ hasText: "Not saved" }),
      ).toBeVisible();

      // The Planner stacks its guard entry once it has mounted; wait for it.
      // Browser Back is guarded the same way: cancel, then confirm.
      await expect
        .poll(() =>
          page.evaluate(() => [
            location.pathname,
            window.history.state?.plannerDepartureGuard === true,
          ]),
        )
        .toEqual(["/plans/" + server.plan.plan_id, true]);
      dialogs.accept = false;
      await page.goBack();
      // Dialog 1: declined link click. Dialog 2: accepted link click. Dialog 3: Back.
      await expect.poll(() => dialogs.messages.length).toBe(3);
      await expect(page).toHaveURL(/\/plans\//);
      // Declining restores the guard entry asynchronously (history.go(1)).
      await expect
        .poll(() =>
          page.evaluate(
            () => window.history.state?.plannerDepartureGuard === true,
          ),
        )
        .toBe(true);
      dialogs.accept = true;
      await page.goBack();
      await expect(page).toHaveURL(/\/transfers\?/);

      const region = page.getByRole("region", {
        name: "Unresolved transfer confirmation",
      });
      await expect(region).toContainText(
        `P${OUTGOING_ID} to Available Alex in GW13`,
      );
      expect(server.mutations).toHaveLength(1);

      await region.getByRole("button", { name: "Retry same transfer" }).click();

      await expectReturnedToPlanner(page, server);
      expect(server.mutations).toHaveLength(2);
      expect(server.mutations[1].mutation_id).toBe(original);
      expect(server.committed).toEqual([1]);
    });

    test("a terminal record found after navigating back is shown once, without navigation or resubmission", async ({
      page,
    }) => {
      const server = await installTransferApi(page, "Terminal", {
        gameweek: 13,
      });
      server.onMutation = () => "price_changed";
      let release!: () => void;
      server.hold = new Promise<void>((resolve) => {
        release = resolve;
      });
      const dialogs = answerDialogs(page);
      dialogs.accept = true;
      await openExplorer(page, server);
      await page
        .getByRole("button", { name: "Preview Available Alex" })
        .click();
      await page.getByRole("button", { name: "Confirm transfer" }).click();
      await expect.poll(() => server.mutations.length).toBe(1);

      await backToPlanLink(page).click();
      await expect(page).toHaveURL(/\/plans\//);
      expect(dialogs.messages).toEqual([DEPARTURE_WARNING]);
      const settled = page.waitForResponse(
        (response) => response.request().method() === "POST",
      );
      release();
      await settled;
      await expect(
        page.getByRole("status").filter({ hasText: /^Saved$/ }),
      ).toBeVisible();

      await page.goBack();

      await expect(page).toHaveURL(/\/transfers\?/);
      expect(dialogs.messages).toEqual([DEPARTURE_WARNING]);
      const earlier = page.getByTestId("commit-earlier");
      await expect(earlier).toContainText(
        "Prices changed since you previewed this transfer",
      );
      expect(server.mutations).toHaveLength(1);
      expect(server.committed).toEqual([]);

      await backToPlanLink(page).click();
      await expect(page).toHaveURL(/\/plans\//);
      await page.goBack();
      await expect(
        page.getByRole("table", { name: "Replacement candidates" }),
      ).toBeVisible();
      await expect(page.getByTestId("commit-earlier")).toHaveCount(0);
      expect(server.mutations).toHaveLength(1);
    });

    test("arrival scrolls without animation when reduced motion is requested", async ({
      page,
    }) => {
      const server = await installTransferApi(page, "Reduced motion", {
        gameweek: 13,
      });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await recordScrolls(page);
      await page.addInitScript((planId) => {
        window.sessionStorage.setItem(
          `plannerTransferNotice:${planId}`,
          JSON.stringify({
            message: "Transferred P8 for P6 in GW13",
            gameweek: 13,
            incomingPlayerId: 6,
          }),
        );
      }, server.plan.plan_id);

      await page.goto(
        `/plans/${server.plan.plan_id}?gw=13&highlight=${OUTGOING_ID}`,
      );

      await expect(
        page.getByLabel("Gameweek 13", { exact: true }),
      ).toHaveAttribute("aria-current", "true");
      await expect(
        page.locator(
          `[data-player-id="${OUTGOING_ID}"][data-highlighted="true"]`,
        ),
      ).toBeVisible();
      await expect(page.getByTestId("transfer-notice")).toHaveCount(1);
      await expectNoticeBesideHighlight(page, OUTGOING_ID);
      expect(await scrolls(page)).toEqual([
        { id: String(OUTGOING_ID), behavior: "auto" },
      ]);
    });
  });
}

// ---------------------------------------------------------------------------
// US4: comparing replacement options on a realistic pool (mocked API). The
// pool's fixtures start at GW9 in the fixture and are shifted to GW12 here.
// ---------------------------------------------------------------------------

const POOL_SERVER_ORDER = [
  207, 201, 202, 203, 204, 205, 206, 208, 209, 210, 211, 212,
];
const BY_PRICE = [211, 210, 208, 209, 205, 206, 203, 204, 202, 201, 212, 207];
const BY_GAIN_3 = [207, 201, 202, 203, 204, 208, 205, 206, 209, 210, 211, 212];
const BY_DIFFICULTY = [
  207, 212, 204, 201, 202, 208, 209, 203, 205, 206, 210, 211,
];

const candidateIds = (page: Page) =>
  page
    .locator("tbody tr[data-player-id]")
    .evaluateAll((rows) =>
      rows.map((row) => Number(row.getAttribute("data-player-id"))),
    );

async function expectOrder(page: Page, expected: number[]) {
  await expect.poll(() => candidateIds(page)).toEqual(expected);
}

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test.describe(`US4 comparison controls at ${viewport.width}px`, () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize(viewport);
    });

    async function openPool(page: Page) {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      const server = await installTransferApi(page, "Comparison", {
        gameweek: GAMEWEEK,
        pool: buildRealisticCandidatePool(),
      });
      await openExplorer(page, server);
      await expectOrder(page, POOL_SERVER_ORDER);
      return { server, errors };
    }

    const search = (page: Page) =>
      page.getByRole("searchbox", { name: "Search players" });
    const club = (page: Page) => page.getByRole("combobox", { name: "Club" });
    const maxPrice = (page: Page) =>
      page.getByRole("textbox", { name: "Maximum price (£m)" });
    const availableOnly = (page: Page) =>
      page.getByRole("checkbox", { name: "Available to apply only" });
    const status = (page: Page) =>
      page.getByRole("combobox", { name: "Playing status" });
    const sortBy = (page: Page) =>
      page.getByRole("combobox", { name: "Sort by" });
    const reset = (page: Page) =>
      page.getByRole("button", { name: "Reset filters and sort" });

    test("searching and filtering narrow the list, and Reset restores the server order", async ({
      page,
    }) => {
      const { server, errors } = await openPool(page);

      await search(page).fill("JAMIE");
      await expectOrder(page, [201, 211]);
      await expect(page.getByTestId("result-count")).toHaveText(
        "Showing 2 of 12 candidates",
      );
      await search(page).fill("");
      await expectOrder(page, POOL_SERVER_ORDER);

      // Affordable candidates from one club.
      await club(page).selectOption("CHE");
      await maxPrice(page).fill("6.0");
      await expectOrder(page, [209]);
      const chips = page.getByRole("list", { name: "Active filters" });
      await expect(chips).toContainText("Club: CHE");
      await expect(chips).toContainText("Maximum price: £6.0m");
      await maxPrice(page).fill("6.2");
      await expectOrder(page, [202, 209]);
      await page.getByRole("button", { name: "Remove Club: CHE" }).click();
      await expectOrder(page, [202, 203, 204, 205, 206, 208, 209, 210, 211]);
      await reset(page).click();
      await expectOrder(page, POOL_SERVER_ORDER);
      await expect(chips).toHaveCount(0);

      // The server's availability, independent of playing status.
      await availableOnly(page).check();
      await expectOrder(page, [201, 202, 203, 204, 205, 208, 209, 210, 211]);
      await status(page).selectOption("i");
      await expectOrder(page, [205]);
      await expect(page.locator('tr[data-player-id="205"]')).toHaveAttribute(
        "data-state",
        "available",
      );
      await expect(page.locator('tr[data-player-id="205"]')).toContainText(
        "Injured",
      );
      await reset(page).click();

      // Nothing matches.
      await search(page).fill("zzz");
      await expect(page.getByTestId("no-matches")).toContainText(
        "No candidates match these filters.",
      );
      await page.getByRole("button", { name: "Clear filters" }).click();
      await expectOrder(page, POOL_SERVER_ORDER);

      expect(server.mutations).toHaveLength(0);
      expect(server.listRequests).toHaveLength(1);
      expect(server.previewRequests).toEqual([]);
      expect(errors).toEqual([]);
    });

    test("sorting by price, three-gameweek gain and fixture difficulty is deterministic and reversible", async ({
      page,
    }) => {
      const { server } = await openPool(page);

      await sortBy(page).selectOption("price");
      await expectOrder(page, BY_PRICE);
      await expect(
        page.getByRole("list", { name: "Active filters" }),
      ).toContainText("Sorted by Price, lowest first");
      await expect(
        page.getByRole("columnheader", { name: "Price" }),
      ).toHaveAttribute("aria-sort", "ascending");
      await page.getByRole("button", { name: /^Sort direction: / }).click();
      await expectOrder(
        page,
        [207, 212, 201, 202, 204, 203, 206, 205, 208, 209, 210, 211],
      );

      await sortBy(page).selectOption("gain-3");
      await expectOrder(page, BY_GAIN_3);
      await expect(
        page.getByRole("list", { name: "Active filters" }),
      ).toContainText("Sorted by Best-XI gain over 3 GWs, highest first");

      await sortBy(page).selectOption("difficulty");
      await expectOrder(page, BY_DIFFICULTY);
      await expect(
        page.getByText(/mean of the supplied difficulties over GW12-16/i),
      ).toBeVisible();

      // Sorting a filtered list sorts only that list.
      await club(page).selectOption("TOT");
      await expectOrder(page, [212, 205]);

      await page
        .getByRole("button", {
          name: "Remove Sorted by Fixture difficulty, easiest first",
        })
        .click();
      await expectOrder(page, [205, 212]);
      await reset(page).click();
      await expectOrder(page, POOL_SERVER_ORDER);
      await expect(sortBy(page)).toHaveValue("default");

      // Local controls never ask the server for anything or change a plan.
      expect(server.listRequests).toHaveLength(1);
      expect(server.previewRequests).toEqual([]);
      expect(server.mutations).toHaveLength(0);
    });

    test("fixtures show opponent, venue and difficulty over the selected horizon, including blanks, doubles and missing data", async ({
      page,
    }) => {
      await openPool(page);
      const fixtures = (id: number) =>
        page.locator(`tr[data-player-id="${id}"]`).getByTestId("fixtures");

      await expect(
        page.getByRole("columnheader", { name: "Fixtures GW12-16" }),
      ).toBeVisible();
      await expect(fixtures(201).locator("li")).toHaveText([
        "GW12 BOU (H) Diff 2",
        "GW13 CHE (A) Diff 4",
        "GW14 EVE (H) Diff 2",
        "GW15 TOT (A) Diff 4",
        "GW16 WHU (H) Diff 2",
      ]);
      // A double gameweek keeps both fixtures; a blank is a known blank.
      const double = fixtures(204).locator('li[data-gameweek="14"]');
      await expect(double).toHaveAttribute("data-double", "true");
      await expect(double.getByTestId("fixture")).toHaveText([
        "FUL (H) Diff 2",
        "TOT (A) Diff 3",
      ]);
      await expect(fixtures(203).locator('li[data-gameweek="13"]')).toHaveText(
        "GW13 Blank gameweek",
      );
      // Missing schedule data and a missing difficulty are never invented.
      await expect(fixtures(205).locator('li[data-gameweek="15"]')).toHaveText(
        "GW15 No fixture data",
      );
      await expect(fixtures(211).locator("li")).toHaveText([
        "GW12 No fixture data",
        "GW13 No fixture data",
        "GW14 No fixture data",
        "GW15 No fixture data",
        "GW16 No fixture data",
      ]);
      await expect(fixtures(206).locator('li[data-gameweek="13"]')).toHaveText(
        "GW13 CHE (H) Diff n/a",
      );

      // A shorter horizon is a new server request and shows only its gameweeks.
      await page.getByRole("button", { name: "3 GWs", exact: true }).click();
      await expect(
        page.getByRole("columnheader", { name: "Fixtures GW12-14" }),
      ).toBeVisible();
      await expect(fixtures(201).locator("li")).toHaveCount(3);
    });

    test("a candidate can be previewed after sorting and filtering, and a new horizon returns to the server ranking", async ({
      page,
    }) => {
      const { server } = await openPool(page);

      await sortBy(page).selectOption("price");
      await club(page).selectOption("CHE");
      await expectOrder(page, [209, 202]);
      await page.getByRole("button", { name: "Preview Kofi Mensah" }).click();

      const panel = page.getByRole("region", { name: "Transfer preview" });
      await expect(panel).toContainText("Kofi Mensah");
      expect(server.previewRequests).toEqual([209]);
      // Previewing does not disturb the controls.
      await expectOrder(page, [209, 202]);
      await panel.getByRole("button", { name: "Close preview" }).click();

      await page.getByRole("button", { name: "3 GWs", exact: true }).click();
      await expect.poll(() => server.listRequests.length).toBe(2);
      expect(server.listRequests[1].searchParams.get("primary_horizon")).toBe(
        "3",
      );
      await expect(sortBy(page)).toHaveValue("default");
      expect(server.mutations).toHaveLength(0);
    });

    test("controls are keyboard operable, focus is visible, and the page neither overflows nor has undersized targets", async ({
      page,
    }) => {
      await openPool(page);
      await search(page).fill("o");
      await maxPrice(page).fill("6.5");
      await sortBy(page).selectOption("difficulty");

      await sortBy(page).focus();
      await page.keyboard.press("Tab");
      const direction = page.getByRole("button", { name: /^Sort direction: / });
      await expect(direction).toBeFocused();
      expect(
        await direction.evaluate(
          (element) => getComputedStyle(element).outlineStyle,
        ),
      ).not.toBe("none");
      await page.keyboard.press("Enter");
      await expect(direction).toHaveAccessibleName(/hardest first/);

      await maxPrice(page).fill("6.55");
      await expect(maxPrice(page)).toHaveAttribute("aria-invalid", "true");
      await expect(page.getByText(/Enter a price in £m/)).toBeVisible();
      await maxPrice(page).fill("6.5");

      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth - window.innerWidth,
        ),
      ).toBeLessThanOrEqual(0);
      expect(await smallTargets(page)).toEqual([]);
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

async function expectReturnedToRealPlanner(page: Page) {
  await expect(page).toHaveURL(
    new RegExp(`/plans/${REAL_PLAN_ID}\\?gw=${REAL_GAMEWEEK}&highlight=106$`),
  );
  await expect(page.getByTestId("transfer-notice")).toContainText(
    `Transferred P${OUTGOING_ID} for P106 in GW${REAL_GAMEWEEK}`,
  );
  await expect(
    page.getByLabel(`Gameweek ${REAL_GAMEWEEK}`, { exact: true }),
  ).toHaveAttribute("aria-current", "true");
  const card = page.locator('[data-player-id="106"][data-highlighted="true"]');
  await expect(card).toBeVisible();
  await expectNoticeBesideHighlight(page, 106);
  await expect(page.locator(`[data-player-id="${OUTGOING_ID}"]`)).toHaveCount(
    0,
  );
  await expect(
    page.getByText(new RegExp(`Transfers: P${OUTGOING_ID} → P106`)),
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

  await expectReturnedToRealPlanner(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    ),
  ).toBeLessThanOrEqual(0);
  // The pre-existing text-style "Remove transfer" control is not touched by this feature.
  expect(
    (await smallTargets(page)).filter(
      (label) => !label.startsWith("BUTTON Remove transfer "),
    ),
  ).toEqual([]);
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

  // Back from the Planner reopens the Explorer, which now reports the player as sold.
  await page.goBack();
  await expect(page).toHaveURL(/\/transfers\?/);
  await expect(
    page.locator("[role=alert]:not(#__next-route-announcer__)"),
  ).toContainText(`not in your squad for GW${REAL_GAMEWEEK}`);

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

  await expectReturnedToRealPlanner(page);
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

  await expectReturnedToRealPlanner(page);
  const posts = seen.filter((item) => item.method === "POST");
  expect(posts).toHaveLength(2);
  expect(posts[1].status).toBe(200);
  expect(posts[1].body?.mutation_id).not.toBe(posts[0].body?.mutation_id);
  expect(savedTransfers(await readRealPlan(page))).toEqual([
    { gameweek: REAL_GAMEWEEK, out: OUTGOING_ID, in: 106 },
  ]);
  await expectPersistedOnPlanner(page);
});
