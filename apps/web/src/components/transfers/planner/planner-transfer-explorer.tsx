"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { HorizonSelector } from "@/components/transfers/horizon-selector";
import { OutgoingPlayerSelector } from "@/components/transfers/outgoing-player-selector";
import { PlannerCandidateTable } from "@/components/transfers/planner/planner-candidate-table";
import { PlannerContextBanner } from "@/components/transfers/planner/planner-context-banner";
import {
  formatGameweekRanges,
  formatTenths,
  horizonLabel,
  missingGameweeks,
} from "@/components/transfers/planner/planner-format";
import { ProjectionRunBadge } from "@/components/team/projection-run-badge";
import {
  fetchPlan,
  fetchPlanTransferExplorer,
  type PlanExplorerOutgoing,
  type PlanResponse,
  type PlanTransferExplorerResponse,
  type TransferHorizon,
} from "@/lib/api";
import { buildPlannerExplorerHref } from "@/lib/planner-explorer-url";

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

const ALERT_CLASSES =
  "rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800";

function unavailableHeading(code: string, gameweek: number): string {
  switch (code) {
    case "gameweek_not_in_plan":
      return `GW${gameweek} is not part of this plan.`;
    case "evaluation_blocked":
      return "This gameweek cannot be evaluated until the plan's earlier problems are fixed.";
    case "player_not_in_squad":
      return `This player is not in your squad for GW${gameweek}.`;
    case "no_projection_run":
      return "No projections are available yet.";
    case "run_not_found":
      return "The pinned projection run no longer exists.";
    case "run_model_mismatch":
      return "The projection run was produced by a different model than this plan expects.";
    case "gameweek_not_projected":
      return "No projections are available for this gameweek.";
    case "missing_projections":
      return "Projections are missing for some players, so replacements cannot be ranked.";
    case "selectability_unknown":
      return "Transfer availability could not be confirmed. Refresh to try again.";
    case "invalid_money":
      return "A money value in this plan is invalid, so transfers cannot be priced.";
    case "invalid_horizon":
      return "The ranking horizon is not valid.";
    default:
      return "This transfer could not be explored.";
  }
}

function PlanProblem({
  message,
  planId,
}: {
  message: string;
  planId?: number;
}): JSX.Element {
  return (
    <div role="alert" className={ALERT_CLASSES}>
      <p>{message}</p>
      <a
        href={planId === undefined ? "/plans" : `/plans/${planId}`}
        className="mt-2 inline-block font-medium underline"
      >
        {planId === undefined ? "Open the Planner" : "Back to plan"}
      </a>
    </div>
  );
}

