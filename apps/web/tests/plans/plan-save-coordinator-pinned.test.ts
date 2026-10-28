import { waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  PlanIntent,
  PlanMutationEnvelope,
  PlanMutationResponse,
  PlanResponse,
  PlannerMutationError,
} from "@/lib/api";
import {
  PlanSaveCoordinator,
  getPlanSaveCoordinator,
} from "@/lib/plan-save-coordinator";
import {
  buildPlannerPlan,
  deferred,
  plannerIdentity,
} from "../fixtures/planner";

const DIAGNOSTIC = {
  code: "prices_changed",
  message: "Prices changed since the preview",
  gameweek_number: 12,
  decision_id: null,
  conflicting_gameweek: null,
  player_id: 106,
};

function transfer(overrides: Partial<PlanIntent> = {}): PlanIntent {
  return {
    kind: "add_transfer",
    gameweek_number: 12,
    outgoing_player_id: 6,
    outgoing_ownership_id: plannerIdentity(1006),
    incoming_player_id: 106,
    expected_outgoing_market_tenths: 54,
    expected_incoming_price_tenths: 50,
    ...overrides,
  } as PlanIntent;
}

function committed(
  plan: PlanResponse,
  mutationId: string,
  revision: number,
  status: PlanMutationResponse["status"] = "committed",
): PlanMutationResponse {
  return {
    status,
    mutation_id: mutationId,
    committed_revision: revision,
    plan: { ...plan, revision },
    candidate: null,
  };
}

function setup(plan = buildPlannerPlan()) {
  const send =
    vi.fn<
      (
        planId: number,
        envelope: PlanMutationEnvelope,
      ) => Promise<PlanMutationResponse>
    >();
  const receipt =
    vi.fn<
      (planId: number, mutationId: string) => Promise<PlanMutationResponse>
    >();
  const load = vi.fn<(planId: number) => Promise<PlanResponse | null>>();
  const coordinator = new PlanSaveCoordinator(plan, { send, receipt, load });
  return { plan, send, receipt, load, coordinator };
}

function pinnedStatus(coordinator: PlanSaveCoordinator) {
  return coordinator.getSnapshot().pinned?.status;
}

function submit(coordinator: PlanSaveCoordinator, expectedRevision = 0) {
  return coordinator.submitPinned({
    intents: [transfer()],
    expectedRevision,
  });
}

