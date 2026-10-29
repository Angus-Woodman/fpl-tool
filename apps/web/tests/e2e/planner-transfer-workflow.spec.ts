import { expect, test } from "@playwright/test";

import {
  buildPlannerExplorerResponse,
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
      await expect(button).toBeDisabled();
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
