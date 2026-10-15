import {
  PlanChip,
  PlanIntent,
  PlanMutationEnvelope,
  PlanMutationResponse,
  PlanResponse,
  PlannerMutationError,
  fetchPlan,
  fetchPlanMutation,
  mutatePlan,
} from "@/lib/api";

export type QueuedPlanIntent =
  | PlanIntent
  | {
      kind: "set_horizon_bound";
      field: "start_gameweek" | "end_gameweek";
      value: number;
    }
  | { kind: "set_starting_chip"; chip: PlanChip; used: boolean }
  | { kind: "set_free_hit_19"; used: boolean };

export type PlanSaveSnapshot = {
  acknowledged: PlanResponse;
  displayPlan: PlanResponse;
  inFlight: PlanMutationEnvelope | null;
  pendingCount: number;
  status: "saved" | "saving" | "not_saved" | "conflict" | "error";
  message: string | null;
  rejection: {
    intents: PlanIntent[];
    diagnostics: PlanResponse["decision_errors"];
  } | null;
};

type Transport = {
  send: (
    planId: number,
    envelope: PlanMutationEnvelope,
  ) => Promise<PlanMutationResponse>;
  receipt: (
    planId: number,
    mutationId: string,
  ) => Promise<PlanMutationResponse>;
  load: (planId: number) => Promise<PlanResponse | null>;
};

export class PlanSaveCoordinator {
  private snapshot: PlanSaveSnapshot;
  private queue: QueuedPlanIntent[][] = [];
  private active: PlanMutationEnvelope | null = null;
  private listeners = new Set<() => void>();
  private transport: Transport;

  constructor(plan: PlanResponse, transport: Partial<Transport> = {}) {
    this.snapshot = {
      acknowledged: plan,
      displayPlan: plan,
      inFlight: null,
      pendingCount: 0,
      status: "saved",
      message: null,
      rejection: null,
    };
    this.transport = {
      send: mutatePlan,
      receipt: fetchPlanMutation,
      load: fetchPlan,
      ...transport,
    };
  }

  getSnapshot = (): PlanSaveSnapshot => this.snapshot;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private publish(change: Partial<PlanSaveSnapshot>): void {
    this.snapshot = {
      ...this.snapshot,
      ...change,
      inFlight: this.active,
      pendingCount: this.queue.reduce(
        (count, batch) => count + batch.length,
        0,
      ),
    };
    this.listeners.forEach((listener) => listener());
  }

  synchronize(plan: PlanResponse): void {
    if (
      !this.active &&
      this.queue.length === 0 &&
      plan.revision >= this.snapshot.acknowledged.revision
    ) {
      this.publish({
        acknowledged: plan,
        displayPlan: plan,
        rejection:
          plan.revision === this.snapshot.acknowledged.revision
            ? this.snapshot.rejection
            : null,
      });
    }
  }

  enqueue(intents: QueuedPlanIntent[]): void {
    if (this.snapshot.acknowledged.foundation_state !== "ready") {
      this.publish({
        status: "error",
        message: "Plan requires explicit initialization before editing",
      });
      return;
    }
    if (intents.length === 0) return;
    this.queue.push(structuredClone(intents));
    this.publish({});
    this.drain();
  }

  private resolve(intent: QueuedPlanIntent): PlanIntent {
    const plan = this.snapshot.acknowledged;
    if (intent.kind === "set_horizon_bound") {
      return {
        kind: "change_horizon",
        start_gameweek: plan.start_gameweek,
        end_gameweek: plan.end_gameweek,
        [intent.field]: intent.value,
      };
    }
    if (
      intent.kind === "set_starting_chip" ||
      intent.kind === "set_free_hit_19"
    ) {
      const boundary = plan.starting_state;
      if (!boundary) throw new Error("Starting state is unavailable");
      const chips = new Set(boundary.used_chips);
      if (intent.kind === "set_starting_chip") {
        if (intent.used) chips.add(intent.chip);
        else chips.delete(intent.chip);
      }
      return {
        kind: "set_starting_chips",
        used_chips: [...chips],
        free_hit_gameweek_19:
          intent.kind === "set_free_hit_19"
            ? intent.used
            : boundary.free_hit_gameweek_19,
      };
    }
    if ("gameweek_number" in intent) {
      const week = plan.gameweeks.find(
        (item) => item.gameweek_number === intent.gameweek_number,
      );
      if (!week) throw new Error("Selected gameweek is no longer in the plan");
      const selectedIds =
        "player_id" in intent
          ? [intent.player_id]
          : intent.kind === "swap_lineup_players"
            ? [intent.first_player_id, intent.second_player_id]
            : intent.kind === "add_transfer"
              ? [intent.outgoing_player_id]
              : [];
      if (
        selectedIds.some(
          (identifier) =>
            !week.players.some((player) => player.player_id === identifier),
        )
      ) {
        throw new Error(
          "Selected player is no longer owned; select the intended player again",
        );
      }
    }
    return intent;
  }

