import { buildPlanBoardHref } from "@/lib/planner-explorer-url";

export function PlannerContextBanner({
  planId,
  planName,
  gameweek,
}: {
  planId: number;
  planName: string;
  gameweek: number;
}): JSX.Element {
  return (
    <section
      aria-label="Planner context"
      className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-950"
    >
      <span className="rounded-full bg-emerald-700 px-3 py-1 text-xs font-semibold text-white">
        Planner mode
      </span>
      <span className="font-medium">{planName}</span>
      <span>Gameweek {gameweek}</span>
      <a
        href={buildPlanBoardHref(planId, gameweek)}
        className="ml-auto font-medium underline"
      >
        Back to plan
      </a>
    </section>
  );
}
