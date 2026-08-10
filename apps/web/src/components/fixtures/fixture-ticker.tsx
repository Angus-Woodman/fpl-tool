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
  const [state, setState] = useState<LoadState>({ type: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function run(): Promise<void> {
      setState({ type: "loading" });
      try {
        const data = await fetchFixtureTicker(20);
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
  }, []);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 text-xl font-semibold">Upcoming Fixtures</h2>
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
