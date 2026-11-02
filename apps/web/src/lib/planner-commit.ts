import type { PlanCommitDescriptor, PlanIntent, PlanResponse } from "@/lib/api";
import {
  getPlanSaveCoordinator,
  type AbandonResult,
  type PinnedSubmission,
  type PlanSaveSnapshot,
  type SubmitPinnedResult,
} from "@/lib/plan-save-coordinator";

/** What a submission was for, remembered with its identity so a returned Explorer can tell it is its own. */
export type SubmissionDetails = {
  gameweek: number;
  playerInId: number;
  outgoingName: string;
  incomingName: string;
};

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
  details: SubmissionDetails | null;
};

export type PlannerCommit = {
  getView: () => PlannerCommitView;
  subscribe: (listener: () => void) => () => void;
  submit: (
    descriptor: PlanCommitDescriptor,
    label?: string,
    details?: SubmissionDetails,
  ) => SubmitPinnedResult;
  retry: () => void;
  reconcile: () => Promise<void>;
  abandon: () => Promise<AbandonResult>;
  /** Offers a freshly loaded plan; the coordinator ignores it while it holds unsaved work. */
  synchronize: (plan: PlanResponse) => void;
  /** The shared coordinator's own answer, used by the departure guard. */
  hasUnsavedWork: () => boolean;
};

export type PlannerCommitFactory = (plan: PlanResponse) => PlannerCommit;

const submissions = new Map<
  string,
  { label: string | null; details: SubmissionDetails | null }
>();

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
              ? (submissions.get(snapshot.pinned.submissionId)?.label ?? null)
              : null,
            details: snapshot.pinned
              ? (submissions.get(snapshot.pinned.submissionId)?.details ?? null)
              : null,
          },
        };
      }
      return cached.view;
    },
    subscribe: coordinator.subscribe,
    submit(descriptor, label, details) {
      const result = coordinator.submitPinned({
        intents: [commitDescriptorToIntent(descriptor)],
        expectedRevision: descriptor.expected_revision,
      });
      if (result.type === "started") {
        submissions.set(result.submissionId, {
          label: label ?? null,
          details: details ?? null,
        });
      }
      return result;
    },
    retry: () => coordinator.retry(),
    reconcile: () => coordinator.reconcile(),
    abandon: () => coordinator.abandon(),
    synchronize: (fresh) => {
      getPlanSaveCoordinator(fresh);
    },
    hasUnsavedWork: () => coordinator.hasUnsavedWork(),
  };
};
