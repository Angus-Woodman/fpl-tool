"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  PlanChip,
  PlanGameweek,
  PlanPlayer,
  PlanResponse,
  PlanRuleError,
  PlayerItem,
  SaveMyTeamPlayerSelection,
  fetchPlan,
  fetchPlayers,
  savePlanGameweek,
  updatePlan,
} from "@/lib/api";

type Position = "GK" | "DEF" | "MID" | "FWD";

type LoadState =
  | { type: "loading" }
  | { type: "error"; message: string }
  | { type: "missing" }
  | { type: "loaded"; plan: PlanResponse };

const POSITION_ORDER: Position[] = ["GK", "DEF", "MID", "FWD"];
const FORMATION_LIMITS: Record<Position, { min: number; max: number }> = {
  GK: { min: 1, max: 1 },
  DEF: { min: 3, max: 5 },
  MID: { min: 2, max: 5 },
  FWD: { min: 1, max: 3 },
};
const CHIPS: { value: PlanChip; label: string }[] = [
  { value: "WILDCARD", label: "Wildcard" },
  { value: "FREE_HIT", label: "Free Hit" },
  { value: "BENCH_BOOST", label: "Bench Boost" },
  { value: "TRIPLE_CAPTAIN", label: "Triple Captain" },
];
const FIRST_HALF_FINAL_GAMEWEEK = 19;

function seasonHalf(gameweekNumber: number): 1 | 2 {
  return gameweekNumber <= FIRST_HALF_FINAL_GAMEWEEK ? 1 : 2;
}

function chipUsedElsewhereInHalf(
  plan: PlanResponse,
  chip: PlanChip,
  gameweekNumber: number,
): boolean {
  return plan.gameweeks.some(
    (gameweek) =>
      gameweek.chip === chip &&
      gameweek.gameweek_number !== gameweekNumber &&
      seasonHalf(gameweek.gameweek_number) === seasonHalf(gameweekNumber),
  );
}

function formationIsLegal(players: PlanPlayer[]): boolean {
  const counts: Record<Position, number> = { GK: 0, DEF: 0, MID: 0, FWD: 0 };
  for (const player of players.filter((player) => player.is_starting)) {
    counts[player.position] += 1;
  }
  return POSITION_ORDER.every(
    (position) =>
      counts[position] >= FORMATION_LIMITS[position].min &&
      counts[position] <= FORMATION_LIMITS[position].max,
  );
}

function swapStarterWithBench(
  players: PlanPlayer[],
  starterId: number,
  benchId: number,
): PlanPlayer[] {
  const starter = players.find((player) => player.player_id === starterId);
  const bench = players.find((player) => player.player_id === benchId);
  if (!starter || !bench) {
    return players;
  }

  return players.map((player) => {
    if (player.player_id === starterId) {
      return { ...player, is_starting: false, bench_order: bench.bench_order };
    }
    if (player.player_id === benchId) {
      return { ...player, is_starting: true, bench_order: null };
    }
    return player;
  });
}

function toSelections(players: PlanPlayer[]): SaveMyTeamPlayerSelection[] {
  return players.map((player) => ({
    player_id: player.player_id,
    is_starting: player.is_starting,
    bench_order: player.bench_order,
    is_captain: player.is_captain,
    is_vice_captain: player.is_vice_captain,
  }));
}

function toPlanPlayer(item: PlayerItem): PlanPlayer {
  return {
    player_id: item.id,
    web_name: item.web_name,
    team_short_name: item.team_short_name,
    position: item.position,
    current_price: item.current_price,
    status: item.status,
    is_starting: false,
    bench_order: null,
    is_captain: false,
    is_vice_captain: false,
    projected_points: 0,
    fixtures: [],
  };
}

function opponentLabel(player: PlanPlayer): string {
  if (player.fixtures.length === 0) {
    return "-";
  }
  return player.fixtures
    .map((fixture) => {
      if (fixture.opponent_team_short_name === null) {
        return "TBD";
      }
      const venue = fixture.is_home === null ? "" : fixture.is_home ? " (H)" : " (A)";
      return `${fixture.opponent_team_short_name}${venue}`;
    })
    .join(", ");
}

