import { playingStatusWarning } from "@/components/transfers/playing-status";
import { describePlannerReasons } from "@/components/transfers/planner/planner-reasons";
import {
  formatSignedPoints,
  formatTenths,
  horizonLabel,
} from "@/components/transfers/planner/planner-format";
import type {
  PlanExplorerCandidate,
  PlanExplorerHorizonInfo,
  PlanExplorerHorizonKey,
  TransferHorizon,
} from "@/lib/api";

const HORIZON_KEYS: PlanExplorerHorizonKey[] = ["1", "3", "5"];

// Below the md breakpoint each row stacks into a labelled card so the state
// and plan impact are never hidden behind sideways scrolling.
const CELL =
  "py-2 pr-3 max-md:flex max-md:items-start max-md:justify-between max-md:gap-4 max-md:py-1 max-md:pr-0 before:text-xs before:font-medium before:uppercase before:tracking-wide before:text-slate-500 before:content-[attr(data-label)] md:before:content-none";

function StateCell({
  candidate,
}: {
  candidate: PlanExplorerCandidate;
}): JSX.Element {
  if (candidate.state === "available") {
    return (
      <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-900">
        Available
      </span>
    );
  }
  if (candidate.state === "blocked_by_later_decision") {
    return (
      <div className="text-xs text-amber-900">
        <span className="rounded bg-amber-100 px-2 py-0.5 font-medium">
          {candidate.conflict
            ? `Blocked by GW${candidate.conflict.gameweek} planned transfer`
            : "Blocked by a later planned transfer"}
        </span>
        {candidate.conflict && (
          <p className="mt-1 text-slate-600">{candidate.conflict.message}</p>
        )}
        {candidate.valid_through_gameweek !== null && (
          <p className="mt-1 text-slate-600">
            Valid through GW{candidate.valid_through_gameweek}
          </p>
        )}
      </div>
    );
  }
  return (
    <span className="text-xs text-red-700">
      Unavailable: {describePlannerReasons(candidate.reasons).join("; ")}
    </span>
  );
}

function PlanImpactCell({
  candidate,
  horizon,
}: {
  candidate: PlanExplorerCandidate;
  horizon: TransferHorizon;
}): JSX.Element {
  const impact =
    candidate.plan_impact_by_horizon[String(horizon) as PlanExplorerHorizonKey];
  return (
    <div data-testid="plan-impact" className="space-y-0.5 text-xs">
      <p data-testid="impact-saved-plan">
        Saved plan: {formatSignedPoints(impact.saved_plan)}
      </p>
      <p data-testid="impact-assumed-continuation">
        Assumed continuation (no plan decisions):{" "}
        {formatSignedPoints(impact.assumed_continuation)}
      </p>
      <p data-testid="impact-net" className="text-slate-600">
        Saved plan after transfer hit:{" "}
        {formatSignedPoints(impact.net_saved_plan)}
      </p>
      {impact.valid_through_gameweek !== null && (
        <p className="text-slate-600">
          Valid through GW{impact.valid_through_gameweek}
        </p>
      )}
    </div>
  );
}

function gainHeading(info: PlanExplorerHorizonInfo): string {
  return `Best-XI gain ${horizonLabel(info)}${info.partial ? " (partial)" : ""}`;
}

export function PlannerCandidateTable({
  candidates,
  horizons,
  horizon,
  bankIsEstimated,
}: {
  candidates: PlanExplorerCandidate[];
  horizons: PlanExplorerHorizonInfo[];
  horizon: TransferHorizon;
  bankIsEstimated: boolean;
}): JSX.Element {
  const selectedInfo = horizons.find((info) => info.horizon === horizon);
  const impactHeading = `Plan impact${selectedInfo ? ` (${horizonLabel(selectedInfo)})` : ""}`;
  // Rows keep the order the server returned: it ranks by best-XI gain over the
  // selected horizon, so the browser never re-ranks or recomputes gains.
  return (
    <div>
      <table
        aria-label="Replacement candidates"
        className="w-full border-collapse text-sm max-md:block"
      >
        <thead className="max-md:sr-only">
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="py-2 pr-3">Player</th>
            <th className="py-2 pr-3">Team</th>
            <th className="py-2 pr-3">Price</th>
            <th className="py-2 pr-3">Resulting bank</th>
            {horizons.map((info) => (
              <th key={info.horizon} className="py-2 pr-3">
                {gainHeading(info)}
              </th>
            ))}
            <th className="py-2 pr-3">{impactHeading}</th>
            <th className="py-2 pr-3">State</th>
            <th className="py-2 pr-3">&nbsp;</th>
          </tr>
        </thead>
        <tbody className="max-md:block">
          {candidates.map((candidate) => {
            const statusWarning = playingStatusWarning(candidate.status);
            return (
              <tr
                key={candidate.player_id}
                data-state={candidate.state}
                className={`border-b border-slate-100 align-top max-md:flex max-md:flex-col max-md:py-3 ${
                  candidate.state === "available" ? "" : "bg-slate-50"
                }`}
              >
                <td className="py-2 pr-3 font-medium text-slate-900 max-md:order-1 max-md:py-1 max-md:text-base">
                  {candidate.web_name}
                  {statusWarning && (
                    <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-normal text-amber-900">
                      {statusWarning}
                    </span>
                  )}
                </td>
                <td className={`${CELL} max-md:order-3`} data-label="Team">
                  {candidate.team_short_name}
                </td>
                <td className={`${CELL} max-md:order-3`} data-label="Price">
                  {formatTenths(candidate.price_tenths)}
                </td>
                <td
                  className={`${CELL} max-md:order-3`}
                  data-label="Resulting bank"
                >
                  <span>
                    {formatTenths(candidate.resulting_bank_tenths)}
                    {bankIsEstimated &&
                      candidate.resulting_bank_tenths !== null && (
                        <span className="ml-1 text-xs text-slate-500">
                          Estimated
                        </span>
                      )}
                    {candidate.points_hit_after !== null &&
                      candidate.points_hit_after > 0 && (
                        <span className="block text-xs text-slate-600">
                          Hit after: -{candidate.points_hit_after} pts
                        </span>
                      )}
                  </span>
                </td>
                {HORIZON_KEYS.map((key) => {
                  const info = horizons.find(
                    (item) => String(item.horizon) === key,
                  );
                  return (
                    <td
                      key={key}
                      data-label={
                        info ? gainHeading(info) : `Best-XI gain ${key} GW`
                      }
                      className={`${CELL} max-md:order-3 ${
                        key === String(horizon) ? "font-semibold" : ""
                      }`}
                    >
                      {formatSignedPoints(
                        candidate.best_xi_gain_by_horizon[key] ?? null,
                      )}
                    </td>
                  );
                })}
                <td
                  className={`${CELL} max-md:order-3`}
                  data-label={impactHeading}
                >
                  <PlanImpactCell candidate={candidate} horizon={horizon} />
                </td>
                <td className={`${CELL} max-md:order-2`} data-label="State">
                  <StateCell candidate={candidate} />
                </td>
                <td className={`${CELL} max-md:order-4`}>
                  <button
                    type="button"
                    disabled
                    aria-label={`Preview ${candidate.web_name} (not available yet)`}
                    className="cursor-not-allowed rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-400"
                  >
                    Preview
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500">
        Transfer preview is not available yet. Best-XI gain compares the saved
        squad with the swap for the evaluated gameweeks.
      </p>
    </div>
  );
}
