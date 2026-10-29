import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchPlanTransferExplorer, fetchPlanTransferPreview } from "@/lib/api";

import {
  buildExplorerHorizons,
  buildFinancialBlockedPreview,
  buildPlannerExplorerResponse,
  buildPlannerPreviewResponse,
  buildStructuralBlockedPreview,
  EXPLORER_GAMEWEEK,
  EXPLORER_PLAN_ID,
} from "../fixtures/planner-explorer";

function respond(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

const params = {
  planId: EXPLORER_PLAN_ID,
  gameweek: EXPLORER_GAMEWEEK,
  playerOutId: 6,
};

describe("fetchPlanTransferExplorer", () => {
  it("requests the plan-scoped list and keeps the planning context", async () => {
    const payload = buildPlannerExplorerResponse();
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(respond(200, payload));

    const result = await fetchPlanTransferExplorer({
      ...params,
      primaryHorizon: 3,
      projectionRunId: 42,
    });

    const url = new URL(String(fetchSpy.mock.calls[0][0]));
    expect(url.pathname).toBe("/plans/7/gameweeks/9/transfers/6");
    expect(url.searchParams.get("primary_horizon")).toBe("3");
    expect(url.searchParams.get("projection_run_id")).toBe("42");
    expect(result.type).toBe("ok");
    if (result.type === "ok") {
      expect(result.data.planning_context).toEqual({
        plan_id: 7,
        gameweek: 9,
        revision: 3,
      });
      expect(result.data.candidates).toHaveLength(3);
    }
  });

  it("defaults to the five gameweek horizon and omits an unpinned run", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(respond(200, buildPlannerExplorerResponse()));

    await fetchPlanTransferExplorer(params);

    const url = new URL(String(fetchSpy.mock.calls[0][0]));
    expect(url.searchParams.get("primary_horizon")).toBe("5");
    expect(url.searchParams.has("projection_run_id")).toBe(false);
  });

  it("maps a missing plan to plan_not_found without a My Team fallback", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        respond(404, { detail: { code: "plan_not_found", message: "no" } }),
      );

    await expect(fetchPlanTransferExplorer(params)).resolves.toEqual({
      type: "plan_not_found",
    });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(String(fetchSpy.mock.calls[0][0])).not.toContain("/my-team/");
  });

  it("maps player_not_found and plan_not_ready", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        respond(404, { detail: { code: "player_not_found", message: "x" } }),
      )
      .mockResolvedValueOnce(
        respond(409, {
          detail: { code: "plan_not_ready", message: "Initialising" },
        }),
      );

    await expect(fetchPlanTransferExplorer(params)).resolves.toEqual({
      type: "player_not_found",
    });
    await expect(fetchPlanTransferExplorer(params)).resolves.toEqual({
      type: "plan_not_ready",
      message: "Initialising",
    });
  });

  it.each([
    "gameweek_not_in_plan",
    "evaluation_blocked",
    "player_not_in_squad",
    "no_projection_run",
    "run_not_found",
    "run_model_mismatch",
    "gameweek_not_projected",
    "selectability_unknown",
    "invalid_money",
    "invalid_horizon",
  ])(
    "maps %s to an unavailable state carrying the server code",
    async (code) => {
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        respond(422, { detail: { code, message: `server says ${code}` } }),
      );

      await expect(fetchPlanTransferExplorer(params)).resolves.toEqual({
        type: "unavailable",
        code,
        message: `server says ${code}`,
        missingPlayerIds: [],
      });
    },
  );

  it("keeps the missing player ids for missing_projections", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      respond(422, {
        detail: {
          code: "missing_projections",
          message: "GW10: fixture not projected",
          missing_player_ids: [3, 8],
        },
      }),
    );

    await expect(fetchPlanTransferExplorer(params)).resolves.toEqual({
      type: "unavailable",
      code: "missing_projections",
      message: "GW10: fixture not projected",
      missingPlayerIds: [3, 8],
    });
  });

  it("throws for unexpected server failures instead of hiding them", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(respond(500, {}));

    await expect(fetchPlanTransferExplorer(params)).rejects.toThrow(
      /status 500/,
    );
  });
});

