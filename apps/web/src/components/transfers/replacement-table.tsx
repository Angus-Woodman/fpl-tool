import type { RankedTransferCandidate, TransferHorizon } from "@/lib/api";
import { describeLegalityReasons } from "@/components/transfers/legality-reasons";
import { playingStatusWarning } from "@/components/transfers/playing-status";

function sortedByHorizon(
  candidates: RankedTransferCandidate[],
  horizon: TransferHorizon,
): RankedTransferCandidate[] {
  // Purely re-sorts already-fetched, backend-computed gains -- no domain
  // logic (legality, budget, gain) is recalculated here.
  return [...candidates].sort((left, right) => {
    const gainDifference =
      (right.team_gain_by_horizon[horizon] ?? 0) - (left.team_gain_by_horizon[horizon] ?? 0);
    if (gainDifference !== 0) {
      return gainDifference;
    }
    return left.player_id - right.player_id;
  });
}

function formatSignedPoints(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

function formatMoney(value: number): string {
  return `${value < 0 ? "-" : ""}£${Math.abs(value).toFixed(1)}m`;
}

export function ReplacementTable({
  candidates,
  horizon,
  onPreview,
}: {
  candidates: RankedTransferCandidate[];
  horizon: TransferHorizon;
  onPreview?: (playerId: number) => void;
}): JSX.Element {
  if (candidates.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
        No eligible replacements were found for this player right now.
      </p>
    );
  }

  const rows = sortedByHorizon(candidates, horizon);

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
          <th className="py-2 pr-3">Player</th>
          <th className="py-2 pr-3">Team</th>
          <th className="py-2 pr-3">Price</th>
          <th className="py-2 pr-3">Resulting bank</th>
          <th className="py-2 pr-3">1 GW</th>
          <th className="py-2 pr-3">3 GW</th>
          <th className="py-2 pr-3">5 GW</th>
          {onPreview && <th className="py-2 pr-3">&nbsp;</th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((candidate) => {
          const statusWarning = playingStatusWarning(candidate.status);
          return (
            <tr
              key={candidate.player_id}
              data-availability={candidate.is_legal ? "available" : "unavailable"}
              className={`border-b border-slate-100 ${candidate.is_legal ? "" : "bg-slate-50"}`}
            >
              <td className="py-2 pr-3 font-medium text-slate-900">
                {candidate.web_name}
                {statusWarning && (
                  <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-normal text-amber-900">
                    {statusWarning}
                  </span>
                )}
                {!candidate.is_legal && (
                  <span className="mt-1 block text-xs font-normal text-red-700">
                    Unavailable: {describeLegalityReasons(candidate.unavailable_reasons).join("; ")}
                  </span>
                )}
              </td>
              <td className="py-2 pr-3 text-slate-700">{candidate.team_short_name}</td>
              <td className="py-2 pr-3 text-slate-700">{formatMoney(candidate.price)}</td>
              <td className="py-2 pr-3 text-slate-700">{formatMoney(candidate.resulting_bank)}</td>
              {([1, 3, 5] as const).map((column) => (
                <td
                  key={column}
                  className={`py-2 pr-3 ${column === horizon ? "font-semibold text-slate-900" : "text-slate-700"}`}
                >
                  {formatSignedPoints(candidate.team_gain_by_horizon[column] ?? 0)} xPts
                </td>
              ))}
              {onPreview && (
                <td className="py-2 pr-3">
                  <button
                    type="button"
                    className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs hover:bg-slate-50"
                    onClick={() => onPreview(candidate.player_id)}
                  >
                    Preview transfer
                  </button>
                </td>
              )}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