function OutgoingSummary({
  outgoing,
  gameweek,
  accounting,
}: {
  outgoing: PlanExplorerOutgoing;
  gameweek: number;
  accounting: PlanTransferExplorerResponse["accounting_before"];
}): JSX.Element {
  const purchaseEstimated = outgoing.purchase_basis.confirmation === "assumed";
  const isEdit = outgoing.operation === "edit_transfer";
  return (
    <section
      aria-label="Outgoing player"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <h2 className="text-lg font-semibold text-slate-900">
        Transferring out {outgoing.web_name}
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        {outgoing.position} · {outgoing.team_short_name} · GW{gameweek}
      </p>
      {isEdit && (
        <p className="mt-2 text-sm text-slate-700">
          Replaces a transfer already planned in this gameweek.
        </p>
      )}
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-slate-500">Purchase price</dt>
          <dd data-testid="purchase-price">
            {formatTenths(outgoing.purchase_price_tenths)}
            {purchaseEstimated && (
              <span className="ml-1 text-xs text-slate-500">Estimated</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Market price</dt>
          <dd>{formatTenths(outgoing.market_price_tenths)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Selling price</dt>
          <dd data-testid="selling-price">
            {outgoing.selling_price_tenths === null ? (
              "No separate sale"
            ) : (
              <>
                {formatTenths(outgoing.selling_price_tenths)}
                {outgoing.selling_provisional && (
                  <span className="ml-1 text-xs text-slate-500">Estimated</span>
                )}
              </>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Bank before</dt>
          <dd>{formatTenths(accounting.closing_bank_tenths)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Free transfers</dt>
          <dd>
            {accounting.unlimited_transfers
              ? "Unlimited"
              : (accounting.free_transfers_available ?? "-")}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Points hit</dt>
          <dd>{accounting.points_hit ?? "-"}</dd>
        </div>
      </dl>
      {accounting.provisional && (
        <p className="mt-3 text-xs text-slate-600">
          Bank and transfer figures are provisional until purchase prices are
          confirmed.
        </p>
      )}
    </section>
  );
}

function ProjectionCoverage({
  projection,
  gameweek,
}: {
  projection: PlanTransferExplorerResponse["projection"];
  gameweek: number;
}): JSX.Element {
  return (
    <section aria-label="Projection coverage" className="space-y-2 text-sm">
      {projection.limited_to_selected_gameweek && (
        <p
          data-testid="free-hit-limit"
          className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-900"
        >
          {projection.limited_reason === "free_hit_gameweek"
            ? `Free Hit gameweek: only GW${gameweek} is evaluated for every horizon, because a Free Hit squad reverts afterwards.`
            : `Only GW${gameweek} is evaluated for every horizon.`}
        </p>
      )}
      <ul className="space-y-1 text-slate-700">
        {projection.horizons.map((info) => {
          const missing = missingGameweeks(info);
          return (
            <li key={info.horizon}>
              <span className="font-medium">
                {info.horizon} GW{info.horizon > 1 ? "s" : ""}:
              </span>{" "}
              {horizonLabel(info)} evaluated
              {info.saved_plan_gameweeks.length > 0 &&
                `; saved plan ${formatGameweekRanges(info.saved_plan_gameweeks)}`}
              {info.assumed_gameweeks.length > 0 &&
                `; assumed continuation ${formatGameweekRanges(info.assumed_gameweeks)}`}
              {info.partial && (
                <span className="ml-1 font-medium text-amber-900">
                  Partial coverage:{" "}
                  {missing.length > 0
                    ? `${formatGameweekRanges(missing)} not projected`
                    : "some gameweeks are not projected"}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function PlannerTransferExplorer({
  planId,
  gameweek,
  playerOutId,
  horizon,
  runId,
}: {
  planId: number;
  gameweek: number;
  playerOutId: number | null;
  horizon: TransferHorizon;
  runId: number | null;
}): JSX.Element {
  const router = useRouter();
  const [planState, setPlanState] = useState<PlanState>({ kind: "loading" });
  const [listState, setListState] = useState<ListState>({ kind: "idle" });
  const loadedRef = useRef<LoadedContext | null>(null);

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

  const plan = planState.plan;
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

  const pinnedRunId =
    runId ??
    (listState.kind === "ok" ? listState.data.projection.run_id : null);

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

  let body: JSX.Element;
  if (playerOutId === null) {
    body = (
      <OutgoingPlayerSelector
        players={week.players}
        onSelect={(id) => navigateWith("push", { playerOutId: id })}
      />
    );
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
        <a
          href={buildPlannerExplorerHref({ planId, gameweek })}
          className="mt-2 inline-block font-medium underline"
        >
          Choose a different player
        </a>
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
        <a
          href={buildPlannerExplorerHref({ planId, gameweek })}
          className="mt-2 inline-block font-medium underline"
        >
          Choose a different player
        </a>
      </div>
    );
  } else {
    const data = listState.data;
    const withheld = data.projection.unprojected_candidate_ids;
    body = (
      <div className="space-y-4">
        <OutgoingSummary
          outgoing={data.outgoing}
          gameweek={gameweek}
          accounting={data.accounting_before}
        />
        <a
          href={buildPlannerExplorerHref({ planId, gameweek })}
          className="inline-block text-sm underline"
        >
          Choose a different player
        </a>
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
                className="font-medium underline"
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
      {body}
    </div>
  );
}
