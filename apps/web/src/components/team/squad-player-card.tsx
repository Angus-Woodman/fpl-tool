import type { Position } from "@/components/team/types";

export type SelectionState = "idle" | "selected" | "target" | "not-target";

export type SquadPlayerCardProps = {
  webName: string;
  teamShortName: string;
  position: Position;
  projectedPoints: number | null;
  opponentLabel?: string;
  badge?: "C" | "VC" | null;
  benchOrder?: number | null;
  changeTag?: "promoted" | "dropped" | null;
  transferHref?: string;
  /** When `onSelect` is provided the card renders a select control reflecting this state. */
  selectionState?: SelectionState;
  onSelect?: () => void;
  selectionDisabled?: boolean;
  children?: React.ReactNode;
};

const CHANGE_TAG_LABEL: Record<"promoted" | "dropped", string> = {
  promoted: "Now a starter",
  dropped: "Now on the bench",
};

const SELECTION_CARD_CLASSES: Record<SelectionState, string> = {
  idle: "border-slate-200",
  selected: "border-emerald-600 ring-2 ring-emerald-500 bg-emerald-50",
  target: "border-sky-500 ring-2 ring-sky-300 bg-sky-50",
  "not-target": "border-slate-200 opacity-60",
};

export function SquadPlayerCard({
  webName,
  teamShortName,
  position,
  projectedPoints,
  opponentLabel,
  badge,
  benchOrder,
  changeTag,
  transferHref,
  selectionState = "idle",
  onSelect,
  selectionDisabled = false,
  children,
}: SquadPlayerCardProps): JSX.Element {
  const selectable = onSelect !== undefined;

  return (
    <article
      className={`rounded-lg border p-3 ${selectable ? SELECTION_CARD_CLASSES[selectionState] : "border-slate-200"}`}
      data-selection-state={selectable ? selectionState : undefined}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-900">{webName}</p>
          <p className="text-xs text-slate-600">
            {teamShortName} · {position}
            {benchOrder != null ? ` · Bench ${benchOrder}` : ""}
          </p>
        </div>
        {badge && (
          <span className="rounded-full bg-slate-900 px-2 py-1 text-[10px] font-semibold text-white">
            {badge}
          </span>
        )}
      </div>

      {changeTag && (
        <p className="mt-2 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800">
          {CHANGE_TAG_LABEL[changeTag]}
        </p>
      )}

      {opponentLabel !== undefined && (
        <p className="mt-2 text-xs text-slate-600">Opponent: {opponentLabel}</p>
      )}
      <p className="mt-1 text-xs text-slate-600">
        GW xPts: {projectedPoints !== null ? projectedPoints.toFixed(1) : "-"}
      </p>

      {transferHref && (
        <a href={transferHref} className="mt-2 inline-block text-xs text-slate-700 underline">
          Explore transfers &rarr;
        </a>
      )}

      {selectable && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            aria-label={`Select ${webName}`}
            aria-pressed={selectionState === "selected"}
            disabled={selectionDisabled}
            onClick={onSelect}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          >
            {selectionState === "selected" ? "Selected" : "Select"}
          </button>
          {selectionState === "target" && (
            <span className="text-xs font-medium text-sky-800">Valid swap target</span>
          )}
        </div>
      )}

      {children}
    </article>
  );
}
