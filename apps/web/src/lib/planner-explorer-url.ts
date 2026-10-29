import type { TransferHorizon } from "@/lib/api";

export const DEFAULT_PLANNER_HORIZON: TransferHorizon = 5;

export type PlannerExplorerRoute =
  | { mode: "my_team" }
  | {
      mode: "planner";
      planId: number;
      gameweek: number;
      playerOutId: number | null;
      horizon: TransferHorizon;
      runId: number | null;
    }
  | { mode: "invalid"; reason: string };

type ParamSource = {
  get(name: string): string | null;
  has(name: string): boolean;
};

function parsePositiveInteger(value: string | null): number | null {
  if (value === null || !/^[0-9]+$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

/**
 * Decide which Explorer mode an address selects. A `plan` parameter always
 * selects Planner mode: a malformed Planner address is an explicit invalid
 * link and never silently falls back to My Team mode.
 */
export function parsePlannerExplorerRoute(
  params: ParamSource,
): PlannerExplorerRoute {
  if (!params.has("plan")) {
    return { mode: "my_team" };
  }

  const planId = parsePositiveInteger(params.get("plan"));
  if (planId === null) {
    return { mode: "invalid", reason: "The plan in this link is not valid." };
  }

  if (!params.has("gw")) {
    return { mode: "invalid", reason: "This link does not name a gameweek." };
  }
  const gameweek = parsePositiveInteger(params.get("gw"));
  if (gameweek === null || gameweek > 38) {
    return {
      mode: "invalid",
      reason: "The gameweek in this link is not valid.",
    };
  }

  let playerOutId: number | null = null;
  if (params.has("out")) {
    playerOutId = parsePositiveInteger(params.get("out"));
    if (playerOutId === null) {
      return {
        mode: "invalid",
        reason: "The outgoing player in this link is not valid.",
      };
    }
  }

  let horizon: TransferHorizon = DEFAULT_PLANNER_HORIZON;
  if (params.has("h")) {
    const parsed = parsePositiveInteger(params.get("h"));
    if (parsed !== 1 && parsed !== 3 && parsed !== 5) {
      return {
        mode: "invalid",
        reason: "The ranking horizon in this link must be 1, 3 or 5.",
      };
    }
    horizon = parsed;
  }

  let runId: number | null = null;
  if (params.has("run")) {
    runId = parsePositiveInteger(params.get("run"));
    if (runId === null) {
      return {
        mode: "invalid",
        reason: "The projection run in this link is not valid.",
      };
    }
  }

  return { mode: "planner", planId, gameweek, playerOutId, horizon, runId };
}

export function buildPlannerExplorerHref(params: {
  planId: number;
  gameweek: number;
  playerOutId?: number | null;
  horizon?: TransferHorizon | null;
  runId?: number | null;
}): string {
  const query = new URLSearchParams({
    plan: String(params.planId),
    gw: String(params.gameweek),
  });
  if (params.playerOutId != null) {
    query.set("out", String(params.playerOutId));
  }
  if (params.horizon != null) {
    query.set("h", String(params.horizon));
  }
  if (params.runId != null) {
    query.set("run", String(params.runId));
  }
  return `/transfers?${query.toString()}`;
}

export function buildPlanBoardHref(planId: number, gameweek: number): string {
  return `/plans/${planId}?gw=${gameweek}`;
}
