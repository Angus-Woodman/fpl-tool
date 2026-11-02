import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  PlannerMutationError,
  type PlanIntent,
  type PlanMutationEnvelope,
  type PlanMutationResponse,
  type PlanResponse,
} from "@/lib/api";
import { PlanSaveCoordinator } from "@/lib/plan-save-coordinator";
import { useDepartureGuard } from "@/lib/use-departure-guard";

import {
  buildPlannerPlan,
  deferred,
  plannerIdentity,
} from "../fixtures/planner";

const WARNING =
  "Your latest Planner edit is not saved yet. Leave this page anyway?";

function Guarded({
  source,
}: {
  source: Parameters<typeof useDepartureGuard>[0];
}): null {
  useDepartureGuard(source);
  return null;
}

type Reply = (envelope: PlanMutationEnvelope) => Promise<PlanMutationResponse>;

function setup(plan: PlanResponse = buildPlannerPlan(9, 14)) {
  const gate = deferred<void>();
  let reply: Reply = async (envelope) => {
    await gate.promise;
    return {
      status: "committed",
      mutation_id: envelope.mutation_id,
      committed_revision: plan.revision + 1,
      plan: { ...plan, revision: plan.revision + 1 },
      candidate: null,
    };
  };
  const coordinator = new PlanSaveCoordinator(plan, {
    send: (_planId, envelope) => reply(envelope),
    receipt: async () => {
      throw new Error("not used");
    },
    load: async () => plan,
  });
  return {
    plan,
    gate,
    coordinator,
    replyWith: (next: Reply) => {
      reply = next;
    },
  };
}

function transfer(): PlanIntent {
  return {
    kind: "add_transfer",
    gameweek_number: 9,
    outgoing_player_id: 6,
    outgoing_ownership_id: plannerIdentity(1006),
    incoming_player_id: 106,
    expected_outgoing_market_tenths: 54,
    expected_incoming_price_tenths: 62,
  };
}

function link(href = "/my-team") {
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.textContent = "Elsewhere";
  const reached: boolean[] = [];
  anchor.addEventListener("click", (event) => {
    reached.push(event.defaultPrevented);
    event.preventDefault();
  });
  document.body.appendChild(anchor);
  return { anchor, reached };
}

const popstate = (state: unknown = {}) =>
  window.dispatchEvent(new PopStateEvent("popstate", { state }));
const sentinel = () =>
  (window.history.state as Record<string, unknown> | null)
    ?.plannerDepartureGuard;

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

