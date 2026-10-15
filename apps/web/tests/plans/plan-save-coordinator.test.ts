import { waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  PlanIntent,
  PlanMutationEnvelope,
  PlannerMutationError,
} from "@/lib/api";
import { PlanSaveCoordinator } from "@/lib/plan-save-coordinator";
import {
  buildPlannerPlan,
  createPlannerFixture,
  deferred,
} from "../fixtures/planner";

describe("PlanSaveCoordinator", () => {
  it("US3 discards rejected repair context when synchronization advances the accepted revision", async () => {
    const initial = buildPlannerPlan();
    const send = vi
      .fn()
      .mockRejectedValue(
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
    const initial = buildPlannerPlan();
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