export function PlanBoard({ planId }: { planId: number }): JSX.Element {
  const [state, setState] = useState<LoadState>({ type: "loading" });
  const [selectedGameweek, setSelectedGameweek] = useState<number | null>(null);
  const [draft, setDraft] = useState<PlanPlayer[] | null>(null);
  const [draftChip, setDraftChip] = useState<PlanChip | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [swapStarterId, setSwapStarterId] = useState<number | null>(null);
  const [transferOutId, setTransferOutId] = useState<number | null>(null);
  const [transferPool, setTransferPool] = useState<PlayerItem[]>([]);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      try {
        const plan = await fetchPlan(planId);
        if (cancelled) {
          return;
        }
        if (plan === null) {
          setState({ type: "missing" });
          return;
        }
        setState({ type: "loaded", plan });
        setSelectedGameweek((current) => current ?? plan.gameweeks[0]?.gameweek_number ?? null);
      } catch (error) {
        if (!cancelled) {
          setState({
            type: "error",
            message: error instanceof Error ? error.message : "Failed to load plan",
          });
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [planId]);

  const plan = state.type === "loaded" ? state.plan : null;
  const gameweek: PlanGameweek | null = useMemo(() => {
    if (plan === null || selectedGameweek === null) {
      return null;
    }
    return plan.gameweeks.find((item) => item.gameweek_number === selectedGameweek) ?? null;
  }, [plan, selectedGameweek]);

  useEffect(() => {
    if (gameweek === null) {
      setDraft(null);
      setDraftChip(null);
      return;
    }
    setDraft(gameweek.players);
    setDraftChip(gameweek.chip);
    setSwapStarterId(null);
    setTransferOutId(null);
  }, [gameweek]);

  async function reload(next: PlanResponse): Promise<void> {
    setState({ type: "loaded", plan: next });
  }

  async function handleSave(): Promise<void> {
    if (plan === null || selectedGameweek === null || draft === null) {
      return;
    }

    setSaving(true);
    setActionError(null);
    try {
      const next = await savePlanGameweek(plan.plan_id, selectedGameweek, {
        chip: draftChip,
        players: toSelections(draft),
      });
      await reload(next);
    } catch (error) {
      setActionError(
        error instanceof PlanRuleError || error instanceof Error
          ? error.message
          : "Failed to save gameweek",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleHorizonChange(field: "start_gameweek" | "end_gameweek", value: number) {
    if (plan === null) {
      return;
    }
    setActionError(null);
    try {
      const next = await updatePlan(plan.plan_id, { [field]: value });
      await reload(next);
      if (selectedGameweek !== null) {
        const stillPresent = next.gameweeks.some(
          (item) => item.gameweek_number === selectedGameweek,
        );
        if (!stillPresent) {
          setSelectedGameweek(next.gameweeks[0]?.gameweek_number ?? null);
        }
      }
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to adjust the horizon");
    }
  }

  async function handleOpenTransfer(player: PlanPlayer): Promise<void> {
    if (transferOutId === player.player_id) {
      setTransferOutId(null);
      return;
    }

    setTransferOutId(player.player_id);
    setActionError(null);
    try {
      const response = await fetchPlayers({
        position: player.position,
        status: "a",
        sort: "price_desc",
        page_size: 50,
      });
      setTransferPool(response.items);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to load transfer options");
    }
  }

  function handleTransfer(outgoing: PlanPlayer, incoming: PlayerItem): void {
    if (draft === null) {
      return;
    }

    setDraft(
      draft.map((player) =>
        player.player_id === outgoing.player_id
          ? {
              ...toPlanPlayer(incoming),
              is_starting: player.is_starting,
              bench_order: player.bench_order,
              is_captain: player.is_captain,
              is_vice_captain: player.is_vice_captain,
            }
          : player,
      ),
    );
    setTransferOutId(null);
  }

  function handleSwap(starterId: number, benchId: number): void {
    if (draft === null) {
      return;
    }

    const next = swapStarterWithBench(draft, starterId, benchId);
    if (!formationIsLegal(next)) {
      setActionError("That swap would leave an illegal formation.");
      return;
    }

    setActionError(null);
    setDraft(next);
    setSwapStarterId(null);
  }

  function handleCaptain(playerId: number, role: "captain" | "vice"): void {
    if (draft === null) {
      return;
    }

    setDraft(
      draft.map((player) => ({
        ...player,
        is_captain: role === "captain" ? player.player_id === playerId : player.is_captain,
        is_vice_captain: role === "vice" ? player.player_id === playerId : player.is_vice_captain,
      })),
    );
  }

  if (state.type === "loading") {
    return <p className="text-sm text-slate-600">Loading plan...</p>;
  }
  if (state.type === "error") {
    return <p className="text-sm text-red-700">{state.message}</p>;
  }
  if (state.type === "missing") {
    return (
      <p className="text-sm text-slate-600">
        That plan no longer exists.{" "}
        <Link href="/plans" className="underline">
          Back to plans
        </Link>
      </p>
    );
  }

  const currentPlan = state.plan;
  const starters = (draft ?? []).filter((player) => player.is_starting);
  const bench = (draft ?? [])
    .filter((player) => !player.is_starting)
    .sort((a, b) => (a.bench_order ?? 0) - (b.bench_order ?? 0));

  return (
    <section className="space-y-5">
      <header className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            {renaming ? (
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="text"
                  aria-label="Plan name"
                  className="w-64 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900"
                  value={renameValue}
                  onChange={(event) => setRenameValue(event.target.value)}
                />
                <button
                  type="button"
                  className="rounded-md border border-emerald-300 bg-emerald-600 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                  disabled={renameValue.trim().length === 0}
                  onClick={() =>
                    void (async () => {
                      const next = await updatePlan(currentPlan.plan_id, {
                        name: renameValue.trim(),
                      });
                      await reload(next);
                      setRenaming(false);
                    })()
                  }
                >
                  Save
                </button>
                <button
                  type="button"
                  className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-800 hover:bg-slate-50"
                  onClick={() => setRenaming(false)}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <h2 className="text-xl font-semibold">{currentPlan.name}</h2>
                <button
                  type="button"
                  aria-label="Rename plan"
                  className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-800 hover:bg-slate-50"
                  onClick={() => {
                    setRenameValue(currentPlan.name);
                    setRenaming(true);
                  }}
                >
                  Rename
                </button>
              </div>
            )}
            <p className="mt-1 text-sm text-slate-600">
              Plan xPts: {currentPlan.total_points.toFixed(1)} · Hits taken:{" "}
              {currentPlan.total_points_hit}
            </p>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm text-slate-700">
              From GW
              <input
                type="number"
                aria-label="Plan start gameweek"
                min={1}
                max={38}
                className="w-24 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900"
                value={currentPlan.start_gameweek}
                onChange={(event) =>
                  void handleHorizonChange("start_gameweek", Number(event.target.value))
                }
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-slate-700">
              To GW
              <input
                type="number"
                aria-label="Plan end gameweek"
                min={1}
                max={38}
                className="w-24 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900"
                value={currentPlan.end_gameweek}
                onChange={(event) =>
                  void handleHorizonChange("end_gameweek", Number(event.target.value))
                }
              />
            </label>
          </div>
        </div>
      </header>

      <nav aria-label="Plan gameweeks" className="flex flex-wrap gap-2">
        {currentPlan.gameweeks.map((item) => (
          <button
            key={item.gameweek_number}
            type="button"
            aria-label={`Gameweek ${item.gameweek_number}`}
            aria-current={item.gameweek_number === selectedGameweek}
            className={`rounded-lg border px-3 py-2 text-left text-xs ${
              item.gameweek_number === selectedGameweek
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-200 bg-white text-slate-800 hover:bg-slate-50"
            }`}
            onClick={() => setSelectedGameweek(item.gameweek_number)}
          >
            <span className="block font-semibold">GW {item.gameweek_number}</span>
            <span className="block">{item.total_points.toFixed(1)} xPts</span>
            <span className="block">
              {item.unlimited_transfers ? "Unlimited" : `${item.free_transfers_available} FT`}
              {item.points_hit > 0 ? ` · -${item.points_hit}` : ""}
            </span>
            {item.chip && <span className="block font-semibold">{item.chip}</span>}
          </button>
        ))}
      </nav>

      {actionError && <p className="text-sm text-red-700">{actionError}</p>}

      {gameweek !== null && draft !== null && (
        <div className="space-y-5">
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm text-slate-700">
                <p className="font-semibold text-slate-900">Gameweek {gameweek.gameweek_number}</p>
                <p>
                  Bank {gameweek.bank.toFixed(1)} · Free transfers{" "}
                  {gameweek.unlimited_transfers
                    ? "unlimited"
                    : gameweek.free_transfers_available}{" "}
                  · Transfers made {gameweek.transfers_made}
                  {gameweek.points_hit > 0 ? ` · Hit -${gameweek.points_hit}` : ""}
                </p>
              </div>
              <button
                type="button"
                className="rounded-md border border-emerald-300 bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                disabled={saving}
                onClick={() => void handleSave()}
              >
                {saving ? "Saving..." : "Save Gameweek"}
              </button>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {CHIPS.map((chip) => {
                const unavailable = chipUsedElsewhereInHalf(
                  currentPlan,
                  chip.value,
                  gameweek.gameweek_number,
                );
                const active = draftChip === chip.value;
                return (
                  <button
                    key={chip.value}
                    type="button"
                    aria-label={chip.label}
                    aria-pressed={active}
                    title={
                      unavailable
                        ? `${chip.label} is already used in this half of the season`
                        : undefined
                    }
                    disabled={unavailable}
                    className={`rounded-md border px-3 py-1.5 text-xs font-medium disabled:opacity-40 ${
                      active
                        ? "border-slate-900 bg-slate-900 text-white"
                        : "border-slate-300 bg-white text-slate-800 hover:bg-slate-50"
                    }`}
                    onClick={() => setDraftChip(active ? null : chip.value)}
                  >
                    {chip.label}
                  </button>
                );
              })}
            </div>

            {(gameweek.transfers_in.length > 0 || gameweek.transfers_out.length > 0) && (
              <p className="mt-3 text-xs text-slate-600">
                Transfers: {gameweek.transfers_out.map((item) => item.web_name).join(", ") || "-"}{" "}
                → {gameweek.transfers_in.map((item) => item.web_name).join(", ") || "-"}
              </p>
            )}
          </section>

          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <section>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Starting XI
              </h3>
              <div className="space-y-5">
                {POSITION_ORDER.map((position) => {
                  const rows = starters.filter((player) => player.position === position);
                  if (rows.length === 0) {
                    return null;
                  }

                  return (
                    <section key={position}>
                      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                        {position}
                      </h4>
                      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                        {rows.map((player) => (
                          <article
                            key={player.player_id}
                            className="rounded-lg border border-slate-200 p-3"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <p className="text-sm font-semibold text-slate-900">
                                  {player.web_name}
                                </p>
                                <p className="text-xs text-slate-600">
                                  {player.team_short_name} · {player.position} ·{" "}
                                  {player.current_price.toFixed(1)}
                                </p>
                              </div>
                              {(player.is_captain || player.is_vice_captain) && (
                                <span className="rounded-full bg-slate-900 px-2 py-1 text-[10px] font-semibold text-white">
                                  {player.is_captain ? "C" : "VC"}
                                </span>
                              )}
                            </div>
                            <p className="mt-2 text-xs text-slate-600">
                              Opponent: {opponentLabel(player)}
                            </p>
                            <p className="mt-1 text-xs text-slate-600">
                              GW xPts: {player.projected_points.toFixed(1)}
                            </p>
                            <div className="mt-3 flex flex-wrap gap-2 text-xs">
                              <button
                                type="button"
                                aria-label={`Swap ${player.web_name} with bench`}
                                className="rounded-md border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50"
                                onClick={() =>
                                  setSwapStarterId(
                                    swapStarterId === player.player_id ? null : player.player_id,
                                  )
                                }
                              >
                                Swap With Bench
                              </button>
                              <button
                                type="button"
                                aria-label={`Transfer ${player.web_name}`}
                                className="rounded-md border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50"
                                onClick={() => void handleOpenTransfer(player)}
                              >
                                Transfer
                              </button>
                              <button
                                type="button"
                                aria-label={`Make ${player.web_name} captain`}
                                className="rounded-md border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50"
                                onClick={() => handleCaptain(player.player_id, "captain")}
                              >
                                C
                              </button>
                              <button
                                type="button"
                                aria-label={`Make ${player.web_name} vice-captain`}
                                className="rounded-md border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50"
                                onClick={() => handleCaptain(player.player_id, "vice")}
                              >
                                VC
                              </button>
                            </div>

                            {swapStarterId === player.player_id && (
                              <ul className="mt-3 space-y-1 text-xs">
                                {bench.map((benchPlayer) => (
                                  <li key={benchPlayer.player_id}>
                                    <button
                                      type="button"
                                      aria-label={`Swap ${player.web_name} for ${benchPlayer.web_name}`}
                                      className="w-full rounded-md border border-slate-200 px-2 py-1 text-left hover:bg-slate-50"
                                      onClick={() =>
                                        handleSwap(player.player_id, benchPlayer.player_id)
                                      }
                                    >
                                      {benchPlayer.web_name} ({benchPlayer.position})
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            )}

                            {transferOutId === player.player_id && (
                              <ul className="mt-3 max-h-48 space-y-1 overflow-y-auto text-xs">
                                {transferPool
                                  .filter(
                                    (option) =>
                                      !draft.some(
                                        (selected) => selected.player_id === option.id,
                                      ),
                                  )
                                  .map((option) => (
                                    <li key={option.id}>
                                      <button
                                        type="button"
                                        aria-label={`Transfer in ${option.web_name}`}
                                        className="w-full rounded-md border border-slate-200 px-2 py-1 text-left hover:bg-slate-50"
                                        onClick={() => handleTransfer(player, option)}
                                      >
                                        {option.web_name} · {option.team_short_name} ·{" "}
                                        {option.current_price.toFixed(1)}
                                      </button>
                                    </li>
                                  ))}
                              </ul>
                            )}
                          </article>
                        ))}
                      </div>
                    </section>
                  );
                })}
              </div>
            </section>

            <section>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Bench
              </h3>
              <div className="space-y-3">
                {bench.map((player) => (
                  <article key={player.player_id} className="rounded-lg border border-slate-200 p-3">
                    <p className="text-sm font-semibold text-slate-900">
                      {player.bench_order}. {player.web_name}
                    </p>
                    <p className="text-xs text-slate-600">
                      {player.team_short_name} · {player.position} ·{" "}
                      {player.current_price.toFixed(1)}
                    </p>
                    <p className="mt-1 text-xs text-slate-600">
                      GW xPts: {player.projected_points.toFixed(1)}
                    </p>
                    <button
                      type="button"
                      aria-label={`Transfer ${player.web_name}`}
                      className="mt-2 rounded-md border border-slate-300 bg-white px-2 py-1 text-xs hover:bg-slate-50"
                      onClick={() => void handleOpenTransfer(player)}
                    >
                      Transfer
                    </button>
                    {transferOutId === player.player_id && (
                      <ul className="mt-3 max-h-48 space-y-1 overflow-y-auto text-xs">
                        {transferPool
                          .filter(
                            (option) =>
                              !draft.some((selected) => selected.player_id === option.id),
                          )
                          .map((option) => (
                            <li key={option.id}>
                              <button
                                type="button"
                                aria-label={`Transfer in ${option.web_name}`}
                                className="w-full rounded-md border border-slate-200 px-2 py-1 text-left hover:bg-slate-50"
                                onClick={() => handleTransfer(player, option)}
                              >
                                {option.web_name} · {option.team_short_name} ·{" "}
                                {option.current_price.toFixed(1)}
                              </button>
                            </li>
                          ))}
                      </ul>
                    )}
                  </article>
                ))}
              </div>
            </section>
          </div>
        </div>
      )}
    </section>
  );
}