  private drain(): void {
    if (this.active || this.queue.length === 0) return;
    const batch = this.queue.shift()!;
    try {
      const envelope: PlanMutationEnvelope = {
        mutation_id: crypto.randomUUID(),
        expected_revision: this.snapshot.acknowledged.revision,
        intents: batch.map((intent) => this.resolve(intent)),
      };
      envelope.intents.forEach((intent) => {
        if ("used_chips" in intent && intent.used_chips)
          Object.freeze(intent.used_chips);
        Object.freeze(intent);
      });
      Object.freeze(envelope.intents);
      this.active = Object.freeze(envelope);
    } catch (error) {
      this.publish({
        status: "error",
        message:
          error instanceof Error ? error.message : "Edit cannot be applied",
      });
      return;
    }
    this.publish({ status: "saving", message: null, rejection: null });
    void this.dispatch();
  }

  private accept(result: PlanMutationResponse): void {
    if (
      !this.active ||
      result.mutation_id !== this.active.mutation_id ||
      result.plan.plan_id !== this.snapshot.acknowledged.plan_id
    ) {
      throw new Error(
        "Mutation acknowledgement does not match the pending edit",
      );
    }
    if (result.status === "accepted_not_saved") {
      this.publish({
        displayPlan: result.candidate ?? this.snapshot.acknowledged,
        status: "not_saved",
        message: "Accepted edit is not saved; retry the same edit",
      });
      return;
    }
    if (result.committed_revision === null)
      throw new Error("Committed revision is missing");
    const plan =
      result.plan.revision >= this.snapshot.acknowledged.revision
        ? result.plan
        : this.snapshot.acknowledged;
    this.active = null;
    this.publish({
      acknowledged: plan,
      displayPlan: plan,
      status: "saved",
      message: null,
    });
    this.drain();
  }

  private fail(error: unknown): void {
    if (error instanceof PlannerMutationError) {
      const { detail } = error;
      if (error.status === 422) {
        const intents = this.active?.intents ?? [];
        this.active = null;
        this.publish({
          displayPlan: this.snapshot.acknowledged,
          status: "error",
          message: error.message,
          rejection: { intents, diagnostics: detail.diagnostics ?? [] },
        });
        this.drain();
        return;
      }
      if (
        error.status === 409 ||
        error.status === 404 ||
        error.status === 410
      ) {
        const plan =
          detail.plan &&
          detail.plan.revision >= this.snapshot.acknowledged.revision
            ? detail.plan
            : this.snapshot.acknowledged;
        this.publish({
          acknowledged: plan,
          displayPlan: plan,
          status: "conflict",
          message: error.message,
        });
        return;
      }
      this.publish({
        status: "not_saved",
        message: error.message,
        displayPlan:
          detail.code === "accepted_not_saved" &&
          detail.candidate &&
          detail.plan?.revision === this.snapshot.acknowledged.revision
            ? detail.candidate
            : this.snapshot.acknowledged,
      });
      return;
    }
    this.publish({
      status: "not_saved",
      message: "Save outcome is unknown; reconcile or retry the same edit",
    });
  }

  private async dispatch(): Promise<void> {
    if (!this.active) return;
    const envelope = this.active;
    try {
      const result = await this.transport.send(
        this.snapshot.acknowledged.plan_id,
        envelope,
      );
      if (this.active === envelope) this.accept(result);
    } catch (error) {
      if (this.active === envelope) this.fail(error);
    }
  }

  retry(): void {
    if (!this.active || this.snapshot.status !== "not_saved") return;
    this.publish({ status: "saving", message: null });
    void this.dispatch();
  }

  async reconcile(): Promise<void> {
    if (!this.active || this.snapshot.status === "saving") return;
    const envelope = this.active;
    try {
      const result = await this.transport.receipt(
        this.snapshot.acknowledged.plan_id,
        envelope.mutation_id,
      );
      if (this.active === envelope) this.accept(result);
    } catch (error) {
      if (this.active === envelope) this.fail(error);
    }
  }

  async revalidate(): Promise<void> {
    if (!this.active || this.snapshot.status !== "conflict") return;
    const envelope = this.active;
    try {
      const plan = await this.transport.load(
        this.snapshot.acknowledged.plan_id,
      );
      if (!plan) throw new Error("Plan no longer exists");
      if (this.active !== envelope) return;
      this.queue.unshift(structuredClone(envelope.intents));
      this.active = null;
      this.publish({
        acknowledged: plan,
        displayPlan: plan,
        status: "saved",
        message: null,
      });
      this.drain();
    } catch (error) {
      this.publish({
        status: "conflict",
        message: error instanceof Error ? error.message : "Revalidation failed",
      });
    }
  }
}

const coordinators = new Map<number, PlanSaveCoordinator>();

export function getPlanSaveCoordinator(
  plan: PlanResponse,
): PlanSaveCoordinator {
  let coordinator = coordinators.get(plan.plan_id);
  if (!coordinator) {
    coordinator = new PlanSaveCoordinator(plan);
    coordinators.set(plan.plan_id, coordinator);
  } else {
    coordinator.synchronize(plan);
  }
  return coordinator;
}
