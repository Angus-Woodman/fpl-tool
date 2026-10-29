"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { HorizonSelector } from "@/components/transfers/horizon-selector";
import { OutgoingPlayerSelector } from "@/components/transfers/outgoing-player-selector";
import { PlannerCandidateTable } from "@/components/transfers/planner/planner-candidate-table";
import { PlannerContextBanner } from "@/components/transfers/planner/planner-context-banner";
import {
  ALERT_CLASSES,
  OutgoingSummary,
  PlanProblem,
  ProjectionCoverage,
  unavailableHeading,
} from "@/components/transfers/planner/planner-explorer-parts";
import {
  PlannerCommitRegion,
  PlannerTransferPreview,
} from "@/components/transfers/planner/planner-transfer-preview";
import {
  usePlannerConfirmation,
  type ConfirmationNotice,
} from "@/components/transfers/planner/use-planner-confirmation";
import { ProjectionRunBadge } from "@/components/team/projection-run-badge";
import {
  fetchPlan,
  fetchPlanTransferExplorer,
  type PlanResponse,
  type PlanTransferExplorerResponse,
  type TransferHorizon,
} from "@/lib/api";
import {
  createPlannerCommit,
  type PlannerCommitFactory,
} from "@/lib/planner-commit";
import {
  buildPlanBoardHref,
  buildPlannerExplorerHref,
} from "@/lib/planner-explorer-url";

type PlanState =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "error" }
  | { kind: "ready"; plan: PlanResponse };

type ListState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: PlanTransferExplorerResponse }
  | { kind: "plan_missing" }
  | { kind: "plan_not_ready" }
  | { kind: "player_not_found" }
  | {
      kind: "unavailable";
      code: string;
      message: string;
      missingPlayerIds: number[];
    }
  | { kind: "error" };

type LoadedContext = {
  planId: number;
  gameweek: number;
  playerOutId: number;
  horizon: TransferHorizon;
  runId: number;
};

type ExplorerProps = {
  planId: number;
  gameweek: number;
  playerOutId: number | null;
  horizon: TransferHorizon;
  runId: number | null;
};

const NOT_ADDED_NOTICE =
  "Transfer not added to your plan. The server may still hold a pending record of it; that record is not a saved transfer and this app will not retry it.";

function ConfirmationNoticeView({
  notice,
  planId,
  gameweek,
  chooseHref,
  onDismiss,
}: {
  notice: ConfirmationNotice;
  planId: number;
  gameweek: number;
  chooseHref: string;
  onDismiss: () => void;
}): JSX.Element {
  const dismiss = (
    <button
      type="button"
      onClick={onDismiss}
      className="mt-2 inline-flex min-h-6 items-center text-sm font-medium underline"
    >
      Dismiss
    </button>
  );
  switch (notice.kind) {
    case "rejected":
      return (
        <div
          role="alert"
          data-testid="commit-rejection"
          className={ALERT_CLASSES}
        >
          <p className="font-medium">
            Not added{notice.summary ? ` (${notice.summary})` : ""}:{" "}
            {notice.message}
          </p>
          {notice.code === "prices_changed" && (
            <p className="mt-1">
              Check the current prices in a fresh preview and confirm again to
              add it. Nothing was submitted automatically.
            </p>
          )}
          {dismiss}
        </div>
      );
    case "not_added":
      return (
        <div
          role="status"
          data-testid="not-added-notice"
          className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
        >
          <p>{NOT_ADDED_NOTICE}</p>
          {notice.summary && (
            <p className="mt-1">Stopped tracking: {notice.summary}.</p>
          )}
          <p className="mt-1">Preview the transfer again to confirm it.</p>
          {dismiss}
        </div>
      );
    case "committed":
      return (
        <div
          role="status"
          data-testid="commit-success"
          className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900"
        >
          <p className="font-medium">
            Transfer added to your plan: {notice.summary}.
          </p>
          <div className="mt-2 flex flex-wrap gap-4">
            <Link
              href={buildPlanBoardHref(planId, gameweek)}
              className="inline-flex min-h-6 items-center font-medium underline"
            >
              Back to plan
            </Link>
            <Link
              href={chooseHref}
              className="inline-flex min-h-6 items-center font-medium underline"
            >
              Explore another transfer
            </Link>
          </div>
        </div>
      );
    case "earlier":
      return (
        <div
          role="status"
          data-testid="commit-earlier"
          className="rounded-lg border border-slate-300 bg-slate-50 p-4 text-sm text-slate-800"
        >
          <p>{notice.text}</p>
          {dismiss}
        </div>
      );
  }
}

