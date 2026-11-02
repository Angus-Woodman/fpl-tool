import type {
  PlanExplorerCandidate,
  PlanExplorerFixture,
  PlanExplorerHorizonInfo,
  PlanExplorerHorizonKey,
} from "@/lib/api";

/**
 * Client-side presentation of the server's candidates: narrowing, ordering and fixture
 * grouping only. Nothing here derives legality, money, gains or fixtures; every figure
 * compared or shown is a value the server supplied.
 */

export type SortKey =
  "default" | "gain-1" | "gain-3" | "gain-5" | "price" | "bank" | "difficulty";
export type SortDirection = "asc" | "desc";

export type Filters = {
  search: string;
  club: string;
  /** What was typed, in £m; parsed to whole tenths only when used. */
  maxPrice: string;
  availableOnly: boolean;
  status: string;
};

export const NO_FILTERS: Filters = {
  search: "",
  club: "",
  maxPrice: "",
  availableOnly: false,
  status: "",
};

/** Gain, price and bank start with the most useful end first; difficulty starts easiest first. */
const DEFAULT_DIRECTION: Record<Exclude<SortKey, "default">, SortDirection> = {
  "gain-1": "desc",
  "gain-3": "desc",
  "gain-5": "desc",
  price: "asc",
  bank: "desc",
  difficulty: "asc",
};

export function defaultDirection(key: SortKey): SortDirection {
  return key === "default" ? "desc" : DEFAULT_DIRECTION[key];
}

export type MaxPrice =
  { kind: "none" } | { kind: "invalid" } | { kind: "ok"; tenths: number };

/** "6", "6.5" or "12.5" in £m to whole tenths, read from the digits so no float arithmetic is involved. */
export function parseMaxPrice(text: string): MaxPrice {
  const trimmed = text.trim();
  if (trimmed === "") return { kind: "none" };
  const match = /^(\d{1,3})(?:\.(\d))?$/.exec(trimmed);
  if (!match) return { kind: "invalid" };
  return { kind: "ok", tenths: Number(match[1]) * 10 + Number(match[2] ?? 0) };
}

export function filtersAreActive(filters: Filters): boolean {
  return (
    filters.search.trim() !== "" ||
    filters.club !== "" ||
    parseMaxPrice(filters.maxPrice).kind === "ok" ||
    filters.availableOnly ||
    filters.status !== ""
  );
}

export function filterCandidates(
  candidates: PlanExplorerCandidate[],
  filters: Filters,
): PlanExplorerCandidate[] {
  const needle = filters.search.trim().toLowerCase();
  const maxPrice = parseMaxPrice(filters.maxPrice);
  return candidates.filter(
    (candidate) =>
      (needle === "" || candidate.web_name.toLowerCase().includes(needle)) &&
      (filters.club === "" || candidate.team_short_name === filters.club) &&
      (maxPrice.kind !== "ok" || candidate.price_tenths <= maxPrice.tenths) &&
      // Strictly the server's verdict; playing status is advisory and never decides this.
      (!filters.availableOnly || candidate.state === "available") &&
      (filters.status === "" || candidate.status === filters.status),
  );
}

export function clubsIn(candidates: PlanExplorerCandidate[]): string[] {
  return [
    ...new Set(candidates.map((candidate) => candidate.team_short_name)),
  ].sort();
}

const STATUS_ORDER = ["a", "d", "i", "s", "u", "n"];

export function statusesIn(candidates: PlanExplorerCandidate[]): string[] {
  const rank = (code: string) => {
    const index = STATUS_ORDER.indexOf(code);
    return index === -1 ? STATUS_ORDER.length : index;
  };
  return [...new Set(candidates.map((candidate) => candidate.status))].sort(
    (left, right) => rank(left) - rank(right) || left.localeCompare(right),
  );
}

export type GameweekFixtures =
  | { gameweek: number; kind: "fixtures"; fixtures: PlanExplorerFixture[] }
  /** The server reported the gameweek with no opponent: a known blank. */
  | { gameweek: number; kind: "blank" }
  /** An evaluated gameweek for which the server returned nothing. */
  | { gameweek: number; kind: "missing" }
  /** Outside the evaluated gameweeks, so the server was not asked for it. */
  | { gameweek: number; kind: "not_evaluated" };

