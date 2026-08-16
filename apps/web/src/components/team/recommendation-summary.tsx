import type { MyTeamRecommendationResponse } from "@/lib/api";
import { ProjectionRunBadge } from "@/components/team/projection-run-badge";

export type RecommendationState =
  | { type: "loading" }
  | { type: "no_squad" }
  | { type: "unavailable"; code: string; message: string; missingPlayerIds: number[] }
  | { type: "error"; message: string }
  | { type: "ready"; data: MyTeamRecommendationResponse };

export type ViewMode = "current" | "recommended";

function formatSignedPoints(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

export function RecommendationSummary({
  state,
  captainName,
  viceCaptainName,
  missingPlayerNames = [],
  viewMode,
  onViewModeChange,
  onRefreshProjections,
  refreshing,
}: {
  state: RecommendationState;
  captainName?: string;
  viceCaptainName?: string;
  missingPlayerNames?: string[];
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  onRefreshProjections: () => void;
  refreshing: boolean;
}): JSX.Element | null {
  if (state.type === "no_squad") {
    return null;
  }

  return (
    <section className="mb-5 rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          This Gameweek
        </h3>
        <div
          role="group"
          aria-label="Current vs recommended selection"
          className="inline-flex overflow-hidden rounded-md border border-slate-300"
        >
          <button
            type="button"
            aria-pressed={viewMode === "current"}
            className={`px-3 py-1.5 text-sm font-medium ${
              viewMode === "current" ? "bg-slate-900 text-white" : "bg-white text-slate-700"
            }`}
            onClick={() => onViewModeChange("current")}
          >
            Current
          </button>
          <button
            type="button"
            aria-pressed={viewMode === "recommended"}
            className={`px-3 py-1.5 text-sm font-medium ${
              viewMode === "recommended" ? "bg-slate-900 text-white" : "bg-white text-slate-700"
            }`}
            onClick={() => onViewModeChange("recommended")}
            disabled={state.type !== "ready"}
          >
            Recommended
          </button>
        </div>
      </div>

      {state.type === "loading" && (
        <p className="mt-3 text-sm text-slate-600">Loading recommendation...</p>
      )}

      {state.type === "error" && <p className="mt-3 text-sm text-red-700">{state.message}</p>}

      {state.type === "unavailable" && (
        <div className="mt-3 space-y-2">
          <p className="text-sm text-red-700">{state.message}</p>
          {missingPlayerNames.length > 0 && (
            <p className="text-sm text-red-700">
              Missing projections for: {missingPlayerNames.join(", ")}.
            </p>
          )}
          <button
            type="button"
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={onRefreshProjections}
            disabled={refreshing}
          >
            {refreshing ? "Refreshing xPts..." : "Refresh xPts"}
          </button>
        </div>
      )}

      {state.type === "ready" && (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold text-slate-900">
              GW {state.data.target_gameweek_number}
            </span>
            <ProjectionRunBadge
              modelVersion={state.data.model_version}
              generatedAt={state.data.generated_at}
              projectionRunId={state.data.projection_run_id}
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Starting XI xPts
              </p>
              <p className="mt-1 text-xl font-semibold text-slate-900">
                {state.data.starting_xi_points.toFixed(1)}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Captain-adjusted total
              </p>
              <p className="mt-1 text-xl font-semibold text-slate-900">
                {state.data.captain_adjusted_points.toFixed(1)}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Recommended XI vs current
              </p>
              <p className="mt-1 text-xl font-semibold text-slate-900">
                {formatSignedPoints(
                  state.data.captain_adjusted_points - state.data.current_captain_adjusted_points,
                )}{" "}
                xPts
              </p>
            </div>
          </div>

          <p className="text-sm text-slate-700">
            Recommended captain: <span className="font-medium">{captainName ?? "-"}</span> · Recommended
            vice-captain: <span className="font-medium">{viceCaptainName ?? "-"}</span>
          </p>
        </div>
      )}
    </section>
  );
}
