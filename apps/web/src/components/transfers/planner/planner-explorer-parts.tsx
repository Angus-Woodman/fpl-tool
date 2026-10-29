import Link from "next/link";

import {
  formatGameweekRanges,
  formatTenths,
  horizonLabel,
  missingGameweeks,
} from "@/components/transfers/planner/planner-format";
import type {
  PlanExplorerOutgoing,
  PlanTransferExplorerResponse,
} from "@/lib/api";

export const ALERT_CLASSES =
  "rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800";

export function unavailableHeading(code: string, gameweek: number): string {
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

export function PlanProblem({
  message,
  planId,
}: {
  message: string;
  planId?: number;
}): JSX.Element {
  return (
    <div role="alert" className={ALERT_CLASSES}>
      <p>{message}</p>
      <Link
        href={planId === undefined ? "/plans" : `/plans/${planId}`}
        className="mt-2 inline-flex min-h-6 items-center font-medium underline"
      >
        {planId === undefined ? "Open the Planner" : "Back to plan"}
      </Link>
    </div>
  );
}

export function OutgoingSummary({
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

export function ProjectionCoverage({
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
