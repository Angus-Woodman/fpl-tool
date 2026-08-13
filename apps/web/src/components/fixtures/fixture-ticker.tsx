"use client";

import { useEffect, useMemo, useState } from "react";

import {
  FixtureTickerItem,
  GameweekItem,
  TeamItem,
  fetchFixtureTicker,
  fetchGameweeks,
  fetchTeams,
  updateTeamDifficulty,
} from "@/lib/api";

const MIN_WINDOW_SIZE = 2;
const MAX_WINDOW_SIZE = 10;
const DEFAULT_WINDOW_SIZE = 6;
const FIXTURES_PER_GAMEWEEK_LIMIT = 20;
const DIFFICULTY_OPTIONS = [1, 2, 3, 4, 5];

type FixturesLoadState =
  | { type: "loading" }
  | { type: "error"; message: string }
  | { type: "loaded"; itemsByGameweek: Map<number, FixtureTickerItem[]> };

type SortMode = "alphabetical" | "hardest-first" | "easiest-first";

type TeamFixtureCell = {
  gameweekNumber: number;
  opponentShortName: string;
  isHome: boolean;
  difficulty: number;
};

const DIFFICULTY_STYLES: Record<number, string> = {
  1: "bg-emerald-600 text-white",
  2: "bg-emerald-300 text-emerald-950",
  3: "bg-slate-200 text-slate-700",
  4: "bg-rose-300 text-rose-950",
  5: "bg-rose-600 text-white",
};

function difficultyStyle(difficulty: number): string {
  return DIFFICULTY_STYLES[difficulty] ?? DIFFICULTY_STYLES[3];
}

function buildCells(
  team: TeamItem,
  visibleGameweeks: GameweekItem[],
  itemsByGameweek: Map<number, FixtureTickerItem[]>
): Map<number, TeamFixtureCell[]> {
  const cellsByGameweek = new Map<number, TeamFixtureCell[]>();

  for (const gameweek of visibleGameweeks) {
    const fixtures = itemsByGameweek.get(gameweek.number) ?? [];
    const cells: TeamFixtureCell[] = [];

    for (const fixture of fixtures) {
      if (fixture.home_team_short_name === team.short_name) {
        cells.push({
          gameweekNumber: gameweek.number,
          opponentShortName: fixture.away_team_short_name,
          isHome: true,
          difficulty: fixture.away_team_difficulty,
        });
      } else if (fixture.away_team_short_name === team.short_name) {
        cells.push({
          gameweekNumber: gameweek.number,
          opponentShortName: fixture.home_team_short_name,
          isHome: false,
          difficulty: fixture.home_team_difficulty,
        });
      }
    }

    cellsByGameweek.set(gameweek.number, cells);
  }

  return cellsByGameweek;
}

function sumDifficultyAcrossWindow(
  team: TeamItem,
  visibleGameweeks: GameweekItem[],
  itemsByGameweek: Map<number, FixtureTickerItem[]>
): number {
  let total = 0;

  for (const gameweek of visibleGameweeks) {
    const fixtures = itemsByGameweek.get(gameweek.number) ?? [];
    for (const fixture of fixtures) {
      if (fixture.home_team_short_name === team.short_name) {
        total += fixture.away_team_difficulty;
      } else if (fixture.away_team_short_name === team.short_name) {
        total += fixture.home_team_difficulty;
      }
    }
  }

  return total;
}