function rename(coordinator: PlanSaveCoordinator, name = "Renamed") {
  coordinator.enqueue([{ kind: "rename_plan", name }]);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PlanSaveCoordinator pinned submission", () => {
  it("C1 sends the previewed intents once, pinned to the previewed revision", () => {
    const { coordinator, send, plan } = setup();
    send.mockReturnValue(new Promise(() => {}));

    const result = submit(coordinator);

    expect(result.type).toBe("started");
    expect(send).toHaveBeenCalledTimes(1);
    const envelope = send.mock.calls[0][1];
    expect(envelope.expected_revision).toBe(0);
    expect(envelope.intents).toEqual([transfer()]);
    const snapshot = coordinator.getSnapshot();
    expect(snapshot.pinned).toMatchObject({
      status: "sending",
      mutationId: envelope.mutation_id,
      expectedRevision: 0,
    });
    expect(snapshot.status).toBe("saving");
    expect(snapshot.inFlight?.mutation_id).toBe(envelope.mutation_id);
    expect(coordinator.hasUnsavedWork()).toBe(true);
    expect(plan.revision).toBe(0);
  });

  it("C2 refuses a stale preview without sending or queueing anything", async () => {
    const { coordinator, send, plan } = setup();
    coordinator.synchronize({ ...plan, revision: 1 });

    const result = submit(coordinator, 0);

    expect(result).toEqual({ type: "refused", reason: "stale_preview" });
    expect(send).not.toHaveBeenCalled();
    expect(coordinator.getSnapshot().pendingCount).toBe(0);
    expect(coordinator.getSnapshot().pinned).toBeNull();

    send.mockImplementation(async (_id, envelope) =>
      committed(plan, envelope.mutation_id, 2),
    );
    rename(coordinator);
    await waitFor(() =>
      expect(coordinator.getSnapshot().acknowledged.revision).toBe(2),
    );
    expect(submit(coordinator, 1)).toEqual({
      type: "refused",
      reason: "stale_preview",
    });
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("C3 refuses while a save is active or edits are queued, leaving both untouched", () => {
    const { coordinator, send } = setup();
    send.mockReturnValue(new Promise(() => {}));
    rename(coordinator, "First");
    rename(coordinator, "Second");
    const before = coordinator.getSnapshot();

    expect(submit(coordinator)).toEqual({ type: "refused", reason: "busy" });

    const after = coordinator.getSnapshot();
    expect(send).toHaveBeenCalledTimes(1);
    expect(after.inFlight).toBe(before.inFlight);
    expect(after.pendingCount).toBe(1);
    expect(after.pinned).toBeNull();
  });

  it("C4 allows one pinned submission at a time", () => {
    const { coordinator, send } = setup();
    send.mockReturnValue(new Promise(() => {}));
    expect(submit(coordinator).type).toBe("started");

    expect(submit(coordinator)).toEqual({
      type: "refused",
      reason: "pinned_exists",
    });
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("C5 refuses intents that no longer resolve, without retargeting", () => {
    const { coordinator, send } = setup();

    const result = coordinator.submitPinned({
      intents: [transfer({ outgoing_player_id: 99 } as Partial<PlanIntent>)],
      expectedRevision: 0,
    });

    expect(result).toEqual({ type: "refused", reason: "stale_preview" });
    expect(send).not.toHaveBeenCalled();
    expect(coordinator.getSnapshot().pinned).toBeNull();
  });

  it("C5 refuses before the plan is ready or after it vanished", async () => {
    const legacy = buildPlannerPlan();
    legacy.foundation_state = "legacy_pending";
    expect(submit(setup(legacy).coordinator)).toEqual({
      type: "refused",
      reason: "not_ready",
    });

    const { coordinator, send } = setup();
    send.mockRejectedValue(
      new PlannerMutationError(404, {
        code: "plan_not_found",
        message: "gone",
      }),
    );
    rename(coordinator);
    await waitFor(() =>
      expect(coordinator.getSnapshot().status).toBe("missing"),
    );
    expect(submit(coordinator)).toEqual({
      type: "refused",
      reason: "plan_missing",
    });
  });

  it("C6 never reports success for another mutation's acknowledgement or a revision change", async () => {
    const { coordinator, send, plan } = setup();
    const response = deferred<PlanMutationResponse>();
    send.mockReturnValue(response.promise);
    submit(coordinator);

    coordinator.synchronize({ ...plan, revision: 5 });
    expect(pinnedStatus(coordinator)).toBe("sending");
    expect(coordinator.getSnapshot().acknowledged.revision).toBe(0);

    response.resolve(committed(plan, "someone-elses-mutation", 1));
    await waitFor(() => expect(pinnedStatus(coordinator)).toBe("unknown"));
    expect(coordinator.getSnapshot().acknowledged.revision).toBe(0);
  });

  it.each(["committed", "already_committed"] as const)(
    "C7 reports %s only for its own mutation identity",
    async (status) => {
      const { coordinator, send, plan } = setup();
      send.mockImplementation(async (_id, envelope) =>
        committed(plan, envelope.mutation_id, 1, status),
      );

      const started = submit(coordinator);

      await waitFor(() => expect(pinnedStatus(coordinator)).toBe("committed"));
      const snapshot = coordinator.getSnapshot();
      if (started.type !== "started") throw new Error("not started");
      expect(snapshot.pinned).toMatchObject({
        submissionId: started.submissionId,
        committedRevision: 1,
      });
      expect(snapshot.acknowledged.revision).toBe(1);
      expect(snapshot.inFlight).toBeNull();
      expect(snapshot.status).toBe("saved");
      expect(coordinator.hasUnsavedWork()).toBe(false);
    },
  );

  it("C8 keeps a 422 rejection with its code and diagnostics and resumes queued edits unchanged", async () => {
    const { coordinator, send, plan } = setup();
    send
      .mockRejectedValueOnce(
        new PlannerMutationError(422, {
          code: "prices_changed",
          message: "Prices changed since the preview",
          diagnostics: [DIAGNOSTIC],
        }),
      )
      .mockImplementation(async (_id, envelope) =>
        committed(plan, envelope.mutation_id, 1),
      );
    submit(coordinator);
    rename(coordinator, "Queued behind the transfer");

    await waitFor(() =>
      expect(coordinator.getSnapshot().acknowledged.revision).toBe(1),
    );

    expect(coordinator.getSnapshot().pinned).toMatchObject({
      status: "rejected",
      code: "prices_changed",
      message: "Prices changed since the preview",
      diagnostics: [DIAGNOSTIC],
    });
    expect(send).toHaveBeenCalledTimes(2);
    expect(send.mock.calls[1][1].intents).toEqual([
      { kind: "rename_plan", name: "Queued behind the transfer" },
    ]);
    expect(send.mock.calls[1][1].expected_revision).toBe(0);
    expect(coordinator.hasUnsavedWork()).toBe(false);
  });

  it.each([
    [409, "revision_conflict"],
    [409, "stale_reprepare_required"],
    [410, "planner_writer_retired"],
  ])(
    "C9 treats %s %s as a known conflict that is never replayed",
    async (status, code) => {
      const { coordinator, send, load, plan } = setup();
      send.mockRejectedValue(
        new PlannerMutationError(status, {
          code,
          message: "conflict",
          plan: { ...plan, revision: 4 },
        }),
      );
      load.mockResolvedValue({ ...plan, revision: 4 });
      submit(coordinator);
      await waitFor(() => expect(pinnedStatus(coordinator)).toBe("conflict"));

      coordinator.retry();
      expect(send).toHaveBeenCalledTimes(1);
      expect(coordinator.hasUnsavedWork()).toBe(true);
      expect(coordinator.getSnapshot().status).toBe("conflict");

      await coordinator.revalidate();

      expect(send).toHaveBeenCalledTimes(1);
      expect(coordinator.getSnapshot().pinned).toBeNull();
      expect(coordinator.getSnapshot().acknowledged.revision).toBe(4);
      expect(coordinator.hasUnsavedWork()).toBe(false);
    },
  );

  describe("C10 unknown outcomes", () => {
    const failures: [string, () => Error][] = [
      ["a network failure", () => new TypeError("Failed to fetch")],
      [
        "503 outcome_unknown",
        () =>
          new PlannerMutationError(503, {
            code: "outcome_unknown",
            message: "?",
          }),
      ],
      [
        "503 not_accepted",
        () =>
          new PlannerMutationError(503, { code: "not_accepted", message: "?" }),
      ],
      [
        "409 mutation_id_reused",
        () =>
          new PlannerMutationError(409, {
            code: "mutation_id_reused",
            message: "?",
          }),
      ],
    ];

    it.each(failures)(
      "%s leaves the outcome unknown and not abandonable",
      async (_name, error) => {
        const { coordinator, send, load, receipt } = setup();
        send.mockRejectedValue(error());
        submit(coordinator);
        await waitFor(() => expect(pinnedStatus(coordinator)).toBe("unknown"));

        const result = await coordinator.abandon();

        expect(result).toEqual({ type: "refused", reason: "reconcile_first" });
        expect(coordinator.getSnapshot().pinned?.status).toBe("unknown");
        expect(coordinator.hasUnsavedWork()).toBe(true);
        expect(load).not.toHaveBeenCalled();
        expect(receipt).not.toHaveBeenCalled();
      },
    );

    it("retries with the same identity and the same pinned revision", async () => {
      const { coordinator, send, plan } = setup();
      send.mockRejectedValueOnce(new TypeError("Failed to fetch"));
      send.mockImplementation(async (_id, envelope) =>
        committed(plan, envelope.mutation_id, 1),
      );
      submit(coordinator);
      await waitFor(() => expect(pinnedStatus(coordinator)).toBe("unknown"));

      coordinator.retry();

      await waitFor(() => expect(pinnedStatus(coordinator)).toBe("committed"));
      expect(send).toHaveBeenCalledTimes(2);
      expect(send.mock.calls[1][1]).toEqual(send.mock.calls[0][1]);
    });

    it("reconciles by its own identity: committed, or still unknown on a 404", async () => {
      const { coordinator, send, receipt, plan } = setup();
      send.mockRejectedValue(new TypeError("Failed to fetch"));
      receipt.mockRejectedValueOnce(
        new PlannerMutationError(404, {
          code: "mutation_not_found",
          message: "?",
        }),
      );
      submit(coordinator);
      await waitFor(() => expect(pinnedStatus(coordinator)).toBe("unknown"));

      await coordinator.reconcile();
      expect(pinnedStatus(coordinator)).toBe("unknown");

      receipt.mockImplementation(async (_id, mutationId) =>
        committed(plan, mutationId, 1, "already_committed"),
      );
      await coordinator.reconcile();
      expect(pinnedStatus(coordinator)).toBe("committed");
      expect(receipt.mock.calls[0][1]).toBe(send.mock.calls[0][1].mutation_id);
    });
  });

  it("C11 holds an accepted-but-not-saved transfer as pending, retried only with the same identity", async () => {
    const { coordinator, send, plan } = setup();
    send.mockRejectedValueOnce(
      new PlannerMutationError(503, {
        code: "accepted_not_saved",
        message: "not saved",
      }),
    );
    send.mockImplementation(async (_id, envelope) =>
      committed(plan, envelope.mutation_id, 1),
    );
    submit(coordinator);
    await waitFor(() =>
      expect(pinnedStatus(coordinator)).toBe("pending_unsaved"),
    );
    expect(coordinator.hasUnsavedWork()).toBe(true);
    expect(coordinator.getSnapshot().status).toBe("not_saved");

    coordinator.retry();

    await waitFor(() => expect(pinnedStatus(coordinator)).toBe("committed"));
    expect(send.mock.calls[1][1].mutation_id).toBe(
      send.mock.calls[0][1].mutation_id,
    );
  });

  it("C12 refuses to abandon while the outcome is in flight", async () => {
    const { coordinator, send, load, plan } = setup();
    const response = deferred<PlanMutationResponse>();
    send.mockReturnValue(response.promise);
    submit(coordinator);

    const result = await coordinator.abandon();

    expect(result).toEqual({ type: "refused", reason: "outcome_pending" });
    expect(coordinator.getSnapshot().pinned?.status).toBe("sending");
    expect(load).not.toHaveBeenCalled();
    response.resolve(committed(plan, send.mock.calls[0][1].mutation_id, 1));
    await waitFor(() => expect(pinnedStatus(coordinator)).toBe("committed"));
  });

  describe("C13 abandoning a known no-write outcome", () => {
    const outcomes: [string, Error][] = [
      [
        "conflict",
        new PlannerMutationError(409, {
          code: "revision_conflict",
          message: "stale",
        }),
      ],
      [
        "pending_unsaved",
        new PlannerMutationError(503, {
          code: "accepted_not_saved",
          message: "not saved",
        }),
      ],
    ];

    it.each(outcomes)(
      "refreshes the plan and clears only the pinned submission after %s",
      async (status, error) => {
        const { coordinator, send, load, receipt, plan } = setup();
        send.mockRejectedValue(error);
        load.mockResolvedValue({
          ...plan,
          revision: 3,
          name: "Fresh from the server",
        });
        submit(coordinator);
        await waitFor(() => expect(pinnedStatus(coordinator)).toBe(status));

        const result = await coordinator.abandon();

        expect(result).toMatchObject({
          type: "abandoned",
          previous: { status },
          serverReceiptRetained: status === "pending_unsaved",
        });
        const snapshot = coordinator.getSnapshot();
        expect(snapshot.pinned).toBeNull();
        expect(snapshot.inFlight).toBeNull();
        expect(snapshot.status).toBe("saved");
        expect(snapshot.acknowledged.revision).toBe(3);
        expect(snapshot.displayPlan.name).toBe("Fresh from the server");
        expect(load).toHaveBeenCalledTimes(1);
        expect(receipt).not.toHaveBeenCalled();
        expect(send).toHaveBeenCalledTimes(1);
      },
    );
  });

  it("C14 discards nothing when the refresh fails, and records a vanished plan", async () => {
    const { coordinator, send, load } = setup();
    send.mockRejectedValue(
      new PlannerMutationError(409, {
        code: "revision_conflict",
        message: "stale",
      }),
    );
    submit(coordinator);
    await waitFor(() => expect(pinnedStatus(coordinator)).toBe("conflict"));

    load.mockRejectedValueOnce(new Error("offline"));
    const failed = await coordinator.abandon();
    expect(failed).toMatchObject({ type: "refresh_failed" });
    expect(coordinator.getSnapshot().pinned?.status).toBe("conflict");
    expect(coordinator.getSnapshot().inFlight).not.toBeNull();
    expect(coordinator.hasUnsavedWork()).toBe(true);

    load.mockResolvedValueOnce(null);
    const missing = await coordinator.abandon();
    expect(missing).toMatchObject({ type: "abandoned" });
    expect(coordinator.getSnapshot().status).toBe("missing");
    expect(coordinator.getSnapshot().pinned).toBeNull();
  });

  it("C14 ignores a repeated abandon while one is in progress", async () => {
    const { coordinator, send, load, plan } = setup();
    send.mockRejectedValue(
      new PlannerMutationError(409, {
        code: "revision_conflict",
        message: "stale",
      }),
    );
    const refresh = deferred<PlanResponse | null>();
    load.mockReturnValue(refresh.promise);
    submit(coordinator);
    await waitFor(() => expect(pinnedStatus(coordinator)).toBe("conflict"));

    const first = coordinator.abandon();
    const second = coordinator.abandon();
    refresh.resolve({ ...plan, revision: 2 });

    expect(await first).toEqual(await second);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("C15 never discards queued Planner edits and rebases them onto the refreshed plan", async () => {
    const { coordinator, send, load, plan } = setup();
    send.mockRejectedValueOnce(
      new PlannerMutationError(409, {
        code: "revision_conflict",
        message: "stale",
      }),
    );
    send.mockImplementation(async (_id, envelope) =>
      committed(plan, envelope.mutation_id, 3),
    );
    load.mockResolvedValue({ ...plan, revision: 2 });
    submit(coordinator);
    rename(coordinator, "Queued while the transfer was sending");
    await waitFor(() => expect(pinnedStatus(coordinator)).toBe("conflict"));
    expect(coordinator.getSnapshot().pendingCount).toBe(1);
    expect(send).toHaveBeenCalledTimes(1);

    await coordinator.abandon();

    await waitFor(() =>
      expect(coordinator.getSnapshot().acknowledged.revision).toBe(3),
    );
    expect(send).toHaveBeenCalledTimes(2);
    expect(send.mock.calls[1][1].intents).toEqual([
      { kind: "rename_plan", name: "Queued while the transfer was sending" },
    ]);
    expect(send.mock.calls[1][1].expected_revision).toBe(2);
    expect(coordinator.getSnapshot().pendingCount).toBe(0);
  });

  it("C16 dispatches an edit enqueued during the transfer afterwards, at the then-acknowledged revision", async () => {
    const { coordinator, send, plan } = setup();
    const response = deferred<PlanMutationResponse>();
    send.mockReturnValueOnce(response.promise);
    send.mockImplementation(async (_id, envelope) =>
      committed(plan, envelope.mutation_id, 2),
    );
    submit(coordinator);
    rename(coordinator, "After");
    expect(send).toHaveBeenCalledTimes(1);

    response.resolve(committed(plan, send.mock.calls[0][1].mutation_id, 1));

    await waitFor(() =>
      expect(coordinator.getSnapshot().acknowledged.revision).toBe(2),
    );
    expect(send.mock.calls[1][1].expected_revision).toBe(1);
    expect(pinnedStatus(coordinator)).toBe("committed");
  });

  it("C17 keeps the pinned record across navigation, flagging unsaved work only while unresolved", async () => {
    const plan = buildPlannerPlan();
    const fetchMock = vi.fn(() => new Promise<Response>(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    const first = getPlanSaveCoordinator(plan);
    first.submitPinned({ intents: [transfer()], expectedRevision: 0 });

    const returned = getPlanSaveCoordinator({ ...plan });

    expect(returned).toBe(first);
    expect(returned.getSnapshot().pinned?.status).toBe("sending");
    expect(returned.hasUnsavedWork()).toBe(true);
  });

  it("C17 reports no unsaved work for a rejected record or after abandoning", async () => {
    const { coordinator, send } = setup();
    send.mockRejectedValue(
      new PlannerMutationError(422, {
        code: "prices_changed",
        message: "changed",
      }),
    );
    submit(coordinator);
    await waitFor(() => expect(pinnedStatus(coordinator)).toBe("rejected"));
    expect(coordinator.hasUnsavedWork()).toBe(false);

    await coordinator.abandon();
    expect(coordinator.hasUnsavedWork()).toBe(false);
  });

  describe("accepted-but-not-saved transfers (C19)", () => {
    it("abandoning is client-side: no mutation or receipt request, the plan lacks the transfer, and it is never committed", async () => {
      const { coordinator, send, load, receipt, plan } = setup();
      send.mockRejectedValueOnce(
        new PlannerMutationError(503, {
          code: "accepted_not_saved",
          message: "Accepted edit is not saved; retry the same mutation ID",
          plan,
          candidate: plan,
        }),
      );
      load.mockResolvedValue({ ...plan });
      submit(coordinator);
      await waitFor(() =>
        expect(pinnedStatus(coordinator)).toBe("pending_unsaved"),
      );
      const abandonedIdentity = send.mock.calls[0][1].mutation_id;

      const result = await coordinator.abandon();

      expect(result).toMatchObject({
        type: "abandoned",
        serverReceiptRetained: true,
        previous: { status: "pending_unsaved", mutationId: abandonedIdentity },
      });
      expect(send).toHaveBeenCalledTimes(1);
      expect(receipt).not.toHaveBeenCalled();
      expect(load).toHaveBeenCalledTimes(1);
      const snapshot = coordinator.getSnapshot();
      expect(snapshot.pinned).toBeNull();
      expect(
        snapshot.acknowledged.gameweeks.every(
          (week) => week.decisions.length === 0,
        ),
      ).toBe(true);
      expect(snapshot.status).toBe("saved");

      send.mockImplementation(async (_id, envelope) =>
        committed(plan, envelope.mutation_id, 1),
      );
      expect(submit(coordinator).type).toBe("started");
      expect(send.mock.calls[1][1].mutation_id).not.toBe(abandonedIdentity);
    });

    it("keeps the pending record and its message until the user retries or abandons", async () => {
      const { coordinator, send } = setup();
      send.mockRejectedValue(
        new PlannerMutationError(503, {
          code: "accepted_not_saved",
          message: "not saved",
        }),
      );
      submit(coordinator);
      await waitFor(() =>
        expect(pinnedStatus(coordinator)).toBe("pending_unsaved"),
      );

      expect(coordinator.getSnapshot().pinned?.message).toBe(
        "Accepted edit is not saved; retry the same edit",
      );
      expect(coordinator.getSnapshot().pinned?.committedRevision).toBeNull();
    });
  });

  describe("rejected submissions (C20, C21)", () => {
    async function rejected() {
      const context = setup();
      context.send.mockRejectedValueOnce(
        new PlannerMutationError(422, {
          code: "prices_changed",
          message: "Prices changed since the preview",
          diagnostics: [DIAGNOSTIC],
        }),
      );
      submit(context.coordinator);
      await waitFor(() =>
        expect(pinnedStatus(context.coordinator)).toBe("rejected"),
      );
      return context;
    }

    it("C20 is cleared by abandon with no server contact, returning the rejection to keep", async () => {
      const { coordinator, send, load, receipt } = await rejected();
      expect(coordinator.getSnapshot().status).toBe("error");

      const result = await coordinator.abandon();

      expect(result).toMatchObject({
        type: "abandoned",
        serverReceiptRetained: false,
        previous: {
          status: "rejected",
          code: "prices_changed",
          message: "Prices changed since the preview",
          diagnostics: [DIAGNOSTIC],
        },
      });
      expect(load).not.toHaveBeenCalled();
      expect(receipt).not.toHaveBeenCalled();
      expect(send).toHaveBeenCalledTimes(1);
      expect(coordinator.getSnapshot().pinned).toBeNull();
      expect(coordinator.getSnapshot().status).toBe("saved");
      expect(coordinator.hasUnsavedWork()).toBe(false);
    });

    it("C21 blocks nothing once acknowledged: a fresh submission gets a new identity and nothing is resubmitted automatically", async () => {
      const { coordinator, send, plan } = await rejected();
      const rejectedIdentity = send.mock.calls[0][1].mutation_id;
      send.mockImplementation(async (_id, envelope) =>
        committed(plan, envelope.mutation_id, 1),
      );

      expect(submit(coordinator)).toEqual({
        type: "refused",
        reason: "pinned_exists",
      });
      expect(send).toHaveBeenCalledTimes(1);

      await coordinator.abandon();
      expect(send).toHaveBeenCalledTimes(1);

      expect(submit(coordinator).type).toBe("started");
      await waitFor(() => expect(pinnedStatus(coordinator)).toBe("committed"));
      expect(send).toHaveBeenCalledTimes(2);
      expect(send.mock.calls[1][1].mutation_id).not.toBe(rejectedIdentity);
    });

    it("C21 never blocks Planner edits while the rejection is unacknowledged, and survives navigation", async () => {
      const plan = buildPlannerPlan();
      const response = new Response(
        JSON.stringify({
          detail: { code: "prices_changed", message: "Prices changed" },
        }),
        { status: 422 },
      );
      vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response));
      const coordinator = getPlanSaveCoordinator(plan);
      coordinator.submitPinned({ intents: [transfer()], expectedRevision: 0 });
      await waitFor(() => expect(pinnedStatus(coordinator)).toBe("rejected"));

      expect(
        getPlanSaveCoordinator({ ...plan }).getSnapshot().pinned?.status,
      ).toBe("rejected");
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          new Response(
            JSON.stringify({
              status: "committed",
              mutation_id: "ignored",
              committed_revision: 1,
              plan: { ...plan, revision: 1 },
              candidate: null,
            }),
          ),
        ),
      );
      rename(coordinator);

      await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1));
      expect(pinnedStatus(coordinator)).toBe("rejected");
    });
  });
});
