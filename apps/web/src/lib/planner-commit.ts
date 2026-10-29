import type { PlanCommitDescriptor, PlanIntent, PlanResponse } from "@/lib/api";
import {
  getPlanSaveCoordinator,
  type AbandonResult,
  type PinnedSubmission,
  type PlanSaveSnapshot,
  type SubmitPinnedResult,
} from "@/lib/plan-save-coordinator";

/** What the Explorer may know about the plan's shared save coordinator. */
export type PlannerCommitView = {
  /** The latest acknowledged plan, never one carrying an unsaved candidate. */
  plan: PlanResponse;
  acknowledgedRevision: number;
  /** Nothing is in flight or queued, so a pinned submission is allowed to start. */
  idle: boolean;
  /** The single pinned submission, whoever started it; success is judged by `submissionId` only. */
  pinned: PinnedSubmission | null;
  /** Remembered for the session so a submission found after navigation can be named. */
  label: string | null;
};

export type PlannerCommit = {
  getView: () => PlannerCommitView;
  subscribe: (listener: () => void) => () => void;
  submit: (
    descriptor: PlanCommitDescriptor,
    label?: string,
  ) => SubmitPinnedResult;
  retry: () => void;
  reconcile: () => Promise<void>;
  abandon: () => Promise<AbandonResult>;
  /** Offers a freshly loaded plan; the coordinator ignores it while it holds unsaved work. */
  synchronize: (plan: PlanResponse) => void;
};

export type PlannerCommitFactory = (plan: PlanResponse) => PlannerCommit;

const labels = new Map<string, string>();

/** The exact mutation the server issued: its intent plus its price guard, nothing recomputed. */
export function commitDescriptorToIntent(
  descriptor: PlanCommitDescriptor,
): PlanIntent {
  return { ...descriptor.intent, ...descriptor.guard } as PlanIntent;
}

export const createPlannerCommit: PlannerCommitFactory = (plan) => {
  const coordinator = getPlanSaveCoordinator(plan);
  let cached: { snapshot: PlanSaveSnapshot; view: PlannerCommitView } | null =
    null;

  return {
    getView() {
      const snapshot = coordinator.getSnapshot();
      if (cached?.snapshot !== snapshot) {
        cached = {
          snapshot,
          view: {
            plan: snapshot.acknowledged,
            acknowledgedRevision: snapshot.acknowledged.revision,
            idle: snapshot.inFlight === null && snapshot.pendingCount === 0,
            pinned: snapshot.pinned,
            label: snapshot.pinned
              ? (labels.get(snapshot.pinned.submissionId) ?? null)
              : null,
          },
        };
      }
      return cached.view;
    },
    subscribe: coordinator.subscribe,
    submit(descriptor, label) {
      const result = coordinator.submitPinned({
        intents: [commitDescriptorToIntent(descriptor)],
        expectedRevision: descriptor.expected_revision,
      });
      if (result.type === "started" && label) {
        labels.set(result.submissionId, label);
      }
      return result;
    },
    retry: () => coordinator.retry(),
    reconcile: () => coordinator.reconcile(),
    abandon: () => coordinator.abandon(),
    synchronize: (fresh) => {
      getPlanSaveCoordinator(fresh);
    },
  };
};
