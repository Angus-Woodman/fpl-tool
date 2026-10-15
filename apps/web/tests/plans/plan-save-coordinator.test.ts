import { waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  PlanDecision,
  PlanIntent,
  PlanMutationEnvelope,
  PlanResponse,
  PlannerMutationError,
} from "@/lib/api";
import { PlanSaveCoordinator } from "@/lib/plan-save-coordinator";
import {
  applyPlannerIntents,
  buildPlannerPlan,
  createPlannerFixture,
  deferred,
} from "../fixtures/planner";

function withDecisions(plan: PlanResponse, ids: string[]): PlanResponse {
  plan.gameweeks.forEach((week, index) => {
    const id = ids[index];
    week.decisions = id
      ? [
          {
            decision_id: id,
            outgoing_player_id: 2,
            outgoing_ownership_id: `own-${id}`,
            incoming_player_id: 102,
            incoming_ownership_id: `in-${id}`,
            outgoing_market_tenths: 50,
            incoming_price_tenths: 50,
            selling_price_tenths: 50,
            observation_source: "stored_player_observation",
            observed_at: "2026-10-14T12:00:00+00:00",
            origin: "captured",
          } satisfies PlanDecision,
        ]
      : [];
  });
  return plan;
}

describe("PlanSaveCoordinator", () => {
  it("US3 discards rejected repair context when synchronization advances the accepted revision", async () => {
    const initial = withDecisions(buildPlannerPlan(), ["upstream"]);
    const send = vi.fn().mockRejectedValue(
      new PlannerMutationError(422, {
        code: "outgoing_not_owned",
        message: "Missing outgoing player",
        diagnostics: [],
      }),
    );
    const coordinator = new PlanSaveCoordinator(initial, { send });
    coordinator.enqueue([
      {
        kind: "edit_transfer",
        decision_id: "upstream",
        incoming_player_id: 103,
      },
    ]);
    await waitFor(() => expect(coordinator.getSnapshot().status).toBe("error"));
    coordinator.synchronize(initial);
    expect(coordinator.getSnapshot().rejection).not.toBeNull();
    coordinator.synchronize({ ...initial, revision: 1 });
    expect(coordinator.getSnapshot().acknowledged.revision).toBe(1);
    expect(coordinator.getSnapshot().rejection).toBeNull();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("US3 retains rejected impacts without accepting them and submits only explicit repair batches", async () => {
    const initial = withDecisions(buildPlannerPlan(), [
      "upstream",
      "downstream",
    ]);
    const intents: PlanIntent[] = [
      {
        kind: "edit_transfer",
        decision_id: "upstream",
        incoming_player_id: 103,
      },
    ];
    const diagnostics = [
      {
        code: "outgoing_not_owned",
        message: "Intended outgoing player 102 is not owned",
        gameweek_number: 13,
        decision_id: "downstream",
        conflicting_gameweek: null,
        player_id: 102,
      },
    ];
    const server = createPlannerFixture(initial, (plan) => plan);
    const send = vi
      .fn(async (_planId: number, envelope: PlanMutationEnvelope) => ({
        ...server.mutate(envelope),
        mutation_id: envelope.mutation_id,
        candidate: null,
      }))
      .mockRejectedValueOnce(
        new PlannerMutationError(422, {
          code: "outgoing_not_owned",
          message: diagnostics[0].message,
          diagnostics,
        }),
      );
    const coordinator = new PlanSaveCoordinator(initial, { send });
    coordinator.enqueue(intents);
    await waitFor(() => expect(coordinator.getSnapshot().status).toBe("error"));
    expect(coordinator.getSnapshot().acknowledged).toEqual(initial);
    expect(coordinator.getSnapshot().displayPlan).toEqual(initial);
    expect(coordinator.getSnapshot().rejection).toEqual({
      intents,
      diagnostics,
    });
    expect(send).toHaveBeenCalledTimes(1);
    coordinator.enqueue([
      ...intents,
      { kind: "remove_transfer", decision_id: "downstream" },
    ]);
    await waitFor(() => expect(coordinator.getSnapshot().status).toBe("saved"));
    expect(send.mock.calls[1][1].intents).toEqual([
      ...intents,
      { kind: "remove_transfer", decision_id: "downstream" },
    ]);
    expect(send.mock.calls[1][1].expected_revision).toBe(0);
    expect(coordinator.getSnapshot().rejection).toBeNull();
  });

  it("dispatches field-only queued edits at the latest acknowledged revision", async () => {
    const initial = buildPlannerPlan();
    const release = deferred<void>();
    const server = createPlannerFixture(
      initial,
      (plan, intents: PlanIntent[]) => ({
        ...plan,
        name: intents[0].kind === "rename_plan" ? intents[0].name : plan.name,
      }),
    );
    const send = vi.fn(
      async (planId: number, envelope: PlanMutationEnvelope) => {
        if (send.mock.calls.length === 1) await release.promise;
        return {
          ...server.mutate(envelope),
          mutation_id: envelope.mutation_id,
          candidate: null,
        };
      },
    );
    const coordinator = new PlanSaveCoordinator(initial, { send });
    coordinator.enqueue([
      { kind: "change_captain", gameweek_number: 12, player_id: 4 },
    ]);
    coordinator.enqueue([
      { kind: "change_vice_captain", gameweek_number: 12, player_id: 5 },
    ]);
    expect(send).toHaveBeenCalledTimes(1);
    const first = structuredClone(send.mock.calls[0][1]);
    expect(coordinator.getSnapshot().acknowledged.revision).toBe(0);
    release.resolve();
    await waitFor(() => expect(coordinator.getSnapshot().status).toBe("saved"));
    expect(send).toHaveBeenCalledTimes(2);
    expect(send.mock.calls[0][1]).toEqual(first);
    expect(send.mock.calls[1][1]).toMatchObject({
      expected_revision: 1,
      intents: [
        { kind: "change_vice_captain", gameweek_number: 12, player_id: 5 },
      ],
    });
    expect(coordinator.getSnapshot().acknowledged.revision).toBe(2);
  });

  it("keeps accepted unsaved state and pauses dependent edits until same-ID retry", async () => {
    const initial = buildPlannerPlan();
    const candidate = { ...initial, name: "Accepted name" };
    const server = createPlannerFixture(initial, (plan) => ({
      ...plan,
      name: "Accepted name",
    }));
    const send = vi
      .fn(async (planId: number, envelope: PlanMutationEnvelope) => ({
        ...server.mutate(envelope),
        mutation_id: envelope.mutation_id,
        candidate: null,
      }))
      .mockRejectedValueOnce(
        new PlannerMutationError(503, {
          code: "accepted_not_saved",
          message: "Accepted edit is not saved",
          plan: initial,
          candidate,
        }),
      );
    const coordinator = new PlanSaveCoordinator(initial, { send });
    coordinator.enqueue([{ kind: "rename_plan", name: "Accepted name" }]);
    await waitFor(() =>
      expect(coordinator.getSnapshot().status).toBe("not_saved"),
    );
    coordinator.enqueue([
      { kind: "change_captain", gameweek_number: 13, player_id: 4 },
    ]);
    expect(send).toHaveBeenCalledTimes(1);
    expect(coordinator.getSnapshot().displayPlan.name).toBe("Accepted name");
    const frozen = structuredClone(send.mock.calls[0][1]);
    coordinator.retry();
    await waitFor(() => expect(coordinator.getSnapshot().status).toBe("saved"));
    expect(send.mock.calls[1][1]).toEqual(frozen);
    expect(send.mock.calls[2][1].expected_revision).toBe(1);
  });

  it("reconciles lost responses using the original ID and never commits twice", async () => {
    const initial = buildPlannerPlan();
    const server = createPlannerFixture(initial, (plan) => ({
      ...plan,
      name: "Committed",
    }));
    const send = vi.fn(
      async (planId: number, envelope: PlanMutationEnvelope) => {
        const result = server.mutate(envelope);
        if (send.mock.calls.length === 1) throw new Error("Response lost");
        return {
          ...result,
          mutation_id: envelope.mutation_id,
          candidate: null,
        };
      },
    );
    const coordinator = new PlanSaveCoordinator(initial, { send });
    coordinator.enqueue([{ kind: "rename_plan", name: "Committed" }]);
    await waitFor(() =>
      expect(coordinator.getSnapshot().status).toBe("not_saved"),
    );
    coordinator.retry();
    await waitFor(() => expect(coordinator.getSnapshot().status).toBe("saved"));
    expect(send.mock.calls[1][1]).toEqual(send.mock.calls[0][1]);
    expect(server.read().revision).toBe(1);
  });

  it("retains stale conflict context without blind overwrite or PATCH fallback", async () => {
    const initial = buildPlannerPlan();
    const send = vi.fn().mockRejectedValue(
      new PlannerMutationError(409, {
        code: "revision_conflict",
        message: "Plan revision has advanced",
        plan: { ...initial, revision: 1 },
      }),
    );
    const coordinator = new PlanSaveCoordinator(initial, { send });
    coordinator.enqueue([{ kind: "rename_plan", name: "Local" }]);
    await waitFor(() =>
      expect(coordinator.getSnapshot().status).toBe("conflict"),
    );
    coordinator.enqueue([
      { kind: "change_captain", gameweek_number: 12, player_id: 4 },
    ]);
    expect(send).toHaveBeenCalledTimes(1);
    expect(coordinator.getSnapshot().inFlight?.intents).toEqual([
      { kind: "rename_plan", name: "Local" },
    ]);
  });
});

function committed(
  server: ReturnType<typeof createPlannerFixture<PlanResponse, PlanIntent>>,
) {
  return async (_planId: number, envelope: PlanMutationEnvelope) => ({
    ...server.mutate(envelope),
    mutation_id: envelope.mutation_id,
    candidate: null,
  });
}

const rejection = (message = "Rejected") =>
  new PlannerMutationError(422, {
    code: "formation",
    message,
    diagnostics: [
      {
        code: "formation",
        message,
        gameweek_number: 12,
        decision_id: null,
        conflicting_gameweek: null,
        player_id: 4,
      },
    ],
  });

describe("US5 PlanSaveCoordinator persistence contract", () => {
  it("rebases vice D onto the acknowledged revision after delayed captain C and keeps C", async () => {
    const initial = buildPlannerPlan();
    const server = createPlannerFixture<PlanResponse, PlanIntent>(
      initial,
      applyPlannerIntents,
    );
    const gate = deferred<void>();
    const send = vi.fn(
      async (planId: number, envelope: PlanMutationEnvelope) => {
        if (send.mock.calls.length === 1) await gate.promise;
        return committed(server)(planId, envelope);
      },
    );
    const coordinator = new PlanSaveCoordinator(initial, { send });
    coordinator.enqueue([
      { kind: "change_captain", gameweek_number: 12, player_id: 4 },
    ]);
    coordinator.enqueue([
      { kind: "change_vice_captain", gameweek_number: 12, player_id: 5 },
    ]);
    expect(send).toHaveBeenCalledTimes(1);
    expect(coordinator.getSnapshot()).toMatchObject({
      status: "saving",
      pendingCount: 1,
    });
    expect(coordinator.getSnapshot().displayPlan).toEqual(initial);
    gate.resolve();
    await waitFor(() => expect(coordinator.getSnapshot().status).toBe("saved"));
    expect(send.mock.calls.map((call) => call[1].intents)).toEqual([
      [{ kind: "change_captain", gameweek_number: 12, player_id: 4 }],
      [{ kind: "change_vice_captain", gameweek_number: 12, player_id: 5 }],
    ]);
    expect(send.mock.calls.map((call) => call[1].expected_revision)).toEqual([
      0, 1,
    ]);
    const roles = coordinator.getSnapshot().acknowledged.gameweeks[0].players;
    expect(roles.find((player) => player.is_captain)?.player_id).toBe(4);
    expect(roles.find((player) => player.is_vice_captain)?.player_id).toBe(5);
  });

  it("rebases the next edit onto unchanged state after a rejected predecessor and keeps the rejection visible meanwhile", async () => {
    const initial = buildPlannerPlan();
    const server = createPlannerFixture<PlanResponse, PlanIntent>(
      initial,
      applyPlannerIntents,
    );
    const gate = deferred<void>();
    const send = vi
      .fn(async (planId: number, envelope: PlanMutationEnvelope) => {
        if (send.mock.calls.length === 2) await gate.promise;
        return committed(server)(planId, envelope);
      })
      .mockRejectedValueOnce(rejection("Illegal formation"));
    const coordinator = new PlanSaveCoordinator(initial, { send });
    const illegal: PlanIntent = {
      kind: "change_captain",
      gameweek_number: 12,
      player_id: 4,
    };
    coordinator.enqueue([illegal]);
    coordinator.enqueue([{ kind: "rename_plan", name: "After" }]);
    await waitFor(() => expect(send).toHaveBeenCalledTimes(2));
    expect(send.mock.calls[1][1]).toMatchObject({
      expected_revision: 0,
      intents: [{ kind: "rename_plan", name: "After" }],
    });
    const meanwhile = coordinator.getSnapshot();
    expect(meanwhile.status).toBe("saving");
    expect(meanwhile.rejection?.intents).toEqual([illegal]);
    expect(meanwhile.message).toBe("Illegal formation");
    expect(meanwhile.acknowledged.revision).toBe(0);
    gate.resolve();
    await waitFor(() => expect(coordinator.getSnapshot().status).toBe("saved"));
    expect(coordinator.getSnapshot().rejection).toBeNull();
    expect(coordinator.getSnapshot().acknowledged.name).toBe("After");
    expect(send).toHaveBeenCalledTimes(2);
  });

  it("surfaces a vanished target for reselection without stranding later queued edits", async () => {
    const initial = buildPlannerPlan();
    const server = createPlannerFixture<PlanResponse, PlanIntent>(
      initial,
      applyPlannerIntents,
    );
    const gate = deferred<void>();
    const send = vi.fn(
      async (planId: number, envelope: PlanMutationEnvelope) => {
        if (send.mock.calls.length === 1) await gate.promise;
        return committed(server)(planId, envelope);
      },
    );
    const coordinator = new PlanSaveCoordinator(initial, { send });
    const vanished: PlanIntent = {
      kind: "change_captain",
      gameweek_number: 12,
      player_id: 99,
    };
    const gone: PlanIntent = {
      kind: "remove_transfer",
      decision_id: "no-such-decision",
    };
    coordinator.enqueue([{ kind: "rename_plan", name: "First" }]);
    coordinator.enqueue([vanished]);
    coordinator.enqueue([gone]);
    coordinator.enqueue([{ kind: "rename_plan", name: "Second" }]);
    gate.resolve();
    await waitFor(() => expect(coordinator.getSnapshot().status).toBe("saved"));
    expect(send.mock.calls.map((call) => call[1].intents)).toEqual([
      [{ kind: "rename_plan", name: "First" }],
      [{ kind: "rename_plan", name: "Second" }],
    ]);
    const snapshot = coordinator.getSnapshot();
    expect(snapshot.pendingCount).toBe(0);
    expect(snapshot.acknowledged.name).toBe("Second");
    expect(snapshot.skipped?.map((item) => item.intents)).toEqual([
      [vanished],
      [gone],
    ]);
    expect(snapshot.skipped?.[0].reason).toMatch(
      /select the intended player again/i,
    );
    expect(snapshot.skipped?.[1].reason).toMatch(/select it again/i);
    coordinator.enqueue([{ kind: "rename_plan", name: "Third" }]);
    expect(coordinator.getSnapshot().skipped).toBeNull();
  });

  it("never regresses acknowledged state to an older revision or accepts a mismatched acknowledgement", async () => {
    const initial = { ...buildPlannerPlan(), revision: 3 };
    const older = vi.fn(
      async (_planId: number, envelope: PlanMutationEnvelope) => ({
        status: "committed" as const,
        mutation_id: envelope.mutation_id,
        committed_revision: 4,
        plan: { ...initial, name: "Older copy", revision: 2 },
        candidate: null,
      }),
    );
    const regress = new PlanSaveCoordinator(initial, { send: older });
    regress.enqueue([{ kind: "rename_plan", name: "A" }]);
    await waitFor(() => expect(regress.getSnapshot().status).toBe("saved"));
    expect(regress.getSnapshot().acknowledged).toEqual(initial);
    const mismatched = vi.fn(async () => ({
      status: "committed" as const,
      mutation_id: "someone-else",
      committed_revision: 4,
      plan: { ...initial, name: "Foreign", revision: 4 },
      candidate: null,
    }));
    const foreign = new PlanSaveCoordinator(initial, { send: mismatched });
    foreign.enqueue([{ kind: "rename_plan", name: "B" }]);
    await waitFor(() => expect(foreign.getSnapshot().status).toBe("not_saved"));
    expect(foreign.getSnapshot().acknowledged).toEqual(initial);
    expect(foreign.getSnapshot().displayPlan).toEqual(initial);
    expect(foreign.getSnapshot().inFlight?.intents).toEqual([
      { kind: "rename_plan", name: "B" },
    ]);
    expect(mismatched).toHaveBeenCalledTimes(1);
  });

  it("keeps each plan's coordinator and pending state when switching plans", async () => {
    const { getPlanSaveCoordinator } =
      await import("@/lib/plan-save-coordinator");
    const first = buildPlannerPlan();
    const second = buildPlannerPlan();
    const gate = deferred<void>();
    const coordinatorA = getPlanSaveCoordinator(first);
    const originalSend = vi.fn(async () => {
      await gate.promise;
      throw new Error("lost");
    });
    (
      coordinatorA as unknown as { transport: { send: typeof originalSend } }
    ).transport.send = originalSend;
    coordinatorA.enqueue([{ kind: "rename_plan", name: "Pending on A" }]);
    const coordinatorB = getPlanSaveCoordinator(second);
    expect(coordinatorB).not.toBe(coordinatorA);
    expect(coordinatorB.getSnapshot()).toMatchObject({
      status: "saved",
      pendingCount: 0,
      inFlight: null,
    });
    expect(
      getPlanSaveCoordinator({ ...first, name: "Older server copy" }),
    ).toBe(coordinatorA);
    expect(coordinatorA.getSnapshot().acknowledged.name).toBe(first.name);
    expect(coordinatorA.getSnapshot().inFlight?.intents).toEqual([
      { kind: "rename_plan", name: "Pending on A" },
    ]);
    gate.resolve();
    await waitFor(() =>
      expect(coordinatorA.getSnapshot().status).toBe("not_saved"),
    );
    expect(coordinatorB.getSnapshot().status).toBe("saved");
  });

  it("acknowledges a committed retry with a newer current plan without overlaying the original candidate", async () => {
    const initial = buildPlannerPlan();
    const current = {
      ...buildPlannerPlan(),
      plan_id: initial.plan_id,
      name: "Other tab",
      revision: 4,
    };
    const stale = { ...initial, name: "Old candidate", revision: 1 };
    const send = vi.fn().mockResolvedValue({
      status: "already_committed",
      mutation_id: "",
      committed_revision: 1,
      plan: current,
      candidate: stale,
    });
    const coordinator = new PlanSaveCoordinator(initial, {
      send: async (planId, envelope) => ({
        ...(await send(planId, envelope)),
        mutation_id: envelope.mutation_id,
      }),
    });
    coordinator.enqueue([{ kind: "rename_plan", name: "Mine" }]);
    await waitFor(() => expect(coordinator.getSnapshot().status).toBe("saved"));
    expect(coordinator.getSnapshot().acknowledged).toEqual(current);
    expect(coordinator.getSnapshot().displayPlan).toEqual(current);
  });

  it("reconciles a lost success by the same ID without a second POST and adopts the newer plan", async () => {
    const initial = buildPlannerPlan();
    const current = { ...initial, name: "Committed", revision: 3 };
    const send = vi.fn().mockRejectedValue(new Error("Response lost"));
    const receipt = vi.fn(async (_planId: number, id: string) => ({
      status: "already_committed" as const,
      mutation_id: id,
      committed_revision: 1,
      plan: current,
      candidate: null,
    }));
    const coordinator = new PlanSaveCoordinator(initial, { send, receipt });
    coordinator.enqueue([{ kind: "rename_plan", name: "Committed" }]);
    await waitFor(() =>
      expect(coordinator.getSnapshot().status).toBe("not_saved"),
    );
    const id = coordinator.getSnapshot().inFlight!.mutation_id;
    await coordinator.reconcile();
    expect(receipt).toHaveBeenCalledWith(initial.plan_id, id);
    expect(send).toHaveBeenCalledTimes(1);
    expect(coordinator.getSnapshot()).toMatchObject({
      status: "saved",
      inFlight: null,
    });
    expect(coordinator.getSnapshot().acknowledged).toEqual(current);
  });

  it("treats an unknown receipt 404 as inconclusive and keeps the same ID for retry or reconcile", async () => {
    const initial = buildPlannerPlan();
    const server = createPlannerFixture<PlanResponse, PlanIntent>(
      initial,
      applyPlannerIntents,
    );
    const send = vi
      .fn(committed(server))
      .mockRejectedValueOnce(new Error("Response lost"));
    const receipt = vi.fn().mockRejectedValue(
      new PlannerMutationError(404, {
        code: "mutation_not_found",
        message: "Mutation receipt is not known",
      }),
    );
    const coordinator = new PlanSaveCoordinator(initial, { send, receipt });
    coordinator.enqueue([{ kind: "rename_plan", name: "Maybe" }]);
    await waitFor(() =>
      expect(coordinator.getSnapshot().status).toBe("not_saved"),
    );
    const original = coordinator.getSnapshot().inFlight!;
    await coordinator.reconcile();
    expect(coordinator.getSnapshot().status).toBe("not_saved");
    expect(coordinator.getSnapshot().message).toMatch(/not confirmed|retry/i);
    expect(coordinator.getSnapshot().inFlight).toBe(original);
    await coordinator.revalidate();
    expect(send).toHaveBeenCalledTimes(1);
    coordinator.retry();
    await waitFor(() => expect(coordinator.getSnapshot().status).toBe("saved"));
    expect(send.mock.calls[1][1]).toEqual(original);
    expect(server.read().revision).toBe(1);
  });

  it("stops dependent writes when the plan no longer exists and never invents a new ID", async () => {
    const initial = buildPlannerPlan();
    const send = vi.fn().mockRejectedValue(
      new PlannerMutationError(404, {
        code: "plan_not_found",
        message: "Plan not found",
      }),
    );
    const load = vi.fn().mockResolvedValue(null);
    const coordinator = new PlanSaveCoordinator(initial, { send, load });
    coordinator.enqueue([{ kind: "rename_plan", name: "Orphan" }]);
    coordinator.enqueue([
      { kind: "change_captain", gameweek_number: 12, player_id: 4 },
    ]);
    await waitFor(() =>
      expect(coordinator.getSnapshot().status).toBe("missing"),
    );
    const original = coordinator.getSnapshot().inFlight;
    coordinator.enqueue([{ kind: "rename_plan", name: "Later" }]);
    coordinator.retry();
    await coordinator.revalidate();
    expect(send).toHaveBeenCalledTimes(1);
    expect(coordinator.getSnapshot().status).toBe("missing");
    expect(coordinator.getSnapshot().inFlight).toBe(original);
    expect(coordinator.getSnapshot().message).toMatch(/no longer exists/i);
  });

  it("requires explicit new-ID reconciliation after stale pending metadata and shows no reconstructed candidate", async () => {
    const initial = buildPlannerPlan();
    const fresh = { ...initial, name: "Fresh", revision: 2 };
    const old = {
      ...initial,
      name: "Reconstructed old candidate",
      revision: 0,
    };
    const server = createPlannerFixture<PlanResponse, PlanIntent>(
      fresh,
      applyPlannerIntents,
    );
    const send = vi.fn(committed(server)).mockRejectedValueOnce(
      new PlannerMutationError(409, {
        code: "stale_reprepare_required",
        message: "Accepted inputs need explicit revalidation with a new ID",
        plan: fresh,
        candidate: old,
        intent_metadata: { operations: [] },
      }),
    );
    const load = vi.fn().mockResolvedValue(fresh);
    const coordinator = new PlanSaveCoordinator(initial, { send, load });
    coordinator.enqueue([{ kind: "rename_plan", name: "Mine" }]);
    await waitFor(() =>
      expect(coordinator.getSnapshot().status).toBe("conflict"),
    );
    const stale = coordinator.getSnapshot();
    expect(stale.displayPlan).toEqual(fresh);
    expect(stale.acknowledged).toEqual(fresh);
    expect(send).toHaveBeenCalledTimes(1);
    const staleId = stale.inFlight!.mutation_id;
    await coordinator.revalidate();
    await waitFor(() => expect(coordinator.getSnapshot().status).toBe("saved"));
    expect(send.mock.calls[1][1].mutation_id).not.toBe(staleId);
    expect(send.mock.calls[1][1]).toMatchObject({
      expected_revision: 2,
      intents: [{ kind: "rename_plan", name: "Mine" }],
    });
    expect(coordinator.getSnapshot().acknowledged.revision).toBe(3);
  });
});
