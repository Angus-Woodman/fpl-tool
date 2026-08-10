"use client";

import { useEffect, useState } from "react";

import { FixtureTickerItem, fetchFixtureTicker } from "@/lib/api";

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
  const [teamIdInput, setTeamIdInput] = useState("");
  const [gameweekInput, setGameweekInput] = useState("");

  const [appliedLimit, setAppliedLimit] = useState(20);
  const [appliedTeamId, setAppliedTeamId] = useState<number | undefined>(undefined);
  const [appliedGameweek, setAppliedGameweek] = useState<number | undefined>(undefined);

  const [state, setState] = useState<LoadState>({ type: "loading" });

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
        <input
          aria-label="Filter by team id"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          value={teamIdInput}
          onChange={(event) => setTeamIdInput(event.target.value)}
          placeholder="Team ID"
        />
        <input
          aria-label="Filter by gameweek"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          value={gameweekInput}
          onChange={(event) => setGameweekInput(event.target.value)}
          placeholder="Gameweek (1-38)"
        />
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

            const parsedTeamId = Number.parseInt(teamIdInput, 10);
            setAppliedTeamId(Number.isNaN(parsedTeamId) ? undefined : parsedTeamId);

            const parsedGameweek = Number.parseInt(gameweekInput, 10);
            if (Number.isNaN(parsedGameweek)) {
              setAppliedGameweek(undefined);
            } else {
              setAppliedGameweek(Math.min(38, Math.max(1, parsedGameweek)));
            }
          }}
        >
          Apply filters
        </button>
      </div>
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
