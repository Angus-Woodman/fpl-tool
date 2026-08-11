"use client";

import { useEffect, useState } from "react";

import {
  MyTeamPlayerItem,
  MyTeamResponse,
  PlayerItem,
  SaveMyTeamRequest,
  fetchMyTeam,
  fetchPlayers,
  saveMyTeam,
} from "@/lib/api";

type LoadState =
  | { type: "loading" }
  | { type: "error"; message: string }
  | { type: "empty" }
  | { type: "loaded"; team: MyTeamResponse };

type CreateStarterSquadState =
  | { type: "idle" }
  | { type: "saving" }
  | { type: "error"; message: string };

const POSITION_COUNTS = {
  GK: 2,
  DEF: 5,
  MID: 5,
  FWD: 3,
} as const;

function choosePlayers(pool: PlayerItem[], count: number, selected: PlayerItem[]): PlayerItem[] {
  const teamCounts = new Map<number, number>();
  for (const player of selected) {
    teamCounts.set(player.id, 0);
  }

  const byTeamShortName = new Map<string, number>();
  for (const player of selected) {
    byTeamShortName.set(player.team_short_name, (byTeamShortName.get(player.team_short_name) ?? 0) + 1);
  }

  const chosen: PlayerItem[] = [];
  for (const player of pool) {
    const existingCount = byTeamShortName.get(player.team_short_name) ?? 0;
    if (existingCount >= 3) {
      continue;
    }

    chosen.push(player);
    byTeamShortName.set(player.team_short_name, existingCount + 1);
    if (chosen.length === count) {
      return chosen;
    }
  }

  throw new Error(`Unable to choose ${count} valid ${pool[0]?.position ?? "player"} options`);
}

function buildStarterSquad(playersByPosition: Record<"GK" | "DEF" | "MID" | "FWD", PlayerItem[]>): SaveMyTeamRequest {
  const pickedGoalkeepers = choosePlayers(playersByPosition.GK, POSITION_COUNTS.GK, []);
  const pickedDefenders = choosePlayers(playersByPosition.DEF, POSITION_COUNTS.DEF, pickedGoalkeepers);
  const pickedMidfielders = choosePlayers(
    playersByPosition.MID,
    POSITION_COUNTS.MID,
    [...pickedGoalkeepers, ...pickedDefenders]
  );
  const pickedForwards = choosePlayers(
    playersByPosition.FWD,
    POSITION_COUNTS.FWD,
    [...pickedGoalkeepers, ...pickedDefenders, ...pickedMidfielders]
  );

  const allPlayers = [
    ...pickedGoalkeepers,
    ...pickedDefenders,
    ...pickedMidfielders,
    ...pickedForwards,
  ];
  const starters = new Set<number>([
    pickedGoalkeepers[0].id,
    pickedDefenders[0].id,
    pickedDefenders[1].id,
    pickedDefenders[2].id,
    pickedMidfielders[0].id,
    pickedMidfielders[1].id,
    pickedMidfielders[2].id,
    pickedMidfielders[3].id,
    pickedForwards[0].id,
    pickedForwards[1].id,
    pickedForwards[2].id,
  ]);

  const bench = [pickedGoalkeepers[1], pickedDefenders[3], pickedMidfielders[4], pickedDefenders[4]];
  const captain = [...pickedMidfielders.slice(0, 4), ...pickedForwards].sort(
    (left, right) => right.current_price - left.current_price
  )[0];
  const viceCaptain = [...pickedMidfielders.slice(0, 4), ...pickedForwards]
    .filter((player) => player.id !== captain.id)
    .sort((left, right) => right.current_price - left.current_price)[0];

  return {
    bank: 0,
    free_transfers: 1,
    players: allPlayers.map((player) => ({
      player_id: player.id,
      is_starting: starters.has(player.id),
      bench_order: bench.findIndex((benchPlayer) => benchPlayer.id === player.id) + 1 || null,
      is_captain: player.id === captain.id,
      is_vice_captain: player.id === viceCaptain.id,
    })),
  };
}

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
  const [createState, setCreateState] = useState<CreateStarterSquadState>({ type: "idle" });

  async function loadMyTeam(): Promise<void> {
    setState({ type: "loading" });
    try {
      const data = await fetchMyTeam();

      if (data === null) {
        setState({ type: "empty" });
        return;
      }

      setState({ type: "loaded", team: data });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load my team";
      setState({ type: "error", message });
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function run(): Promise<void> {
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

  async function handleCreateStarterSquad(): Promise<void> {
    setCreateState({ type: "saving" });
    try {
      const [gk, def, mid, fwd] = await Promise.all([
        fetchPlayers({ position: "GK", status: "a", sort: "price_asc", page_size: 50 }),
        fetchPlayers({ position: "DEF", status: "a", sort: "price_asc", page_size: 80 }),
        fetchPlayers({ position: "MID", status: "a", sort: "price_asc", page_size: 80 }),
        fetchPlayers({ position: "FWD", status: "a", sort: "price_asc", page_size: 50 }),
      ]);

      const payload = buildStarterSquad({
        GK: gk.items,
        DEF: def.items,
        MID: mid.items,
        FWD: fwd.items,
      });

      await saveMyTeam(payload);
      setCreateState({ type: "idle" });
      await loadMyTeam();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to create starter squad";
      setCreateState({ type: "error", message });
    }
  }

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
          Create a starter squad from the currently imported player pool and this page will render
          the starting XI, bench, and projected totals.
        </p>
        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            className="rounded-md border border-slate-300 bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            onClick={() => void handleCreateStarterSquad()}
            disabled={createState.type === "saving"}
          >
            {createState.type === "saving" ? "Creating Starter Squad..." : "Create Starter Squad"}
          </button>
          {createState.type === "error" && (
            <p className="text-sm text-red-700">{createState.message}</p>
          )}
        </div>
      </section>
    );
  }

  const starters = state.team.players.filter((player) => player.is_starting);
  const bench = [...state.team.players]
    .filter((player) => !player.is_starting)
    .sort((left, right) => (left.bench_order ?? 99) - (right.bench_order ?? 99));

  const projectionCards = [
    {
      label: "1 GW xPts",
      value: state.team.captain_adjusted_projection_totals?.horizon_1,
    },
    {
      label: "3 GW xPts",
      value: state.team.captain_adjusted_projection_totals?.horizon_3,
    },
    {
      label: "5 GW xPts",
      value: state.team.captain_adjusted_projection_totals?.horizon_5,
    },
  ];

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

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        {projectionCards.map((card) => (
          <article key={card.label} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {card.label}
            </p>
            <p className="mt-2 text-2xl font-semibold text-slate-900">
              {card.value?.toFixed(1) ?? "-"}
            </p>
          </article>
        ))}
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
                  {player.projection_totals && (
                    <p className="mt-2 text-xs text-slate-600">
                      xPts 1/3/5: {player.projection_totals.horizon_1.toFixed(1)} / {player.projection_totals.horizon_3.toFixed(1)} / {player.projection_totals.horizon_5.toFixed(1)}
                    </p>
                  )}
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
                  {player.projection_totals && (
                    <p className="mt-2 text-xs text-slate-600">
                      xPts 1/3/5: {player.projection_totals.horizon_1.toFixed(1)} / {player.projection_totals.horizon_3.toFixed(1)} / {player.projection_totals.horizon_5.toFixed(1)}
                    </p>
                  )}
                </article>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}