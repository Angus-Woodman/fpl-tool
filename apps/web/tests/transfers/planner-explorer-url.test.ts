import { describe, expect, it } from "vitest";

import {
  buildPlannerExplorerHref,
  parsePlannerExplorerRoute,
} from "@/lib/planner-explorer-url";

function parse(query: string) {
  return parsePlannerExplorerRoute(new URLSearchParams(query));
}

describe("parsePlannerExplorerRoute", () => {
  it("selects My Team mode when there is no plan parameter", () => {
    expect(parse("")).toEqual({ mode: "my_team" });
    expect(parse("out=9&h=3")).toEqual({ mode: "my_team" });
  });

  it("parses plan and gameweek with defaults", () => {
    expect(parse("plan=7&gw=9")).toEqual({
      mode: "planner",
      planId: 7,
      gameweek: 9,
      playerOutId: null,
      horizon: 5,
      runId: null,
    });
  });

  it("parses outgoing player, horizon and pinned run", () => {
    expect(parse("plan=7&gw=9&out=6&h=3&run=42")).toEqual({
      mode: "planner",
      planId: 7,
      gameweek: 9,
      playerOutId: 6,
      horizon: 3,
      runId: 42,
    });
  });

  it.each([
    "plan=abc&gw=9",
    "plan=&gw=9",
    "plan=0&gw=9",
    "plan=-3&gw=9",
    "plan=7",
    "plan=7&gw=",
    "plan=7&gw=nine",
    "plan=7&gw=0",
    "plan=7&gw=39",
    "plan=7&gw=9.5",
    "plan=7&gw=9&out=x",
    "plan=7&gw=9&out=",
    "plan=7&gw=9&h=2",
    "plan=7&gw=9&h=",
    "plan=7&gw=9&run=latest",
    "plan=7&gw=9&run=0",
  ])("reports %s as an explicit invalid link, never My Team mode", (query) => {
    const route = parse(query);
    expect(route.mode).toBe("invalid");
    if (route.mode === "invalid") {
      expect(route.reason.length).toBeGreaterThan(0);
    }
  });
});

describe("buildPlannerExplorerHref", () => {
  it("builds the required parameters only", () => {
    expect(buildPlannerExplorerHref({ planId: 7, gameweek: 9 })).toBe(
      "/transfers?plan=7&gw=9",
    );
  });

  it("adds optional parameters", () => {
    expect(
      buildPlannerExplorerHref({
        planId: 7,
        gameweek: 9,
        playerOutId: 6,
        horizon: 3,
        runId: 42,
      }),
    ).toBe("/transfers?plan=7&gw=9&out=6&h=3&run=42");
  });

  it("round-trips through the parser", () => {
    const href = buildPlannerExplorerHref({
      planId: 12,
      gameweek: 20,
      playerOutId: 301,
      horizon: 1,
      runId: 5,
    });
    const route = parse(href.split("?")[1]);
    expect(route).toEqual({
      mode: "planner",
      planId: 12,
      gameweek: 20,
      playerOutId: 301,
      horizon: 1,
      runId: 5,
    });
  });
});
