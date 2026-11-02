"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import type { CommitRegionModel } from "@/components/transfers/planner/planner-transfer-preview";
import { describePlannerReasons } from "@/components/transfers/planner/planner-reasons";
import {
  fetchPlan,
  fetchPlanTransferPreview,
  type PlanTransferPreviewResponse,
  type TransferHorizon,
} from "@/lib/api";
import type { PlannerCommit } from "@/lib/planner-commit";
import { buildPlannerExplorerHref } from "@/lib/planner-explorer-url";
import type { PinnedSubmission } from "@/lib/plan-save-coordinator";

export type PreviewState =
  | { kind: "idle" }
  | { kind: "loading"; playerInId: number }
  | { kind: "ok"; data: PlanTransferPreviewResponse }
  | {
      kind: "error";
      playerInId: number;
      message: string;
      missingPlayerIds: number[];
    };

export type ConfirmationNotice =
  | {
      kind: "rejected";
      message: string;
      code: string | null;
      summary: string | null;
      /** Where to preview the rejected transfer again, when it is not the page's own scope. */
      recoverHref?: string | null;
    }
  | { kind: "not_added"; summary: string | null }
  | { kind: "committed"; summary: string; incomingName: string }
  | { kind: "earlier"; text: string; recoverHref?: string | null };

type OwnSubmission = {
  submissionId: string;
  gameweek: number;
  outgoingPlayerId: number;
  projectionRunId: number;
  playerInId: number;
  summary: string;
  outgoingName: string;
  incomingName: string;
};

/** Reported once, after the Explorer's own submission is acknowledged as committed and cleared. */
export type CommittedTransfer = {
  gameweek: number;
  playerInId: number;
  outgoingName: string;
  incomingName: string;
};

function notConfirmableReason(data: PlanTransferPreviewResponse): string {
  if (data.state === "unavailable") {
    return `This transfer cannot be added: ${describePlannerReasons(data.reasons).join("; ")}.`;
  }
  const conflict = data.conflict;
  if (conflict?.kind === "financial") {
    return `This transfer cannot be added: GW${conflict.gameweek} would overdraw the bank.`;
  }
  if (conflict) {
    return `This transfer cannot be added: it is blocked by GW${conflict.gameweek}.`;
  }
  return "This transfer cannot be added right now.";
}

function describeEarlier(record: PinnedSubmission): string {
  switch (record.status) {
    case "committed":
      return "A transfer you confirmed earlier was added to your plan.";
    case "plan_missing":
      return "This plan no longer exists, so a transfer you confirmed earlier was not added.";
    default:
      return `A transfer you confirmed earlier was not added${record.message ? `: ${record.message}` : "."}`;
  }
}

/**
 * Preview selection and the confirmation state machine for the Planner Explorer.
 * Success is derived only from the pinned record of this Explorer's own submission;
 * nothing here resubmits or rebases a transfer.
 */
