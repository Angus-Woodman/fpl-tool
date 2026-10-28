import { afterEach, describe, expect, it, vi } from "vitest";

import { PlanRuleError, createPlan, fetchPlan } from "@/lib/api";

const request = { name: "Plan", start_gameweek: 1, end_gameweek: 4 };

function respond(status: number, body: BodyInit | null, json = true) {
  vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(body, {
      status,
      headers: json ? { "Content-Type": "application/json" } : undefined,
    }),
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("plan response errors", () => {
  it("shows a string detail from an HTTP 400", async () => {
    respond(
      400,
      JSON.stringify({
        detail: "Money must be a finite whole number of tenths",
      }),
    );

    const error = await createPlan(request).catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(Error);
    expect(error).not.toBeInstanceOf(PlanRuleError);
    expect((error as Error).message).toBe(
      "Money must be a finite whole number of tenths",
    );
  });

  it("shows the message of an object detail from an HTTP 400", async () => {
    respond(
      400,
      JSON.stringify({
        detail: { code: "invalid_money", message: "Bad bank" },
      }),
    );

    await expect(createPlan(request)).rejects.toThrow("Bad bank");
  });

  it("falls back to the status when the 400 body has no usable detail", async () => {
    respond(400, "<html>Bad Request</html>", false);
    await expect(createPlan(request)).rejects.toThrow(
      "Create plan request failed with status 400",
    );

    respond(400, JSON.stringify({ detail: [{ msg: "validation" }] }));
    await expect(createPlan(request)).rejects.toThrow(
      "Create plan request failed with status 400",
    );
  });

  it("keeps the structured 422 rule error", async () => {
    respond(
      422,
      JSON.stringify({
        detail: {
          code: "invalid_money",
          message: "Saved bank must be a finite whole number of tenths",
        },
      }),
    );

    const error = await createPlan(request).catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(PlanRuleError);
    expect((error as PlanRuleError).code).toBe("invalid_money");
    expect((error as PlanRuleError).message).toBe(
      "Saved bank must be a finite whole number of tenths",
    );
  });

  it("keeps the generic message for other failures and the null for a missing plan", async () => {
    respond(500, "boom", false);
    await expect(createPlan(request)).rejects.toThrow(
      "Create plan request failed with status 500",
    );

    respond(404, JSON.stringify({ detail: "Plan not found" }));
    await expect(fetchPlan(7)).resolves.toBeNull();
  });
});
