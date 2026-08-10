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
  | { type: "loaded"; items: FixtureTickerItem[]; total: number };

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
  const [teamsError, setTeamsError] = useState<string | null>(null);
  const [gameweeksError, setGameweeksError] = useState<string | null>(null);

  const [appliedLimit, setAppliedLimit] = useState(20);
  const [appliedTeamId, setAppliedTeamId] = useState<number | undefined>(undefined);
  const [appliedGameweek, setAppliedGameweek] = useState<number | undefined>(undefined);

  const [state, setState] = useState<LoadState>({ type: "loading" });

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
      } catch (error) {
        if (cancelled) {
          return;
        }

        const message = error instanceof Error ? error.message : "Failed to load gameweeks";
        setGameweeksError(message);
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
      setState({ type: "loading" });
      try {
        const data = await fetchFixtureTicker({
          limit: appliedLimit,
          team_id: appliedTeamId,
          gameweek: appliedGameweek,
        });
        if (cancelled) {
          return;
        }

        setState({ type: "loaded", items: data.items, total: data.total });
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
  }, [appliedGameweek, appliedLimit, appliedTeamId]);

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

            const parsedTeamId = Number.parseInt(selectedTeamId, 10);
            setAppliedTeamId(Number.isNaN(parsedTeamId) ? undefined : parsedTeamId);

            const parsedGameweek = Number.parseInt(selectedGameweek, 10);
            setAppliedGameweek(Number.isNaN(parsedGameweek) ? undefined : parsedGameweek);
          }}
        >
          Apply filters
        </button>
      </div>
      {(appliedLimit !== 20 || appliedTeamId !== undefined || appliedGameweek !== undefined) && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {appliedLimit !== 20 && (
            <button
              type="button"
              className="rounded-full border border-slate-300 bg-slate-50 px-3 py-1 text-xs"
              onClick={() => {
                setLimit("20");
                setAppliedLimit(20);
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
              }}
            >
              Team: {teams.find((team) => team.id === appliedTeamId)?.short_name ?? appliedTeamId} x
            </button>
          )}
          {appliedGameweek !== undefined && (
            <button
              type="button"
              className="rounded-full border border-slate-300 bg-slate-50 px-3 py-1 text-xs"
              onClick={() => {
                setSelectedGameweek("");
                setAppliedGameweek(undefined);
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
              setSelectedGameweek("");
              setAppliedLimit(20);
              setAppliedTeamId(undefined);
              setAppliedGameweek(undefined);
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
          <p className="mt-3 text-xs text-slate-600">Showing {state.total} fixtures</p>
        </div>
      )}
    </section>
  );
}
