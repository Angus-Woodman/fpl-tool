"use client";

import { useEffect, useState } from "react";

import {
  FixtureTickerItem,
  GameweekItem,
  TeamItem,
  fetchFixtureTicker,
  fetchGameweeks,
  fetchTeams,
} from "@/lib/api";

type LoadState =
  | { type: "loading" }
  | { type: "error"; message: string }
  | {
      type: "loaded";
      items: FixtureTickerItem[];
      total: number;
      page: number;
      pageSize: number;
    };

function formatKickoff(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date);
}

export function FixtureTicker(): JSX.Element {
  const [limit, setLimit] = useState("20");
  const [selectedTeamId, setSelectedTeamId] = useState("");
  const [selectedGameweek, setSelectedGameweek] = useState("");
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [gameweeks, setGameweeks] = useState<GameweekItem[]>([]);
  const [gameweeksLoaded, setGameweeksLoaded] = useState(false);
  const [teamsError, setTeamsError] = useState<string | null>(null);
  const [gameweeksError, setGameweeksError] = useState<string | null>(null);

  const [appliedLimit, setAppliedLimit] = useState(20);
  const [appliedPage, setAppliedPage] = useState(1);
  const [appliedTeamId, setAppliedTeamId] = useState<number | undefined>(undefined);
  const [appliedGameweek, setAppliedGameweek] = useState<number | undefined>(undefined);

  const [state, setState] = useState<LoadState>({ type: "loading" });

  const defaultGameweek =
    gameweeks.find((gameweek) => gameweek.is_next)?.number ??
    gameweeks.find((gameweek) => gameweek.is_current)?.number;
  const hasAppliedGameweekFilter =
    appliedGameweek !== undefined && appliedGameweek !== defaultGameweek;

  useEffect(() => {
    let cancelled = false;

    async function run(): Promise<void> {
      try {
        const data = await fetchTeams();
        if (cancelled) {
          return;
        }

        setTeams(data.items);
      } catch (error) {
        if (cancelled) {
          return;
        }

        const message = error instanceof Error ? error.message : "Failed to load teams";
        setTeamsError(message);
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
        if (cancelled) {
          return;
        }

        setGameweeks(data.items);

        const defaultNumber =
          data.items.find((gameweek) => gameweek.is_next)?.number ??
          data.items.find((gameweek) => gameweek.is_current)?.number;

        if (defaultNumber !== undefined) {
          setSelectedGameweek(String(defaultNumber));
          setAppliedGameweek(defaultNumber);
        }
      } catch (error) {
        if (cancelled) {
          return;
        }

        const message = error instanceof Error ? error.message : "Failed to load gameweeks";
        setGameweeksError(message);
      } finally {
        if (!cancelled) {
          setGameweeksLoaded(true);
        }
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!gameweeksLoaded) {
      return;
    }

    let cancelled = false;

    async function run(): Promise<void> {
      setState({ type: "loading" });
      try {
        const data = await fetchFixtureTicker({
          page: appliedPage,
          limit: appliedLimit,
          team_id: appliedTeamId,
          gameweek: appliedGameweek,
        });
        if (cancelled) {
          return;
        }

        setState({
          type: "loaded",
          items: data.items,
          total: data.total,
          page: data.page,
          pageSize: data.page_size,
        });
      } catch (error) {
        if (cancelled) {
          return;
        }

        const message =
          error instanceof Error ? error.message : "Failed to load fixture ticker";
        setState({ type: "error", message });
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, [appliedGameweek, appliedLimit, appliedPage, appliedTeamId, gameweeksLoaded]);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 text-xl font-semibold">Upcoming Fixtures</h2>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <input
          aria-label="Fixture limit"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          value={limit}
          onChange={(event) => setLimit(event.target.value)}
          placeholder="Limit (1-100)"
        />
        <select
          aria-label="Filter by team"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          value={selectedTeamId}
          onChange={(event) => setSelectedTeamId(event.target.value)}
        >
          <option value="">All teams</option>
          {teams.map((team) => (
            <option key={team.id} value={String(team.id)}>
              {team.name} ({team.short_name})
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by gameweek"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          value={selectedGameweek}
          onChange={(event) => setSelectedGameweek(event.target.value)}
        >
          <option value="">All gameweeks</option>
          {gameweeks.map((gameweek) => (
            <option key={gameweek.id} value={String(gameweek.number)}>
              GW {gameweek.number}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50"
          onClick={() => {
            const parsedLimit = Number.parseInt(limit, 10);
            if (Number.isNaN(parsedLimit)) {
              setAppliedLimit(20);
            } else {
              setAppliedLimit(Math.min(100, Math.max(1, parsedLimit)));
            }
            setAppliedPage(1);

            const parsedTeamId = Number.parseInt(selectedTeamId, 10);
            setAppliedTeamId(Number.isNaN(parsedTeamId) ? undefined : parsedTeamId);

            const parsedGameweek = Number.parseInt(selectedGameweek, 10);
            setAppliedGameweek(Number.isNaN(parsedGameweek) ? undefined : parsedGameweek);
          }}
        >
          Apply filters
        </button>
      </div>
      {defaultGameweek !== undefined && appliedGameweek !== defaultGameweek && (
        <div className="mb-3">
          <button
            type="button"
            className="rounded-md border border-slate-300 bg-slate-50 px-3 py-1 text-xs hover:bg-slate-100"
            onClick={() => {
              setSelectedGameweek(String(defaultGameweek));
              setAppliedGameweek(defaultGameweek);
              setAppliedPage(1);
            }}
          >
            Reset to next GW
          </button>
        </div>
      )}
      {(appliedLimit !== 20 || appliedTeamId !== undefined || hasAppliedGameweekFilter) && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {appliedLimit !== 20 && (
            <button
              type="button"
              className="rounded-full border border-slate-300 bg-slate-50 px-3 py-1 text-xs"
              onClick={() => {
                setLimit("20");
                setAppliedLimit(20);
                setAppliedPage(1);
              }}
            >
              Limit: {appliedLimit} x
            </button>
          )}
          {appliedTeamId !== undefined && (
            <button
              type="button"
              className="rounded-full border border-slate-300 bg-slate-50 px-3 py-1 text-xs"
              onClick={() => {
                setSelectedTeamId("");
                setAppliedTeamId(undefined);
                setAppliedPage(1);
              }}
            >
              Team: {teams.find((team) => team.id === appliedTeamId)?.short_name ?? appliedTeamId} x
            </button>
          )}
          {hasAppliedGameweekFilter && (
            <button
              type="button"
              className="rounded-full border border-slate-300 bg-slate-50 px-3 py-1 text-xs"
              onClick={() => {
                setSelectedGameweek("");
                setAppliedGameweek(undefined);
                setAppliedPage(1);
              }}
            >
              GW: {appliedGameweek} x
            </button>
          )}
          <button
            type="button"
            className="rounded-full border border-slate-300 px-3 py-1 text-xs hover:bg-slate-50"
            onClick={() => {
              setLimit("20");
              setSelectedTeamId("");
              setSelectedGameweek(defaultGameweek !== undefined ? String(defaultGameweek) : "");
              setAppliedLimit(20);
              setAppliedTeamId(undefined);
              setAppliedGameweek(defaultGameweek);
              setAppliedPage(1);
            }}
          >
            Clear all
          </button>
        </div>
      )}
      {teamsError && <p className="mb-3 text-sm text-amber-700">{teamsError}</p>}
      {gameweeksError && <p className="mb-3 text-sm text-amber-700">{gameweeksError}</p>}
      {state.type === "loading" && <p className="text-sm text-slate-600">Loading fixtures...</p>}
      {state.type === "error" && <p className="text-sm text-red-700">{state.message}</p>}
      {state.type === "loaded" && state.items.length === 0 && (
        <p className="text-sm text-slate-600">No upcoming fixtures found.</p>
      )}
      {state.type === "loaded" && state.items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-slate-600">
                <th className="px-3 py-2 font-medium">GW</th>
                <th className="px-3 py-2 font-medium">Fixture</th>
                <th className="px-3 py-2 font-medium">Kickoff (UTC)</th>
              </tr>
            </thead>
            <tbody>
              {state.items.map((item) => (
                <tr key={item.fixture_id} className="border-b border-slate-100">
                  <td className="px-3 py-2 text-slate-700">{item.gameweek_number ?? "-"}</td>
                  <td className="px-3 py-2 font-medium text-slate-900">
                    {item.home_team_short_name} vs {item.away_team_short_name}
                  </td>
                  <td className="px-3 py-2 text-slate-700">{formatKickoff(item.kickoff_time)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-slate-600">
            Showing {state.items.length} of {state.total} fixtures
          </p>
          <div className="mt-3 flex items-center justify-between">
            <p className="text-xs text-slate-600">
              Page {state.page} of {Math.max(1, Math.ceil(state.total / state.pageSize))}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                className="rounded-md border border-slate-300 px-3 py-1 text-xs disabled:opacity-40"
                disabled={state.page <= 1}
                onClick={() => setAppliedPage((value) => Math.max(1, value - 1))}
              >
                Previous
              </button>
              <button
                type="button"
                className="rounded-md border border-slate-300 px-3 py-1 text-xs disabled:opacity-40"
                disabled={state.page >= Math.max(1, Math.ceil(state.total / state.pageSize))}
                onClick={() => setAppliedPage((value) => value + 1)}
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
