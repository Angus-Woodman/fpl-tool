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

export type PinnedStatus =
  | "sending"
  | "committed"
  | "rejected"
  | "conflict"
  | "unknown"
  | "pending_unsaved"
  | "plan_missing";

/** One transfer submission previewed at an exact revision (see contracts/pinned-submission.md). */
export type PinnedSubmission = {
  submissionId: string;
  mutationId: string;
  expectedRevision: number;
  status: PinnedStatus;
  committedRevision: number | null;
  code: string | null;
  diagnostics: PlanResponse["decision_errors"] | null;
  message: string | null;
};

export type SubmitPinnedRequest = {
  intents: PlanIntent[];
  expectedRevision: number;
};

export type SubmitPinnedResult =
  | { type: "started"; submissionId: string }
  | {
      type: "refused";
      reason:
        | "not_ready"
        | "plan_missing"
        | "pinned_exists"
        | "busy"
        | "stale_preview";
    };

export type AbandonResult =
  | {
      type: "abandoned";
      previous: PinnedSubmission;
      // True only for an accepted-but-not-saved transfer: the server keeps its pending receipt.
      serverReceiptRetained: boolean;
    }
  | { type: "nothing_to_abandon" }
  | { type: "refused"; reason: "outcome_pending" | "reconcile_first" }
  | { type: "refresh_failed"; message: string };