function ExplorerWorkspace({
  initialPlan,
  commitFactory,
  planId,
  gameweek,
  playerOutId,
  horizon,
  runId,
}: ExplorerProps & {
  initialPlan: PlanResponse;
  commitFactory: PlannerCommitFactory;
}): JSX.Element {
  const router = useRouter();
  const [commit] = useState(() => commitFactory(initialPlan));
  const [listState, setListState] = useState<ListState>({ kind: "idle" });
  const loadedRef = useRef<LoadedContext | null>(null);

  useEffect(() => {
    if (playerOutId === null) {
      loadedRef.current = null;
      setListState({ kind: "idle" });
      return;
    }
    const loaded = loadedRef.current;
    if (
      loaded !== null &&
      runId !== null &&
      loaded.planId === planId &&
      loaded.gameweek === gameweek &&
      loaded.playerOutId === playerOutId &&
      loaded.horizon === horizon &&
      loaded.runId === runId
    ) {
      // The address was only updated to pin the run we already loaded.
      return;
    }

    let cancelled = false;
    setListState({ kind: "loading" });
    fetchPlanTransferExplorer({
      planId,
      gameweek,
      playerOutId,
      primaryHorizon: horizon,
      projectionRunId: runId,
    })
      .then((result) => {
        if (cancelled) {
          return;
        }
        switch (result.type) {
          case "ok": {
            const pinnedRun = result.data.projection.run_id;
            loadedRef.current = {
              planId,
              gameweek,
              playerOutId,
              horizon,
              runId: pinnedRun,
            };
            setListState({ kind: "ok", data: result.data });
            if (runId === null) {
              router.replace(
                buildPlannerExplorerHref({
                  planId,
                  gameweek,
                  playerOutId,
                  horizon,
                  runId: pinnedRun,
                }),
              );
            }
            return;
          }
          case "plan_not_found":
            setListState({ kind: "plan_missing" });
            return;
          case "plan_not_ready":
            setListState({ kind: "plan_not_ready" });
            return;
          case "player_not_found":
            setListState({ kind: "player_not_found" });
            return;
          case "unavailable":
            setListState({
              kind: "unavailable",
              code: result.code,
              message: result.message,
              missingPlayerIds: result.missingPlayerIds,
            });
            return;
        }
      })
      .catch(() => {
        if (!cancelled) {
          setListState({ kind: "error" });
        }
      });
    return () => {
      cancelled = true;
    };
    // `router` is stable for the lifetime of the page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planId, gameweek, playerOutId, horizon, runId]);

  const pinnedRunId =
    runId ??
    (listState.kind === "ok" ? listState.data.projection.run_id : null);
  const confirmation = usePlannerConfirmation({
    planId,
    gameweek,
    playerOutId,
    horizon,
    runId: pinnedRunId,
    commit,
  });

  // The coordinator's acknowledged plan is the freshest the Planner and Explorer share.
  const plan = confirmation.view.plan;
  if (
    plan.foundation_state !== "ready" ||
    listState.kind === "plan_not_ready"
  ) {
    return (
      <PlanProblem
        message="This plan is not ready for transfers yet."
        planId={planId}
      />
    );
  }
  if (listState.kind === "plan_missing") {
    return <PlanProblem message="This plan no longer exists." />;
  }
  const week = plan.gameweeks.find((item) => item.gameweek_number === gameweek);
  if (!week) {
    return (
      <PlanProblem
        message={`GW${gameweek} is not part of this plan.`}
        planId={planId}
      />
    );
  }

  // Switching players keeps the horizon and the pinned run; only "Use the latest run" changes the run.
  const chooseHref = buildPlannerExplorerHref({
    planId,
    gameweek,
    horizon,
    runId: pinnedRunId,
  });

  function navigateWith(
    mode: "push" | "replace",
    next: {
      playerOutId?: number | null;
      horizon?: TransferHorizon;
      runId?: number | null;
    },
  ): void {
    const href = buildPlannerExplorerHref({
      planId,
      gameweek,
      playerOutId:
        next.playerOutId === undefined ? playerOutId : next.playerOutId,
      horizon: next.horizon ?? horizon,
      runId: next.runId === undefined ? pinnedRunId : next.runId,
    });
    if (mode === "push") {
      router.push(href);
    } else {
      router.replace(href);
    }
  }

  const choosePlayerLink = (
    <Link
      href={chooseHref}
      className="mt-2 inline-flex min-h-6 items-center text-sm font-medium underline"
    >
      Choose a different player
    </Link>
  );

  const completed = confirmation.notice?.kind === "committed";
  let body: JSX.Element;
  if (playerOutId === null) {
    body = (
      <OutgoingPlayerSelector
        players={week.players}
        onSelect={(id) => navigateWith("push", { playerOutId: id })}
      />
    );
  } else if (completed) {
    body = <></>;
  } else if (listState.kind === "idle" || listState.kind === "loading") {
    body = (
      <p role="status" className="text-sm text-slate-600">
        Loading replacements...
      </p>
    );
  } else if (listState.kind === "player_not_found") {
    body = (
      <div role="alert" className={ALERT_CLASSES}>
        <p>This player was not found in the plan.</p>
        {choosePlayerLink}
      </div>
    );
  } else if (listState.kind === "error") {
    body = (
      <p role="alert" className={ALERT_CLASSES}>
        Could not load replacements. Try again shortly.
      </p>
    );
  } else if (listState.kind === "unavailable") {
    body = (
      <div role="alert" className={ALERT_CLASSES}>
        <p className="font-medium">
          {unavailableHeading(listState.code, gameweek)}
        </p>
        <p className="mt-1">{listState.message}</p>
        {listState.missingPlayerIds.length > 0 && (
          <p className="mt-1">
            Missing projections for:{" "}
            {listState.missingPlayerIds.map((id) => `#${id}`).join(", ")}
          </p>
        )}
        {choosePlayerLink}
      </div>
    );
  } else {
    const data = listState.data;
    const withheld = data.projection.unprojected_candidate_ids;
    const preview = confirmation.preview;
    body = (
      <div className="space-y-4">
        <OutgoingSummary
          outgoing={data.outgoing}
          gameweek={gameweek}
          accounting={data.accounting_before}
        />
        {choosePlayerLink}
        <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center gap-3">
            <HorizonSelector
              value={horizon}
              onChange={(next) => navigateWith("replace", { horizon: next })}
            />
            <ProjectionRunBadge
              modelVersion={data.projection.model_version}
              generatedAt={data.projection.generated_at}
              projectionRunId={data.projection.run_id}
            />
          </div>
          {data.projection.newer_run_available && (
            <div
              data-testid="newer-run-notice"
              className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900"
            >
              A newer projection run is available. This list stays on run #
              {data.projection.run_id} so results stay comparable.{" "}
              <button
                type="button"
                className="inline-flex min-h-6 items-center font-medium underline"
                onClick={() => navigateWith("replace", { runId: null })}
              >
                Use the latest run
              </button>
            </div>
          )}
          <ProjectionCoverage
            projection={data.projection}
            gameweek={gameweek}
          />
        </section>
        {preview.kind === "loading" && (
          <p role="status" className="text-sm text-slate-600">
            Loading preview...
          </p>
        )}
        {preview.kind === "error" && (
          <div
            role="alert"
            data-testid="preview-error"
            className={ALERT_CLASSES}
          >
            <p>{preview.message}</p>
            {preview.missingPlayerIds.length > 0 && (
              <p className="mt-1">
                Missing projections for:{" "}
                {preview.missingPlayerIds.map((id) => `#${id}`).join(", ")}
              </p>
            )}
          </div>
        )}
        {preview.kind === "ok" && confirmation.model && (
          <PlannerTransferPreview
            data={preview.data}
            gameweek={gameweek}
            horizon={horizon}
            onClose={confirmation.closePreview}
          >
            <PlannerCommitRegion
              gameweek={gameweek}
              model={confirmation.model}
            />
          </PlannerTransferPreview>
        )}
        {withheld.length > 0 && (
          <p
            data-testid="withheld-candidates"
            className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
          >
            {withheld.length} player{withheld.length === 1 ? "" : "s"} withheld:
            no complete projection for the evaluated gameweeks (
            {withheld.map((id) => `#${id}`).join(", ")}).
          </p>
        )}
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          {data.candidates.length === 0 ? (
            <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
              No replacement candidates are available for this player.
            </p>
          ) : (
            <PlannerCandidateTable
              candidates={data.candidates}
              horizons={data.projection.horizons}
              horizon={horizon}
              bankIsEstimated={data.outgoing.selling_provisional}
              onPreview={confirmation.openPreview}
            />
          )}
        </section>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PlannerContextBanner
        planId={planId}
        planName={plan.name}
        gameweek={gameweek}
      />
      {confirmation.notice && (
        <ConfirmationNoticeView
          notice={confirmation.notice}
          planId={planId}
          gameweek={gameweek}
          chooseHref={chooseHref}
          onDismiss={confirmation.dismissNotice}
        />
      )}
      {confirmation.unresolved && (
        <PlannerCommitRegion
          gameweek={gameweek}
          model={confirmation.unresolved}
          label={confirmation.unresolvedLabel}
          standalone
        />
      )}
      {body}
    </div>
  );
}

export function PlannerTransferExplorer({
  planId,
  gameweek,
  playerOutId,
  horizon,
  runId,
  commit = createPlannerCommit,
}: ExplorerProps & { commit?: PlannerCommitFactory }): JSX.Element {
  const [planState, setPlanState] = useState<PlanState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    setPlanState({ kind: "loading" });
    fetchPlan(planId)
      .then((plan) => {
        if (!cancelled) {
          setPlanState(
            plan === null ? { kind: "missing" } : { kind: "ready", plan },
          );
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPlanState({ kind: "error" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [planId]);

  if (planState.kind === "loading") {
    return (
      <p role="status" className="text-sm text-slate-600">
        Loading plan...
      </p>
    );
  }
  if (planState.kind === "missing") {
    return <PlanProblem message="This plan no longer exists." />;
  }
  if (planState.kind === "error") {
    return (
      <PlanProblem message="Could not load the plan. Try again shortly." />
    );
  }
  return (
    <ExplorerWorkspace
      key={planId}
      initialPlan={planState.plan}
      commitFactory={commit}
      planId={planId}
      gameweek={gameweek}
      playerOutId={playerOutId}
      horizon={horizon}
      runId={runId}
    />
  );
}
