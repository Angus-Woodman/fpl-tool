import { waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PlanMutationEnvelope, PlanResponse } from "@/lib/api";
import {
  commitDescriptorToIntent,
  createPlannerCommit,
} from "@/lib/planner-commit";
import { getPlanSaveCoordinator } from "@/lib/plan-save-coordinator";

import {
  buildCommitDescriptor,
  buildEditCommitDescriptor,
  buildPlannerPlan,
  deferred,
} from "../fixtures/planner-explorer";

function planAtRevision(revision = 3): PlanResponse {
  return { ...buildPlannerPlan(9, 14), revision };
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function committedBody(
  plan: PlanResponse,
  mutationId: string,
  revision: number,
) {
  return {
    status: "committed",
    mutation_id: mutationId,
    committed_revision: revision,
    plan: { ...plan, revision },
    candidate: null,
  };
}

function captureMutations() {
  const gates: {
    gate: ReturnType<typeof deferred<Response>>;
    envelope: PlanMutationEnvelope;
  }[] = [];
  const spy = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      if (init?.method === "POST") {
        const gate = deferred<Response>();
        gates.push({
          gate,
          envelope: JSON.parse(String(init.body)) as PlanMutationEnvelope,
        });
        return gate.promise;
      }
      throw new Error(`Unexpected request ${String(input)}`);
    });
  return { gates, spy };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("commitDescriptorToIntent", () => {
  it("submits the server's add intent with its price guard and nothing else", () => {
    const descriptor = buildCommitDescriptor(101);

    expect(commitDescriptorToIntent(descriptor)).toEqual({
      ...descriptor.intent,
      expected_outgoing_market_tenths: 54,
      expected_incoming_price_tenths: 62,
    });
  });

  it("keeps an edit intent as the server issued it", () => {
    const descriptor = buildEditCommitDescriptor(101);
    const intent = commitDescriptorToIntent(descriptor);

    expect(intent).toMatchObject({
      kind: "edit_transfer",
      decision_id:
        descriptor.intent.kind === "edit_transfer"
          ? descriptor.intent.decision_id
          : "",
      incoming_player_id: 101,
      expected_incoming_price_tenths: 62,
    });
    expect(intent).not.toHaveProperty("outgoing_player_id");
  });
});

describe("createPlannerCommit", () => {
  it("sends one request pinned to the descriptor's revision with the exact intent", async () => {
    const plan = planAtRevision(3);
    const { gates } = captureMutations();
    const commit = createPlannerCommit(plan);
    const descriptor = buildCommitDescriptor(101);

    const result = commit.submit(descriptor, "P6 to Available Alex");

    expect(result.type).toBe("started");
    await waitFor(() => expect(gates).toHaveLength(1));
    expect(gates[0].envelope.expected_revision).toBe(3);
    expect(gates[0].envelope.intents).toEqual([
      commitDescriptorToIntent(descriptor),
    ]);
    expect(commit.getView().pinned?.status).toBe("sending");
    expect(commit.getView().label).toBe("P6 to Available Alex");
  });

  it("shares the plan's coordinator with the Planner", () => {
    const plan = planAtRevision();
    const commit = createPlannerCommit(plan);
    captureMutations();

    commit.submit(buildCommitDescriptor(101));

    const planner = getPlanSaveCoordinator(plan).getSnapshot();
    expect(planner.pinned?.status).toBe("sending");
    expect(planner.status).toBe("saving");
    expect(commit.getView().pinned).toBe(planner.pinned);
  });

  it("refuses a preview from another revision without contacting the server", () => {
    const { spy } = captureMutations();
    const commit = createPlannerCommit(planAtRevision(4));

    const result = commit.submit(buildCommitDescriptor(101));

    expect(result).toEqual({ type: "refused", reason: "stale_preview" });
    expect(spy).not.toHaveBeenCalled();
    expect(commit.getView().pinned).toBeNull();
  });

  it("refuses a second submission while one is pinned", async () => {
    const { gates } = captureMutations();
    const commit = createPlannerCommit(planAtRevision());
    commit.submit(buildCommitDescriptor(101));
    await waitFor(() => expect(gates).toHaveLength(1));

    expect(commit.submit(buildCommitDescriptor(102))).toEqual({
      type: "refused",
      reason: "pinned_exists",
    });
    expect(gates).toHaveLength(1);
  });

  it("does not treat an unrelated newer revision as the transfer being committed", async () => {
    const plan = planAtRevision(3);
    const { gates } = captureMutations();
    const commit = createPlannerCommit(plan);
    commit.submit(buildCommitDescriptor(101));
    await waitFor(() => expect(gates).toHaveLength(1));

    commit.synchronize({ ...plan, revision: 4 });

    expect(commit.getView().pinned?.status).toBe("sending");
    expect(commit.getView().acknowledgedRevision).toBe(3);
    expect(commit.getView().idle).toBe(false);

    gates[0].gate.resolve(
      json(200, committedBody(plan, gates[0].envelope.mutation_id, 4)),
    );
    await waitFor(() =>
      expect(commit.getView().pinned?.status).toBe("committed"),
    );
    expect(commit.getView().pinned?.committedRevision).toBe(4);
    expect(commit.getView().acknowledgedRevision).toBe(4);
  });

  it("does not report a committed transfer for another mutation's acknowledgement", async () => {
    const plan = planAtRevision(3);
    const { gates } = captureMutations();
    const commit = createPlannerCommit(plan);
    commit.submit(buildCommitDescriptor(101));
    await waitFor(() => expect(gates).toHaveLength(1));

    gates[0].gate.resolve(
      json(200, committedBody(plan, "00000000-0000-4000-8000-000000000999", 4)),
    );

    await waitFor(() =>
      expect(commit.getView().pinned?.status).toBe("unknown"),
    );
  });

  it("returns a stable view until the coordinator changes", () => {
    const commit = createPlannerCommit(planAtRevision());

    expect(commit.getView()).toBe(commit.getView());
  });

  it("is busy while another Planner edit is queued", () => {
    const plan = planAtRevision();
    const { gates } = captureMutations();
    const commit = createPlannerCommit(plan);
    getPlanSaveCoordinator(plan).enqueue([
      { kind: "set_starting_transfers", value: 2 },
    ]);

    expect(commit.getView().idle).toBe(false);
    expect(commit.submit(buildCommitDescriptor(101))).toEqual({
      type: "refused",
      reason: "busy",
    });
    expect(gates).toHaveLength(1);
    expect(gates[0].envelope.intents[0].kind).toBe("set_starting_transfers");
  });
});