export type PlanSaveSnapshot = {
  acknowledged: PlanResponse;
  displayPlan: PlanResponse;
  inFlight: PlanMutationEnvelope | null;
  pendingCount: number;
  status: "saved" | "saving" | "not_saved" | "conflict" | "error" | "missing";
  message: string | null;
  rejection: {
    intents: PlanIntent[];
    diagnostics: PlanResponse["decision_errors"];
  } | null;
  skipped: { intents: QueuedPlanIntent[]; reason: string }[] | null;
  pinned: PinnedSubmission | null;
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
  private activeSource: QueuedPlanIntent[] | null = null;
  private listeners = new Set<() => void>();
  private transport: Transport;
  private abandonInFlight: Promise<AbandonResult> | null = null;

  constructor(plan: PlanResponse, transport: Partial<Transport> = {}) {
    this.snapshot = {
      acknowledged: plan,
      displayPlan: plan,
      inFlight: null,
      pendingCount: 0,
      status: "saved",
      message: null,
      rejection: null,
      skipped: null,
      pinned: null,
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

  hasUnsavedWork(): boolean {
    if (this.snapshot.status === "missing") return false;
    return this.active !== null || this.queue.length > 0;
  }

  private pinnedIsActive(): boolean {
    const pinned = this.snapshot.pinned;
    return (
      pinned !== null &&
      this.active !== null &&
      this.active.mutation_id === pinned.mutationId
    );
  }

  /** The snapshot change for the pinned record, or nothing when no pinned envelope is active. */
  private pinnedChange(
    status: PinnedStatus,
    change: Partial<Omit<PinnedSubmission, "status">> = {},
  ): { pinned?: PinnedSubmission } {
    const pinned = this.snapshot.pinned;
    if (!pinned || !this.pinnedIsActive()) return {};
    return { pinned: { ...pinned, ...change, status } };
  }

  /**
   * Submit a previewed transfer against exactly `expectedRevision`. It is never queued,
   * rebased or replayed: if anything else is pending or the revision moved, it is refused.
   */
  submitPinned(request: SubmitPinnedRequest): SubmitPinnedResult {
    if (this.snapshot.status === "missing")
      return { type: "refused", reason: "plan_missing" };
    if (this.snapshot.acknowledged.foundation_state !== "ready")
      return { type: "refused", reason: "not_ready" };
    if (this.snapshot.pinned)
      return { type: "refused", reason: "pinned_exists" };
    if (this.active || this.queue.length > 0)
      return { type: "refused", reason: "busy" };
    if (this.snapshot.acknowledged.revision !== request.expectedRevision)
      return { type: "refused", reason: "stale_preview" };
    let intents: PlanIntent[];
    try {
      intents = request.intents.map((intent) => this.resolve(intent));
    } catch {
      // An intent that no longer resolves means the preview no longer describes this plan.
      return { type: "refused", reason: "stale_preview" };
    }
    const envelope: PlanMutationEnvelope = {
      mutation_id: crypto.randomUUID(),
      expected_revision: request.expectedRevision,
      intents,
    };
    intents.forEach((intent) => Object.freeze(intent));
    Object.freeze(envelope.intents);
    this.active = Object.freeze(envelope);
    this.activeSource = null;
    const submissionId = crypto.randomUUID();
    this.publish({
      status: "saving",
      message: null,
      pinned: {
        submissionId,
        mutationId: envelope.mutation_id,
        expectedRevision: request.expectedRevision,
        status: "sending",
        committedRevision: null,
        code: null,
        diagnostics: null,
        message: null,
      },
    });
    void this.dispatch();
    return { type: "started", submissionId };
  }

  /**
   * Discard only the pinned submission, and only when its outcome is known not to have
   * been applied (or it already finished). Never touches queued Planner edits. For an
   * accepted-but-not-saved transfer this is client-side only: the server's pending
   * receipt is neither cancelled, deleted nor committed.
   */
  abandon(): Promise<AbandonResult> {
    if (this.abandonInFlight) return this.abandonInFlight;
    const run = this.runAbandon().finally(() => {
      this.abandonInFlight = null;
    });
    this.abandonInFlight = run;
    return run;
  }

  private async runAbandon(): Promise<AbandonResult> {
    const pinned = this.snapshot.pinned;
    if (!pinned) return { type: "nothing_to_abandon" };
    if (pinned.status === "sending")
      return { type: "refused", reason: "outcome_pending" };
    if (pinned.status === "unknown")
      return { type: "refused", reason: "reconcile_first" };
    if (
      pinned.status === "committed" ||
      pinned.status === "rejected" ||
      pinned.status === "plan_missing"
    ) {
      const clearsError =
        pinned.status === "rejected" &&
        this.snapshot.status === "error" &&
        !this.active &&
        this.queue.length === 0;
      this.publish({
        pinned: null,
        ...(clearsError ? { status: "saved" as const, message: null } : {}),
      });
      return {
        type: "abandoned",
        previous: pinned,
        serverReceiptRetained: false,
      };
    }
    // conflict or pending_unsaved: the server did not apply it; refresh first.
    const envelope = this.active;
    if (!envelope || envelope.mutation_id !== pinned.mutationId)
      return {
        type: "refresh_failed",
        message: "The submission is no longer the active save",
      };
    let plan: PlanResponse | null;
    try {
      plan = await this.transport.load(this.snapshot.acknowledged.plan_id);
    } catch (error) {
      return {
        type: "refresh_failed",
        message:
          error instanceof Error ? error.message : "Refreshing the plan failed",
      };
    }
    if (
      this.active !== envelope ||
      this.snapshot.pinned?.mutationId !== pinned.mutationId
    )
      return {
        type: "refresh_failed",
        message: "The submission changed while the plan was refreshing",
      };
    this.active = null;
    this.activeSource = null;
    const result: AbandonResult = {
      type: "abandoned",
      previous: pinned,
      serverReceiptRetained: pinned.status === "pending_unsaved",
    };
    if (plan === null) {
      this.publish({
        status: "missing",
        message: "This plan no longer exists",
        pinned: null,
      });
      return result;
    }
    const next =
      plan.revision >= this.snapshot.acknowledged.revision
        ? plan
        : this.snapshot.acknowledged;
    this.publish({
      acknowledged: next,
      displayPlan: next,
      status: "saved",
      message: null,
      pinned: null,
    });
    this.drain();
    return result;
  }

  enqueue(intents: QueuedPlanIntent[]): void {
    if (this.snapshot.status === "missing") return;
    if (this.snapshot.acknowledged.foundation_state !== "ready") {
      this.publish({
        status: "error",
        message: "Plan requires explicit initialization before editing",
      });
      return;
    }
    if (intents.length === 0) return;
    this.queue.push(structuredClone(intents));
    this.publish({ skipped: null });
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
    if (intent.kind === "edit_transfer" || intent.kind === "remove_transfer") {
      const exists = plan.gameweeks.some((week) =>
        week.decisions.some(
          (decision) => decision.decision_id === intent.decision_id,
        ),
      );
      if (!exists)
        throw new Error("Transfer decision no longer exists; select it again");
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
    while (!this.active && this.queue.length > 0) {
      if (this.snapshot.status === "missing") return;
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
        this.activeSource = batch;
      } catch (error) {
        // An unresolvable intent is surfaced for reselection, never retargeted.
        this.publish({
          skipped: [
            ...(this.snapshot.skipped ?? []),
            {
              intents: batch,
              reason:
                error instanceof Error
                  ? error.message
                  : "Edit cannot be applied",
            },
          ],
        });
        continue;
      }
      this.publish({ status: "saving" });
      void this.dispatch();
    }
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
        ...this.pinnedChange("pending_unsaved", {
          message: "Accepted edit is not saved; retry the same edit",
        }),
      });
      return;
    }
    if (result.committed_revision === null)
      throw new Error("Committed revision is missing");
    const plan =
      result.plan.revision >= this.snapshot.acknowledged.revision
        ? result.plan
        : this.snapshot.acknowledged;
    const pinned = this.pinnedChange("committed", {
      committedRevision: result.committed_revision,
      message: null,
    });
    this.active = null;
    this.publish({
      acknowledged: plan,
      displayPlan: plan,
      status: "saved",
      message: null,
      rejection: null,
      ...pinned,
    });
    this.drain();
  }

  private fail(error: unknown): void {
    if (error instanceof PlannerMutationError) {
      const { detail } = error;
      if (error.status === 422) {
        const intents = this.active?.intents ?? [];
        const pinned = this.pinnedChange("rejected", {
          code: detail.code,
          diagnostics: detail.diagnostics ?? [],
          message: error.message,
        });
        this.active = null;
        this.publish({
          displayPlan: this.snapshot.acknowledged,
          status: "error",
          message: error.message,
          // A rejected transfer keeps its diagnostics on the pinned record, not the Planner banner.
          rejection:
            "pinned" in pinned
              ? null
              : { intents, diagnostics: detail.diagnostics ?? [] },
          ...pinned,
        });
        this.drain();
        return;
      }
      if (error.status === 404) {
        if (detail.code === "plan_not_found") {
          const message = "This plan no longer exists; the edit was not saved";
          const pinned = this.pinnedChange("plan_missing", { message });
          if ("pinned" in pinned) this.active = null;
          this.publish({ status: "missing", message, ...pinned });
          return;
        }
        // An unknown receipt is inconclusive: the original request may still be in flight.
        const message = "Save outcome is not confirmed; retry the same edit";
        this.publish({
          status: "not_saved",
          message,
          ...this.pinnedChange("unknown", { message }),
        });
        return;
      }
      if (
        (error.status === 409 || error.status === 410) &&
        !(this.pinnedIsActive() && detail.code === "mutation_id_reused")
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
          ...this.pinnedChange("conflict", { message: error.message }),
        });
        return;
      }
      const accepted = detail.code === "accepted_not_saved";
      this.publish({
        status: "not_saved",
        message: error.message,
        displayPlan:
          accepted &&
          detail.candidate &&
          detail.plan?.revision === this.snapshot.acknowledged.revision
            ? detail.candidate
            : this.snapshot.acknowledged,
        ...this.pinnedChange(accepted ? "pending_unsaved" : "unknown", {
          message: accepted
            ? "Accepted edit is not saved; retry the same edit"
            : error.message,
        }),
      });
      return;
    }
    const message = "Save outcome is unknown; reconcile or retry the same edit";
    this.publish({
      status: "not_saved",
      message,
      ...this.pinnedChange("unknown", { message }),
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
    this.publish({
      status: "saving",
      message: null,
      ...this.pinnedChange("sending", { message: null }),
    });
    void this.dispatch();
  }

  async reconcile(): Promise<void> {
    if (!this.active || this.snapshot.status === "saving") return;
    // A known conflict has no outcome left to look up.
    if (this.snapshot.pinned?.status === "conflict" && this.pinnedIsActive())
      return;
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
    if (this.pinnedIsActive()) {
      // A previewed transfer is never replayed against a newer plan; only a known conflict can be cleared.
      if (this.snapshot.pinned?.status === "conflict") await this.abandon();
      return;
    }
    if (!this.active || this.snapshot.status !== "conflict") return;
    const envelope = this.active;
    try {
      const plan = await this.transport.load(
        this.snapshot.acknowledged.plan_id,
      );
      if (!plan) throw new Error("Plan no longer exists");
      if (this.active !== envelope) return;
      // Re-resolve the original edit against the fresh plan; never replay stale absolute values.
      this.queue.unshift(
        structuredClone(this.activeSource ?? envelope.intents),
      );
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
