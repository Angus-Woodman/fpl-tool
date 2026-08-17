import type { RankedTransferCandidate, TransferHorizon } from "@/lib/api";

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

export function ReplacementTable({
  candidates,
  horizon,
}: {
  candidates: RankedTransferCandidate[];
  horizon: TransferHorizon;
}): JSX.Element {
  if (candidates.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
        No legal, affordable replacements were found for this player right now.
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
        </tr>
      </thead>
      <tbody>
        {rows.map((candidate) => (
          <tr key={candidate.player_id} className="border-b border-slate-100">
            <td className="py-2 pr-3 font-medium text-slate-900">{candidate.web_name}</td>
            <td className="py-2 pr-3 text-slate-700">{candidate.team_short_name}</td>
            <td className="py-2 pr-3 text-slate-700">£{candidate.price.toFixed(1)}m</td>
            <td className="py-2 pr-3 text-slate-700">£{candidate.resulting_bank.toFixed(1)}m</td>
            {([1, 3, 5] as const).map((column) => (
              <td
                key={column}
                className={`py-2 pr-3 ${column === horizon ? "font-semibold text-slate-900" : "text-slate-700"}`}
              >
                {formatSignedPoints(candidate.team_gain_by_horizon[column] ?? 0)} xPts
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