describe("fetchPlanTransferPreview", () => {
  const previewParams = { ...params, playerInId: 101, projectionRunId: 42 };

  it("requests the plan-scoped preview on the pinned run", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(respond(200, buildPlannerPreviewResponse()));

    await fetchPlanTransferPreview(previewParams);

    const url = new URL(String(fetchSpy.mock.calls[0][0]));
    expect(url.pathname).toBe("/plans/7/gameweeks/9/transfers/6/preview");
    expect(url.searchParams.get("player_in_id")).toBe("101");
    expect(url.searchParams.get("projection_run_id")).toBe("42");
    expect(fetchSpy.mock.calls[0][1]?.method ?? "GET").toBe("GET");
  });

  it("omits an unpinned run", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(respond(200, buildPlannerPreviewResponse()));

    await fetchPlanTransferPreview({ ...params, playerInId: 101 });

    const url = new URL(String(fetchSpy.mock.calls[0][0]));
    expect(url.searchParams.has("projection_run_id")).toBe(false);
  });

  it("returns the exact server-issued commit descriptor untouched", async () => {
    const payload = buildPlannerPreviewResponse();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(respond(200, payload));

    const result = await fetchPlanTransferPreview(previewParams);

    expect(result.type).toBe("ok");
    if (result.type === "ok") {
      expect(result.data.commit).toEqual(payload.commit);
      expect(result.data.commit?.expected_revision).toBe(
        result.data.planning_context.revision,
      );
      expect(result.data.planning_context).toEqual(payload.planning_context);
    }
  });

  it("keeps a blocked candidate's conflict and withheld descriptor", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      respond(200, buildStructuralBlockedPreview()),
    );

    const result = await fetchPlanTransferPreview(previewParams);

    expect(result.type).toBe("ok");
    if (result.type === "ok") {
      expect(result.data.confirmable).toBe(false);
      expect(result.data.commit).toBeNull();
      expect(result.data.conflict).toMatchObject({
        kind: "structural",
        gameweek: 11,
      });
      expect(result.data.valid_through_gameweek).toBe(10);
    }
  });

  it("keeps a financial shortfall gameweek's accounting and shortfall", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      respond(200, buildFinancialBlockedPreview()),
    );

    const result = await fetchPlanTransferPreview(previewParams);

    expect(result.type).toBe("ok");
    if (result.type === "ok") {
      const shortfall = result.data.gameweeks.find(
        (week) => week.reason === "financial_shortfall",
      );
      expect(shortfall).toMatchObject({
        gameweek: 10,
        valid: false,
        shortfall_tenths: 25,
      });
      expect(shortfall?.accounting?.after.closing_bank_tenths).toBe(-25);
      expect(result.data.conflict?.kind).toBe("financial");
    }
  });

  it("keeps partial horizon coverage", async () => {
    const payload = buildPlannerPreviewResponse();
    payload.projection.horizons = buildExplorerHorizons({
      5: { evaluated_gameweeks: [9, 10], partial: true },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(respond(200, payload));

    const result = await fetchPlanTransferPreview(previewParams);

    expect(
      result.type === "ok" && result.data.projection.horizons[2].partial,
    ).toBe(true);
  });

  it("maps missing plan, player and readiness without a My Team fallback", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        respond(404, { detail: { code: "plan_not_found", message: "x" } }),
      )
      .mockResolvedValueOnce(
        respond(404, { detail: { code: "player_not_found", message: "x" } }),
      )
      .mockResolvedValueOnce(
        respond(409, { detail: { code: "plan_not_ready", message: "Wait" } }),
      );

    await expect(fetchPlanTransferPreview(previewParams)).resolves.toEqual({
      type: "plan_not_found",
    });
    await expect(fetchPlanTransferPreview(previewParams)).resolves.toEqual({
      type: "player_not_found",
    });
    await expect(fetchPlanTransferPreview(previewParams)).resolves.toEqual({
      type: "plan_not_ready",
      message: "Wait",
    });
    for (const call of fetchSpy.mock.calls) {
      expect(String(call[0])).not.toContain("/my-team/");
    }
  });

  it.each([
    "player_not_in_candidate_pool",
    "missing_projections",
    "selectability_unknown",
    "gameweek_not_projected",
    "run_not_found",
  ])("maps %s to an unavailable state with the server code", async (code) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      respond(422, {
        detail: { code, message: `server ${code}`, missing_player_ids: [101] },
      }),
    );

    await expect(fetchPlanTransferPreview(previewParams)).resolves.toEqual({
      type: "unavailable",
      code,
      message: `server ${code}`,
      missingPlayerIds: [101],
    });
  });

  it("throws for unexpected failures", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(respond(500, {}));

    await expect(fetchPlanTransferPreview(previewParams)).rejects.toThrow(
      /status 500/,
    );
  });
});