/** The gameweeks to show: the selected horizon's, which start at the selected gameweek. */
export function fixtureWindow(
  candidates: PlanExplorerCandidate[],
  info: PlanExplorerHorizonInfo | undefined,
): number[] {
  if (info) return info.requested_gameweeks;
  return [
    ...new Set(
      candidates.flatMap((candidate) =>
        candidate.fixtures.map((fixture) => fixture.gameweek),
      ),
    ),
  ].sort((left, right) => left - right);
}

export function groupFixtures(
  candidate: PlanExplorerCandidate,
  gameweeks: number[],
  info: PlanExplorerHorizonInfo | undefined,
): GameweekFixtures[] {
  const evaluated = info ? new Set(info.evaluated_gameweeks) : null;
  return gameweeks.map((gameweek): GameweekFixtures => {
    const entries = candidate.fixtures.filter(
      (fixture) => fixture.gameweek === gameweek,
    );
    const played = entries.filter(
      (fixture) => fixture.opponent_short_name !== null,
    );
    if (played.length > 0)
      return { gameweek, kind: "fixtures", fixtures: played };
    if (entries.length > 0) return { gameweek, kind: "blank" };
    return {
      gameweek,
      kind:
        evaluated === null || evaluated.has(gameweek)
          ? "missing"
          : "not_evaluated",
    };
  });
}

type Mean = { sum: number; count: number };

/**
 * Mean of the supplied difficulties over the shown fixtures. Each fixture of a double
 * gameweek counts; blank gameweeks, missing fixtures and missing values add nothing, and a
 * candidate with no difficulty at all has no mean.
 */
function meanDifficulty(groups: GameweekFixtures[]): Mean | null {
  let sum = 0;
  let count = 0;
  for (const group of groups) {
    if (group.kind !== "fixtures") continue;
    for (const fixture of group.fixtures) {
      if (fixture.difficulty !== null) {
        sum += fixture.difficulty;
        count += 1;
      }
    }
  }
  return count === 0 ? null : { sum, count };
}

type Ordering = (
  left: PlanExplorerCandidate,
  right: PlanExplorerCandidate,
) => number;

/** Smaller first; a missing value goes after every value in either direction. */
function byNumber(
  value: (candidate: PlanExplorerCandidate) => number | null,
  direction: SortDirection,
): Ordering {
  return (left, right) => {
    const a = value(left);
    const b = value(right);
    if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1;
    return direction === "asc" ? a - b : b - a;
  };
}

/** Compares sum/count means by cross-multiplication, so no rounding can reorder them. */
function byMean(
  mean: (candidate: PlanExplorerCandidate) => Mean | null,
  direction: SortDirection,
): Ordering {
  return (left, right) => {
    const a = mean(left);
    const b = mean(right);
    if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1;
    const difference = a.sum * b.count - b.sum * a.count;
    return direction === "asc" ? difference : -difference;
  };
}

/**
 * The server's order for "default"; otherwise a re-ordered copy. Ties always fall back to
 * ascending player id, whatever the direction, and the input is never mutated.
 */
export function sortCandidates(
  candidates: PlanExplorerCandidate[],
  key: SortKey,
  direction: SortDirection,
  fixtures: { gameweeks: number[]; info: PlanExplorerHorizonInfo | undefined },
): PlanExplorerCandidate[] {
  if (key === "default") return candidates;
  let primary: Ordering;
  if (key === "price") {
    primary = byNumber((candidate) => candidate.price_tenths, direction);
  } else if (key === "bank") {
    primary = byNumber(
      (candidate) => candidate.resulting_bank_tenths,
      direction,
    );
  } else if (key === "difficulty") {
    const means = new Map(
      candidates.map((candidate) => [
        candidate.player_id,
        meanDifficulty(
          groupFixtures(candidate, fixtures.gameweeks, fixtures.info),
        ),
      ]),
    );
    primary = byMean(
      (candidate) => means.get(candidate.player_id) ?? null,
      direction,
    );
  } else {
    const horizon = key.slice("gain-".length) as PlanExplorerHorizonKey;
    primary = byNumber(
      (candidate) => candidate.best_xi_gain_by_horizon[horizon] ?? null,
      direction,
    );
  }
  return [...candidates].sort(
    (left, right) => primary(left, right) || left.player_id - right.player_id,
  );
}
