"use client";

import { useEffect, useState } from "react";

import { MyTeamPlayerItem, MyTeamResponse, fetchMyTeam } from "@/lib/api";

type LoadState =
  | { type: "loading" }
  | { type: "error"; message: string }
  | { type: "empty" }
  | { type: "loaded"; team: MyTeamResponse };

function badgeLabel(player: MyTeamPlayerItem): string | null {
  if (player.is_captain) {
    return "C";
  }
  if (player.is_vice_captain) {
    return "VC";
  }
  return null;
}

export function MyTeamBoard(): JSX.Element {
  const [state, setState] = useState<LoadState>({ type: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function run(): Promise<void> {
      setState({ type: "loading" });
      try {
        const data = await fetchMyTeam();
        if (cancelled) {
          return;
        }

        if (data === null) {
          setState({ type: "empty" });
          return;
        }

        setState({ type: "loaded", team: data });
      } catch (error) {
        if (cancelled) {
          return;
        }

        const message = error instanceof Error ? error.message : "Failed to load my team";
        setState({ type: "error", message });
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, []);

  if (state.type === "loading") {
    return <p className="text-sm text-slate-600">Loading my team...</p>;
  }

  if (state.type === "error") {
    return <p className="text-sm text-red-700">{state.message}</p>;
  }

  if (state.type === "empty") {
    return (
      <section className="rounded-xl border border-dashed border-slate-300 bg-white p-5 shadow-sm">
        <h2 className="text-xl font-semibold">No Squad Saved Yet</h2>
        <p className="mt-2 text-sm text-slate-700">
          The persisted squad API is in place, but no squad has been saved yet. For now, save one
          through the API and this page will render the starting XI and bench.
        </p>
      </section>
    );
  }

  const starters = state.team.players.filter((player) => player.is_starting);
  const bench = [...state.team.players]
    .filter((player) => !player.is_starting)
    .sort((left, right) => (left.bench_order ?? 99) - (right.bench_order ?? 99));

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">{state.team.name}</h2>
          <p className="mt-1 text-sm text-slate-600">A persisted snapshot of the current squad state.</p>
        </div>
        <div className="flex gap-3 text-sm text-slate-700">
          <span className="rounded-md bg-slate-100 px-3 py-2">Bank: {state.team.bank.toFixed(1)}</span>
          <span className="rounded-md bg-slate-100 px-3 py-2">
            Free Transfers: {state.team.free_transfers}
          </span>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Starting XI
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {starters.map((player) => {
              const badge = badgeLabel(player);
              return (
                <article key={player.player_id} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{player.web_name}</p>
                      <p className="text-xs text-slate-600">
                        {player.team_short_name} · {player.position}
                      </p>
                    </div>
                    {badge && (
                      <span className="rounded-full bg-slate-900 px-2 py-1 text-[10px] font-semibold text-white">
                        {badge}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-xs text-slate-600">Price: {player.current_price.toFixed(1)}</p>
                </article>
              );
            })}
          </div>
        </div>

        <div>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Bench</h3>
          <div className="space-y-3">
            {bench.map((player) => {
              const badge = badgeLabel(player);
              return (
                <article key={player.player_id} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{player.web_name}</p>
                      <p className="text-xs text-slate-600">
                        Bench {player.bench_order} · {player.team_short_name} · {player.position}
                      </p>
                    </div>
                    {badge && (
                      <span className="rounded-full bg-slate-900 px-2 py-1 text-[10px] font-semibold text-white">
                        {badge}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-xs text-slate-600">Price: {player.current_price.toFixed(1)}</p>
                </article>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}