beforeEach(() => {
  window.history.replaceState({}, "", "/transfers?plan=1&gw=9");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("useDepartureGuard", () => {
  it("installs nothing without a source", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { anchor, reached } = link();
    render(<Guarded source={null} />);

    anchor.click();
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);

    expect(confirm).not.toHaveBeenCalled();
    expect(reached).toEqual([false]);
    expect(unload.defaultPrevented).toBe(false);
  });

  it("guards link clicks and beforeunload only while work is unsaved", async () => {
    const { coordinator, gate } = setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { anchor, reached } = link();
    render(<Guarded source={coordinator} />);

    anchor.click();
    expect(confirm).not.toHaveBeenCalled();
    expect(reached).toEqual([false]);

    coordinator.enqueue([{ kind: "set_starting_transfers", value: 2 }]);
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    anchor.click();
    expect(confirm).toHaveBeenCalledWith(WARNING);
    expect(reached).toEqual([false]);

    confirm.mockReturnValue(true);
    anchor.click();
    expect(reached).toEqual([false, false]);

    gate.resolve();
    await flush();
    const calm = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(calm);
    expect(calm.defaultPrevented).toBe(false);
  });

  it("ignores same-address links, modified clicks and non-web links while unsaved", () => {
    const { coordinator } = setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    coordinator.enqueue([{ kind: "set_starting_transfers", value: 2 }]);
    render(<Guarded source={coordinator} />);
    const same = link(window.location.href);
    const mail = link("mailto:support@example.com");
    const modified = link("/players");

    same.anchor.click();
    mail.anchor.click();
    modified.anchor.dispatchEvent(
      new MouseEvent("click", {
        bubbles: true,
        cancelable: true,
        ctrlKey: true,
      }),
    );

    expect(confirm).not.toHaveBeenCalled();
  });

  it("removes every listener when the page is left", () => {
    const { coordinator } = setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    coordinator.enqueue([{ kind: "set_starting_transfers", value: 2 }]);
    const view = render(<Guarded source={coordinator} />);
    const { anchor } = link();

    view.unmount();
    anchor.click();
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    popstate();

    expect(confirm).not.toHaveBeenCalled();
    expect(unload.defaultPrevented).toBe(false);
  });

  describe("pinned Explorer submissions use the same coordinator", () => {
    it.each([
      [
        "unknown",
        async () => {
          throw new TypeError("Failed to fetch");
        },
      ],
      [
        "pending_unsaved",
        async () => {
          throw new PlannerMutationError(503, {
            code: "accepted_not_saved",
            message: "not saved",
            plan: null,
            candidate: null,
          });
        },
      ],
      [
        "conflict",
        async () => {
          throw new PlannerMutationError(409, {
            code: "revision_conflict",
            message: "advanced",
            plan: null,
          });
        },
      ],
    ] as [string, Reply][])(
      "warns while a pinned submission is %s and keeps the record",
      async (status, reply) => {
        const { coordinator, replyWith } = setup();
        replyWith(reply);
        const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
        const { anchor, reached } = link();
        render(<Guarded source={coordinator} />);

        coordinator.submitPinned({
          intents: [transfer()],
          expectedRevision: 0,
        });
        await flush();

        expect(coordinator.getSnapshot().pinned?.status).toBe(status);
        anchor.click();
        expect(confirm).toHaveBeenCalledWith(WARNING);
        expect(reached).toEqual([]);
        const unload = new Event("beforeunload", { cancelable: true });
        window.dispatchEvent(unload);
        expect(unload.defaultPrevented).toBe(true);
        expect(coordinator.getSnapshot().pinned?.status).toBe(status);
      },
    );

    it("warns while a pinned submission is sending", () => {
      const { coordinator } = setup();
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      const { anchor } = link();
      render(<Guarded source={coordinator} />);

      coordinator.submitPinned({ intents: [transfer()], expectedRevision: 0 });

      expect(coordinator.getSnapshot().pinned?.status).toBe("sending");
      anchor.click();
      expect(confirm).toHaveBeenCalledTimes(1);
    });

    it.each([
      [
        "rejected",
        async () => {
          throw new PlannerMutationError(422, {
            code: "prices_changed",
            message: "prices",
            diagnostics: [],
          });
        },
      ],
      ["committed", null],
    ] as [string, Reply | null][])(
      "does not warn once the submission is %s",
      async (status, reply) => {
        const { coordinator, replyWith, gate } = setup();
        if (reply) replyWith(reply);
        const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
        const { anchor, reached } = link();
        render(<Guarded source={coordinator} />);

        coordinator.submitPinned({
          intents: [transfer()],
          expectedRevision: 0,
        });
        gate.resolve();
        await flush();

        expect(coordinator.getSnapshot().pinned?.status).toBe(status);
        anchor.click();
        const unload = new Event("beforeunload", { cancelable: true });
        window.dispatchEvent(unload);
        expect(confirm).not.toHaveBeenCalled();
        expect(reached).toEqual([false]);
        expect(unload.defaultPrevented).toBe(false);
      },
    );
  });

  describe("history", () => {
    it("leaves history alone while nothing is unsaved", () => {
      const { coordinator } = setup();
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      const back = vi.spyOn(window.history, "back");
      const length = window.history.length;
      render(<Guarded source={coordinator} />);

      popstate();

      expect(window.history.length).toBe(length);
      expect(sentinel()).toBeUndefined();
      expect(confirm).not.toHaveBeenCalled();
      expect(back).not.toHaveBeenCalled();
    });

    it("adds one guard entry for a pinned submission and prompts on Back, restoring the entry when the user stays", async () => {
      const { coordinator, replyWith } = setup();
      replyWith(async () => {
        throw new TypeError("Failed to fetch");
      });
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      const back = vi
        .spyOn(window.history, "back")
        .mockImplementation(() => {});
      const go = vi.spyOn(window.history, "go").mockImplementation(() => {});
      const length = window.history.length;
      render(<Guarded source={coordinator} />);

      coordinator.submitPinned({ intents: [transfer()], expectedRevision: 0 });
      await flush();

      expect(sentinel()).toBe(true);
      expect(window.history.length).toBe(length + 1);
      popstate();
      expect(confirm).toHaveBeenCalledWith(WARNING);
      expect(go).toHaveBeenCalledWith(1);
      expect(back).not.toHaveBeenCalled();
      expect(coordinator.getSnapshot().pinned?.status).toBe("unknown");
    });

    it("lets the user leave once confirmed, without a second native prompt", async () => {
      const { coordinator, replyWith } = setup();
      replyWith(async () => {
        throw new TypeError("Failed to fetch");
      });
      vi.spyOn(window, "confirm").mockReturnValue(true);
      const back = vi
        .spyOn(window.history, "back")
        .mockImplementation(() => {});
      render(<Guarded source={coordinator} />);
      coordinator.submitPinned({ intents: [transfer()], expectedRevision: 0 });
      await flush();

      popstate();

      expect(back).toHaveBeenCalledTimes(1);
      const unload = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(unload);
      expect(unload.defaultPrevented).toBe(false);
      expect(coordinator.getSnapshot().pinned?.status).toBe("unknown");
    });

    it("passes Back straight through once the submission is safely committed", async () => {
      const { coordinator, gate } = setup();
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      const back = vi
        .spyOn(window.history, "back")
        .mockImplementation(() => {});
      render(<Guarded source={coordinator} />);
      coordinator.submitPinned({ intents: [transfer()], expectedRevision: 0 });
      expect(sentinel()).toBe(true);
      gate.resolve();
      await flush();

      popstate();

      expect(confirm).not.toHaveBeenCalled();
      expect(back).toHaveBeenCalledTimes(1);
    });
  });
});
