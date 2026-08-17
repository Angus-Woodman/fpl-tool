import type { LineupSummary, TransferPreviewResponse } from "@/lib/api";

export type TransferPreviewState =
  | { type: "loading" }
  | { type: "error"; message: string }
  | { type: "unavailable"; message: string }
  | { type: "ready"; data: TransferPreviewResponse };

function formatSignedPoints(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

function LineupSummaryList({
  lineup,
  resolveName,
}: {
  lineup: LineupSummary;
  resolveName: (playerId: number) => string;
}): JSX.Element {
  return (
    <div className="text-sm text-slate-700">
      <p>
        Captain: <span className="font-medium">{resolveName(lineup.captain)}</span> ·
        Vice-captain: <span className="font-medium">{resolveName(lineup.vice_captain)}</span>
      </p>
      <p className="mt-1 text-xs text-slate-500">
        Starting XI: {lineup.starting_xi.map(resolveName).join(", ")}
      </p>
    </div>
  );
}

export function TransferPreview({
  state,
  outgoingName,
  incomingName,
  onClose,
  resolveName,
  onApply,
  applying = false,
}: {
  state: TransferPreviewState;
  outgoingName: string;
  incomingName: string;
  onClose: () => void;
  resolveName: (playerId: number) => string;
  onApply?: () => void;
  applying?: boolean;
}): JSX.Element {
  return (
    <section className="rounded-xl border border-slate-300 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-base font-semibold text-slate-900">
          Preview: {outgoingName} &rarr; {incomingName}
        </h3>
        <button type="button" className="text-sm text-slate-600 underline" onClick={onClose}>
          Close
        </button>
      </div>

      {state.type === "loading" && (
        <p className="mt-3 text-sm text-slate-600">Loading preview...</p>
      )}
      {state.type === "error" && <p className="mt-3 text-sm text-red-700">{state.message}</p>}
      {state.type === "unavailable" && (
        <p className="mt-3 text-sm text-red-700">{state.message}</p>
      )}

      {state.type === "ready" && (
        <div className="mt-3 space-y-3">
          {!state.data.is_legal && (
            <p className="text-sm text-red-700">
              This transfer is not currently legal: {state.data.errors.join(", ")}
            </p>
          )}

          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Resulting bank
              </p>
              <p className="mt-1 text-lg font-semibold text-slate-900">
                £{state.data.resulting_bank.toFixed(1)}m
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Current XI total
              </p>
              <p className="mt-1 text-lg font-semibold text-slate-900">
                {state.data.lineup_before?.captain_adjusted_points.toFixed(1) ?? "-"}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Post-transfer XI total
              </p>
              <p className="mt-1 text-lg font-semibold text-slate-900">
                {state.data.lineup_after?.captain_adjusted_points.toFixed(1) ?? "-"}
              </p>
            </div>
          </div>

          <p className="text-sm text-slate-700">
            Projected gain: {formatSignedPoints(state.data.projected_team_gain)} xPts (GW{" "}
            {state.data.target_gameweek_number})
          </p>

          {state.data.lineup_after && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Resulting recommended XI
              </p>
              <LineupSummaryList lineup={state.data.lineup_after} resolveName={resolveName} />
              {(state.data.captain_changed || state.data.vice_captain_changed) && (
                <p className="mt-1 text-xs text-amber-800">
                  {state.data.captain_changed && "Captain changes. "}
                  {state.data.vice_captain_changed && "Vice-captain changes."}
                </p>
              )}
            </div>
          )}

          {onApply && (
            <button
              type="button"
              className="rounded-md border border-emerald-300 bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
              onClick={onApply}
              disabled={!state.data.is_legal || applying}
            >
              {applying ? "Applying..." : "Apply transfer"}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
