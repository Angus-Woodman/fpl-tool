import type { PlanExplorerHorizonInfo } from "@/lib/api";

/** Integer tenths of a million to £m for display only; never used to compute. */
export function formatTenths(tenths: number | null): string {
  if (tenths === null) {
    return "-";
  }
  const magnitude = Math.abs(tenths);
  return `${tenths < 0 ? "-" : ""}£${Math.trunc(magnitude / 10)}.${magnitude % 10}m`;
}

export function formatSignedPoints(value: number | null): string {
  if (value === null) {
    return "-";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

/** "GW9", "GW9-11" or "GW9-11, GW13" from a list of gameweek numbers. */
export function formatGameweekRanges(gameweeks: number[]): string {
  const sorted = [...new Set(gameweeks)].sort((left, right) => left - right);
  const ranges: string[] = [];
  let index = 0;
  while (index < sorted.length) {
    let end = index;
    while (end + 1 < sorted.length && sorted[end + 1] === sorted[end] + 1) {
      end += 1;
    }
    ranges.push(
      end === index
        ? `GW${sorted[index]}`
        : `GW${sorted[index]}-${sorted[end]}`,
    );
    index = end + 1;
  }
  return ranges.join(", ");
}

export function missingGameweeks(info: PlanExplorerHorizonInfo): number[] {
  const evaluated = new Set(info.evaluated_gameweeks);
  return info.requested_gameweeks.filter(
    (gameweek) => !evaluated.has(gameweek),
  );
}

export function horizonLabel(info: PlanExplorerHorizonInfo): string {
  return info.evaluated_gameweeks.length === 0
    ? "no gameweeks"
    : formatGameweekRanges(info.evaluated_gameweeks);
}