export function usePlannerConfirmation(params: {
  planId: number;
  gameweek: number;
  playerOutId: number | null;
  horizon: TransferHorizon;
  runId: number | null;
  commit: PlannerCommit;
  onCommitted?: (transfer: CommittedTransfer) => void;
  /** Reloads the candidate list in the background after the plan or prices moved under it. */
  refreshList?: () => void;
}) {
  const { planId, gameweek, playerOutId, horizon, runId, commit } = params;
  const onCommittedRef = useRef(params.onCommitted);
  onCommittedRef.current = params.onCommitted;
  const refreshListRef = useRef(params.refreshList);
  refreshListRef.current = params.refreshList;
  const view = useSyncExternalStore(
    commit.subscribe,
    commit.getView,
    commit.getView,
  );
  const [preview, setPreview] = useState<PreviewState>({ kind: "idle" });
  const [notice, setNotice] = useState<ConfirmationNotice | null>(null);
  const sequence = useRef(0);
  const own = useRef<OwnSubmission | null>(null);
  const handled = useRef(new Set<string>());
  const watched = useRef(new Set<string>());
  const runRef = useRef(runId);
  runRef.current = runId;
  const selectedRef = useRef<number | null>(null);
  // What the page shows now, read at call time so an async recovery sees the latest scope.
  const scopeRef = useRef({ gameweek, playerOutId });
  scopeRef.current = { gameweek, playerOutId };

  type Scoped = Pick<
    OwnSubmission,
    "gameweek" | "outgoingPlayerId" | "projectionRunId"
  >;
  const inScope = useCallback(
    (submission: Scoped | null | undefined): boolean =>
      submission != null &&
      submission.gameweek === scopeRef.current.gameweek &&
      submission.outgoingPlayerId === scopeRef.current.playerOutId &&
      submission.projectionRunId === runRef.current,
    [],
  );
  const recoverHrefFor = useCallback(
    (submission: Scoped): string =>
      buildPlannerExplorerHref({
        planId,
        gameweek: submission.gameweek,
        playerOutId: submission.outgoingPlayerId,
        horizon,
        runId: submission.projectionRunId,
      }),
    [planId, horizon],
  );

  const loadPreview = useCallback(
    async (playerInId: number, options: { syncPlan?: boolean } = {}) => {
      if (playerOutId === null) return;
      const current = ++sequence.current;
      selectedRef.current = playerInId;
      setPreview({ kind: "loading", playerInId });
      try {
        if (options.syncPlan) {
          const fresh = await fetchPlan(planId);
          if (current !== sequence.current) return;
          if (fresh === null) {
            setPreview({
              kind: "error",
              playerInId,
              message: "This plan no longer exists.",
              missingPlayerIds: [],
            });
            return;
          }
          commit.synchronize(fresh);
        }
        const result = await fetchPlanTransferPreview({
          planId,
          gameweek,
          playerOutId,
          playerInId,
          projectionRunId: runRef.current,
        });
        if (current !== sequence.current) return;
        if (result.type === "ok") {
          setPreview({ kind: "ok", data: result.data });
        } else {
          setPreview({
            kind: "error",
            playerInId,
            message:
              result.type === "unavailable"
                ? result.message
                : result.type === "plan_not_ready"
                  ? "This plan is not ready for transfers yet."
                  : result.type === "plan_not_found"
                    ? "This plan no longer exists."
                    : "This player was not found.",
            missingPlayerIds:
              result.type === "unavailable" ? result.missingPlayerIds : [],
          });
        }
      } catch {
        if (current === sequence.current) {
          setPreview({
            kind: "error",
            playerInId,
            message: "Could not load the preview. Try again shortly.",
            missingPlayerIds: [],
          });
        }
      }
    },
    [planId, gameweek, playerOutId, commit],
  );

  const reset = useCallback(() => {
    sequence.current += 1;
    selectedRef.current = null;
    setPreview({ kind: "idle" });
    setNotice(null);
  }, []);

  // Changing the outgoing player or gameweek abandons the candidate being previewed.
  const scope = `${planId}:${gameweek}:${playerOutId}`;
  const lastScope = useRef(scope);
  useEffect(() => {
    if (lastScope.current !== scope) {
      lastScope.current = scope;
      reset();
    }
  }, [scope, reset]);

  // A preview belongs to one projection run; a different run makes it obsolete. A horizon change keeps the run.
  const lastRun = useRef(runId);
  useEffect(() => {
    if (runId === null) return;
    if (lastRun.current !== null && lastRun.current !== runId) {
      sequence.current += 1;
      selectedRef.current = null;
      setPreview({ kind: "idle" });
      setNotice((current) => (current?.kind === "rejected" ? null : current));
    }
    lastRun.current = runId;
  }, [runId]);

  const lastHorizon = useRef(horizon);
  useEffect(() => {
    if (lastHorizon.current !== horizon) {
      lastHorizon.current = horizon;
      setNotice((current) => (current?.kind === "rejected" ? null : current));
    }
  }, [horizon]);

  const acknowledge = useCallback(
    async (record: PinnedSubmission, mine: OwnSubmission | null) => {
      // Another candidate's preview, or a preview of another gameweek, player or run, is not
      // replaced by the outcome of an earlier transfer.
      const owns = () =>
        inScope(mine) &&
        (selectedRef.current === null ||
          selectedRef.current === mine?.playerInId);
      if (mine && record.status === "rejected" && owns()) {
        sequence.current += 1;
        setPreview({ kind: "loading", playerInId: mine.playerInId });
      }
      const result = await commit.abandon();
      if (result.type !== "abandoned") return;
      const previous = result.previous;
      if (!mine) {
        setNotice({ kind: "earlier", text: describeEarlier(previous) });
        return;
      }
      if (previous.status === "committed") {
        selectedRef.current = null;
        setPreview({ kind: "idle" });
        setNotice({
          kind: "committed",
          summary: mine.summary,
          incomingName: mine.incomingName,
        });
        onCommittedRef.current?.({
          gameweek: mine.gameweek,
          playerInId: mine.playerInId,
          outgoingName: mine.outgoingName,
          incomingName: mine.incomingName,
        });
      } else if (previous.status === "rejected") {
        setNotice({
          kind: "rejected",
          message:
            previous.message ??
            (previous.code === "prices_changed"
              ? "Prices changed since you previewed this transfer."
              : "The server rejected this transfer."),
          code: previous.code,
          summary: mine.summary,
          recoverHref: inScope(mine) ? null : recoverHrefFor(mine),
        });
        if (inScope(mine)) {
          refreshListRef.current?.();
          if (owns()) void loadPreview(mine.playerInId);
        }
      } else {
        setNotice({ kind: "earlier", text: describeEarlier(previous) });
      }
    },
    [commit, loadPreview, inScope, recoverHrefFor],
  );

  useEffect(() => {
    const record = view.pinned;
    if (!record) return;
    if (!["committed", "rejected", "plan_missing"].includes(record.status)) {
      // Seen unresolved while mounted, so its outcome belongs to this Explorer even if it was started earlier.
      watched.current.add(record.submissionId);
      return;
    }
    const key = `${record.submissionId}:${record.status}`;
    if (handled.current.has(key)) return;
    handled.current.add(key);
    let mine: OwnSubmission | null = null;
    if (own.current?.submissionId === record.submissionId) {
      mine = own.current;
    } else if (watched.current.has(record.submissionId) && view.details) {
      mine = {
        submissionId: record.submissionId,
        ...view.details,
        summary: view.label ?? "",
      };
    }
    void acknowledge(record, mine);
  }, [view.pinned, view.details, view.label, acknowledge]);

  const openPreview = useCallback(
    (playerInId: number) => {
      setNotice((current) =>
        current?.kind === "rejected" || current?.kind === "not_added"
          ? null
          : current,
      );
      void loadPreview(playerInId);
    },
    [loadPreview],
  );

  const closePreview = useCallback(() => {
    sequence.current += 1;
    selectedRef.current = null;
    setPreview({ kind: "idle" });
  }, []);

  const confirm = useCallback(() => {
    if (preview.kind !== "ok") return;
    const data = preview.data;
    const descriptor = data.commit;
    if (!descriptor) return;
    const submittedGameweek = data.planning_context.gameweek;
    const summary = `${data.outgoing.web_name} to ${data.candidate.web_name} in GW${submittedGameweek}`;
    const result = commit.submit(descriptor, summary, {
      gameweek: submittedGameweek,
      outgoingPlayerId: data.outgoing.player_id,
      projectionRunId: data.projection.run_id,
      playerInId: data.candidate.player_id,
      outgoingName: data.outgoing.web_name,
      incomingName: data.candidate.web_name,
    });
    if (result.type === "started") {
      own.current = {
        submissionId: result.submissionId,
        gameweek: submittedGameweek,
        outgoingPlayerId: data.outgoing.player_id,
        projectionRunId: data.projection.run_id,
        playerInId: data.candidate.player_id,
        summary,
        outgoingName: data.outgoing.web_name,
        incomingName: data.candidate.web_name,
      };
      setNotice(null);
      return;
    }
    setNotice({
      kind: "earlier",
      text:
        result.reason === "stale_preview"
          ? "Plan changed, preview again"
          : result.reason === "busy"
            ? "The Planner is saving other changes. Try again when they finish."
            : result.reason === "pinned_exists"
              ? "Another transfer confirmation is still unresolved."
              : result.reason === "not_ready"
                ? "This plan is not ready for transfers yet."
                : "This plan no longer exists.",
    });
  }, [preview, commit]);

  const previewAgain = useCallback(() => {
    const target = selectedRef.current;
    if (target !== null) void loadPreview(target, { syncPlan: true });
  }, [loadPreview]);

  const submissionOf = useCallback(
    (submissionId: string | undefined): OwnSubmission | null => {
      if (submissionId === undefined) return null;
      const view = commit.getView();
      if (view.pinned?.submissionId === submissionId && view.details) {
        return { submissionId, ...view.details, summary: view.label ?? "" };
      }
      return own.current?.submissionId === submissionId ? own.current : null;
    },
    [commit],
  );

  const refreshAfterConflict = useCallback(async () => {
    const submission = submissionOf(commit.getView().pinned?.submissionId);
    const result = await commit.abandon();
    if (result.type === "refresh_failed") {
      setNotice({
        kind: "earlier",
        text: `Could not refresh the plan: ${result.message}`,
      });
      return;
    }
    // The plan moved on the server, so the list this page shows is stale whichever transfer clashed.
    refreshListRef.current?.();
    if (submission && !inScope(submission)) {
      // The clash belongs to another scope: keep this page and point to that transfer.
      setNotice({
        kind: "earlier",
        text: `The plan was refreshed. The transfer you confirmed earlier${
          submission.summary ? ` (${submission.summary})` : ""
        } was not submitted; preview it again to add it.`,
        recoverHref: recoverHrefFor(submission),
      });
      return;
    }
    const target = submission?.playerInId ?? selectedRef.current;
    if (target !== null) {
      await loadPreview(target, { syncPlan: true });
    } else {
      setPreview({ kind: "idle" });
    }
  }, [commit, loadPreview, submissionOf, inScope, recoverHrefFor]);

  const stopTracking = useCallback(async () => {
    const before = commit.getView();
    const summary =
      before.label ??
      (own.current?.submissionId === before.pinned?.submissionId
        ? (own.current?.summary ?? null)
        : null);
    const stopped = submissionOf(before.pinned?.submissionId);
    const result = await commit.abandon();
    if (result.type === "abandoned") {
      // Only a preview of the stopped transfer itself, in its own scope, is closed.
      if (
        stopped !== null &&
        inScope(stopped) &&
        stopped.playerInId === selectedRef.current
      ) {
        sequence.current += 1;
        selectedRef.current = null;
        setPreview({ kind: "idle" });
      }
      setNotice({ kind: "not_added", summary });
    } else if (result.type === "refresh_failed") {
      setNotice({
        kind: "earlier",
        text: `Could not refresh the plan: ${result.message}`,
      });
    }
  }, [commit, submissionOf, inScope]);

  const record = view.pinned;
  const unresolvedLabel =
    view.label ??
    (own.current?.submissionId === record?.submissionId
      ? (own.current?.summary ?? null)
      : null);
  let pinnedModel: CommitRegionModel | null = null;
  if (record?.status === "sending") {
    pinnedModel = {
      kind: "saving",
      reason: "A transfer confirmation is already being saved.",
    };
  } else if (record?.status === "unknown") {
    pinnedModel = {
      kind: "unknown",
      message: record.message,
      onCheck: () => void commit.reconcile(),
      onRetry: () => commit.retry(),
    };
  } else if (record?.status === "pending_unsaved") {
    pinnedModel = {
      kind: "pending_unsaved",
      onCheck: () => void commit.reconcile(),
      onRetry: () => commit.retry(),
      onStop: () => void stopTracking(),
    };
  } else if (record?.status === "conflict") {
    pinnedModel = {
      kind: "conflict",
      message: record.message,
      // Only a conflict in the page's own scope reloads a preview here.
      previewsAgain: submissionOf(record.submissionId)
        ? inScope(submissionOf(record.submissionId))
        : true,
      onRefresh: () => void refreshAfterConflict(),
    };
  }

  let model: CommitRegionModel | null = null;
  if (preview.kind === "ok") {
    const data = preview.data;
    if (record) {
      // Controls for the unresolved submission live in their own region, not in this preview.
      const named = unresolvedLabel ?? "an earlier transfer";
      model = {
        kind: "disabled",
        reason: !pinnedModel
          ? "Finishing the previous confirmation. One moment."
          : record.status === "sending"
            ? `A transfer confirmation is already being saved (${named}).`
            : `A transfer confirmation is still unresolved (${named}). Resolve it above first.`,
      };
    } else if (runId === null || data.projection.run_id !== runId) {
      model = {
        kind: "disabled",
        reason: "The projection run changed since this preview, preview again",
        onPreviewAgain: previewAgain,
      };
    } else if (!data.confirmable || !data.commit) {
      model = { kind: "disabled", reason: notConfirmableReason(data) };
    } else if (view.acknowledgedRevision !== data.commit.expected_revision) {
      model = {
        kind: "disabled",
        reason: "Plan changed, preview again",
        onPreviewAgain: previewAgain,
      };
    } else if (!view.idle) {
      model = {
        kind: "disabled",
        reason: "The Planner is saving other changes. Wait for them to finish.",
      };
    } else {
      model = {
        kind: "ready",
        revision: data.commit.expected_revision,
        onConfirm: confirm,
      };
    }
  }

  return {
    view,
    preview,
    notice,
    model,
    // An unresolved submission stays actionable, apart from whichever candidate is previewed.
    unresolved: pinnedModel,
    unresolvedLabel,
    openPreview,
    closePreview,
    dismissNotice: () => setNotice(null),
  };
}