export function FixtureTicker(): JSX.Element {
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [gameweeks, setGameweeks] = useState<GameweekItem[]>([]);
  const [teamsError, setTeamsError] = useState<string | null>(null);
  const [gameweeksError, setGameweeksError] = useState<string | null>(null);
  const [windowStart, setWindowStart] = useState<number | undefined>(undefined);
  const [windowSize, setWindowSize] = useState(DEFAULT_WINDOW_SIZE);
  const [sortMode, setSortMode] = useState<SortMode>("alphabetical");
  const [fixturesState, setFixturesState] = useState<FixturesLoadState>({ type: "loading" });
  const [fixturesRefreshToken, setFixturesRefreshToken] = useState(0);
  const [updatingTeamId, setUpdatingTeamId] = useState<number | null>(null);
  const [updateError, setUpdateError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function run(): Promise<void> {
      try {
        const data = await fetchTeams();
        if (!cancelled) setTeams(data.items);
      } catch (error) {
        if (!cancelled) {
          setTeamsError(error instanceof Error ? error.message : "Failed to load teams");
        }
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function run(): Promise<void> {
      try {
        const data = await fetchGameweeks();
        if (cancelled) return;

        setGameweeks(data.items);

        const defaultNumber =
          data.items.find((gameweek) => gameweek.is_next)?.number ??
          data.items.find((gameweek) => gameweek.is_current)?.number ??
          data.items[0]?.number;

        if (defaultNumber !== undefined) {
          setWindowStart(defaultNumber);
        }
      } catch (error) {
        if (!cancelled) {
          setGameweeksError(error instanceof Error ? error.message : "Failed to load gameweeks");
        }
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  const maxGameweekNumber = useMemo(
    () => gameweeks.reduce((max, gameweek) => Math.max(max, gameweek.number), 0),
    [gameweeks]
  );
  const minGameweekNumber = useMemo(
    () => gameweeks.reduce((min, gameweek) => Math.min(min, gameweek.number), Infinity),
    [gameweeks]
  );

  const visibleGameweeks = useMemo(() => {
    if (windowStart === undefined) return [];

    return gameweeks
      .filter(
        (gameweek) =>
          gameweek.number >= windowStart && gameweek.number < windowStart + windowSize
      )
      .sort((a, b) => a.number - b.number);
  }, [gameweeks, windowStart, windowSize]);

  const visibleGameweekNumbers = visibleGameweeks.map((gameweek) => gameweek.number).join(",");

  useEffect(() => {
    if (visibleGameweeks.length === 0) return;

    let cancelled = false;

    async function run(): Promise<void> {
      setFixturesState({ type: "loading" });
      try {
        const responses = await Promise.all(
          visibleGameweeks.map((gameweek) =>
            fetchFixtureTicker({ gameweek: gameweek.number, limit: FIXTURES_PER_GAMEWEEK_LIMIT })
          )
        );
        if (cancelled) return;

        const itemsByGameweek = new Map<number, FixtureTickerItem[]>();
        visibleGameweeks.forEach((gameweek, index) => {
          itemsByGameweek.set(gameweek.number, responses[index].items);
        });

        setFixturesState({ type: "loaded", itemsByGameweek });
      } catch (error) {
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : "Failed to load fixture ticker";
          setFixturesState({ type: "error", message });
        }
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleGameweekNumbers, fixturesRefreshToken]);

  const canGoPrevious =
    windowStart !== undefined && Number.isFinite(minGameweekNumber) && windowStart > minGameweekNumber;
  const canGoNext = windowStart !== undefined && windowStart + windowSize - 1 < maxGameweekNumber;

  const visibleTeams = useMemo(() => {
    if (sortMode === "alphabetical" || fixturesState.type !== "loaded") {
      return [...teams].sort((a, b) => a.name.localeCompare(b.name));
    }

    const totalByTeamId = new Map<number, number>();
    for (const team of teams) {
      totalByTeamId.set(
        team.id,
        sumDifficultyAcrossWindow(team, visibleGameweeks, fixturesState.itemsByGameweek)
      );
    }

    return [...teams].sort((a, b) => {
      const totalA = totalByTeamId.get(a.id) ?? Infinity;
      const totalB = totalByTeamId.get(b.id) ?? Infinity;
      if (totalA === totalB) {
        return a.name.localeCompare(b.name);
      }
      return sortMode === "easiest-first" ? totalA - totalB : totalB - totalA;
    });
  }, [teams, sortMode, fixturesState, visibleGameweeks]);

  async function handleDifficultyChange(team: TeamItem, newDifficulty: number): Promise<void> {
    setUpdateError(null);
    setUpdatingTeamId(team.id);
    try {
      const updated = await updateTeamDifficulty(team.id, newDifficulty);
      setTeams((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      // Fixture cells embed each opponent's difficulty at fetch time, so refetch to reflect the change.
      setFixturesRefreshToken((value) => value + 1);
    } catch (error) {
      setUpdateError(error instanceof Error ? error.message : "Failed to update difficulty");
    } finally {
      setUpdatingTeamId(null);
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Fixture Ticker</h2>
          <p className="mt-1 text-xs text-slate-600">
            Every team&apos;s next fixtures, colour-coded by opponent difficulty.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-600">
            Sort by
            <select
              aria-label="Sort teams"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900"
              value={sortMode}
              onChange={(event) => setSortMode(event.target.value as SortMode)}
            >
              <option value="alphabetical">A-Z</option>
              <option value="hardest-first">Hardest to easiest</option>
              <option value="easiest-first">Easiest to hardest</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-600">
            Window
            <input
              aria-label="Gameweek window size"
              type="range"
              min={MIN_WINDOW_SIZE}
              max={MAX_WINDOW_SIZE}
              value={windowSize}
              onChange={(event) => setWindowSize(Number(event.target.value))}
            />
            <span className="w-16 font-medium text-slate-900">{windowSize} GWs</span>
          </label>
          <button
            type="button"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-40"
            aria-label="Previous gameweeks"
            disabled={!canGoPrevious}
            onClick={() => setWindowStart((value) => (value === undefined ? value : value - 1))}
          >
            &lsaquo; Prev
          </button>
          <button
            type="button"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-40"
            aria-label="Next gameweeks"
            disabled={!canGoNext}
            onClick={() => setWindowStart((value) => (value === undefined ? value : value + 1))}
          >
            Next &rsaquo;
          </button>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-slate-600">
        <span className="font-medium">Difficulty:</span>
        {DIFFICULTY_OPTIONS.map((difficulty) => (
          <span
            key={difficulty}
            className={`rounded px-2 py-0.5 font-semibold ${difficultyStyle(difficulty)}`}
          >
            {difficulty}
          </span>
        ))}
        <span className="text-slate-500">
          (1 = easiest, 5 = hardest &mdash; edit a team&apos;s rating in the Team column. Sorting by
          difficulty totals the ratings across every fixture in the visible gameweek window.)
        </span>
      </div>

      {teamsError && <p className="mb-3 text-sm text-amber-700">{teamsError}</p>}
      {gameweeksError && <p className="mb-3 text-sm text-amber-700">{gameweeksError}</p>}
      {updateError && <p className="mb-3 text-sm text-red-700">{updateError}</p>}
      {fixturesState.type === "error" && (
        <p className="mb-3 text-sm text-red-700">{fixturesState.message}</p>
      )}

      {visibleGameweeks.length === 0 ? (
        <p className="text-sm text-slate-600">No upcoming gameweeks found.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-slate-600">
                <th className="sticky left-0 bg-slate-50 px-3 py-2 font-medium">Team</th>
                {visibleGameweeks.map((gameweek) => (
                  <th key={gameweek.id} className="px-2 py-2 text-center font-medium">
                    GW{gameweek.number}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleTeams.map((team) => {
                const cellsByGameweek =
                  fixturesState.type === "loaded"
                    ? buildCells(team, visibleGameweeks, fixturesState.itemsByGameweek)
                    : undefined;

                return (
                  <tr key={team.id} className="border-b border-slate-100">
                    <td className="sticky left-0 bg-white px-3 py-2 font-medium text-slate-900">
                      <div className="flex items-center gap-2">
                        <span>{team.short_name}</span>
                        <select
                          aria-label={`${team.short_name} difficulty`}
                          className={`rounded px-1 py-0.5 text-xs font-semibold disabled:opacity-50 ${difficultyStyle(
                            team.difficulty
                          )}`}
                          value={team.difficulty}
                          disabled={updatingTeamId === team.id}
                          onChange={(event) =>
                            void handleDifficultyChange(team, Number(event.target.value))
                          }
                        >
                          {DIFFICULTY_OPTIONS.map((difficulty) => (
                            <option key={difficulty} value={difficulty}>
                              {difficulty}
                            </option>
                          ))}
                        </select>
                      </div>
                    </td>
                    {visibleGameweeks.map((gameweek) => {
                      if (!cellsByGameweek) {
                        return (
                          <td key={gameweek.id} className="px-2 py-2 text-center text-slate-400">
                            …
                          </td>
                        );
                      }

                      const cells = cellsByGameweek.get(gameweek.number) ?? [];

                      if (cells.length === 0) {
                        return (
                          <td key={gameweek.id} className="px-2 py-2 text-center text-slate-300">
                            -
                          </td>
                        );
                      }

                      return (
                        <td key={gameweek.id} className="px-1 py-1 text-center">
                          <div className="flex flex-col items-center gap-1">
                            {cells.map((cell, index) => (
                              <span
                                key={`${cell.gameweekNumber}-${index}`}
                                className={`w-full rounded px-2 py-1 text-xs font-semibold ${difficultyStyle(
                                  cell.difficulty
                                )}`}
                              >
                                {cell.opponentShortName} ({cell.isHome ? "H" : "A"})
                              </span>
                            ))}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
              {visibleTeams.length === 0 && (
                <tr>
                  <td
                    colSpan={visibleGameweeks.length + 1}
                    className="px-3 py-4 text-center text-sm text-slate-600"
                  >
                    No teams found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
