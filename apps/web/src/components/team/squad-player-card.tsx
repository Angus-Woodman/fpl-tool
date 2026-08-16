import type { Position } from "@/components/team/types";

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
  children?: React.ReactNode;
};

const CHANGE_TAG_LABEL: Record<"promoted" | "dropped", string> = {
  promoted: "Now a starter",
  dropped: "Now on the bench",
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
  children,
}: SquadPlayerCardProps): JSX.Element {
  return (
    <article className="rounded-lg border border-slate-200 p-3">
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

      {children}
    </article>
  );
}
