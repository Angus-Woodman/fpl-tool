"use client";

import { useEffect, useState } from "react";

import {
  MyTeamPlayerItem,
  MyTeamResponse,
  PlayerItem,
  SaveMyTeamRequest,
  SaveMyTeamPlayerSelection,
  TeamItem,
  fetchMyTeam,
  fetchPlayers,
  fetchTeams,
  refreshProjections,
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

type EditState =
  | { type: "idle" }
  | { type: "editing" }
  | { type: "saving" }
  | { type: "error"; message: string };

type RefreshState =
  | { type: "idle" }
  | { type: "running" }
  | { type: "success"; message: string }
  | { type: "error"; message: string };

type Position = "GK" | "DEF" | "MID" | "FWD";
type OptimiseMode = "none" | "xpts" | "difficulty";

const BUDGET_CAP = 100;
const POSITION_ORDER: Position[] = ["GK", "DEF", "MID", "FWD"];
const VALID_FORMATIONS = [
  { DEF: 3, MID: 4, FWD: 3 },
  { DEF: 3, MID: 5, FWD: 2 },
  { DEF: 4, MID: 3, FWD: 3 },
  { DEF: 4, MID: 4, FWD: 2 },
  { DEF: 4, MID: 5, FWD: 1 },
  { DEF: 5, MID: 2, FWD: 3 },
  { DEF: 5, MID: 3, FWD: 2 },
  { DEF: 5, MID: 4, FWD: 1 },
];

const POSITION_COUNTS = {
  GK: 2,
  DEF: 5,
  MID: 5,
  FWD: 3,
} as const;

function choosePlayers(pool: PlayerItem[], count: number, selected: PlayerItem[]): PlayerItem[] {
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

function buildStarterSquad(playersByPosition: Record<Position, PlayerItem[]>): SaveMyTeamRequest {
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

  const totalCost = allPlayers.reduce((sum, player) => sum + player.current_price, 0);

  return {
    bank: Math.max(0, Number((BUDGET_CAP - totalCost).toFixed(1))),
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

function badgeLabel(isCaptain: boolean, isViceCaptain: boolean): string | null {
  if (isCaptain) {
    return "C";
  }
  if (isViceCaptain) {
    return "VC";
  }
  return null;
}

function draftFromTeam(team: MyTeamResponse): SaveMyTeamRequest {
  return {
    bank: team.bank,
    free_transfers: team.free_transfers,
    players: team.players.map((player) => ({
      player_id: player.player_id,
      is_starting: player.is_starting,
      bench_order: player.bench_order,
      is_captain: player.is_captain,
      is_vice_captain: player.is_vice_captain,
    })),
  };
}

function selectionMap(players: SaveMyTeamPlayerSelection[]): Map<number, SaveMyTeamPlayerSelection> {
  return new Map(players.map((player) => [player.player_id, player]));
}

function pointsForGameweek(player: MyTeamPlayerItem, gameweek: number): number {
  return player.fixture_projections
    .filter((fixture) => fixture.gameweek_number === gameweek)
    .reduce((sum, fixture) => sum + fixture.projected_points, 0);
}

function opponentLabelForGameweek(player: MyTeamPlayerItem, gameweek: number): string {
  const fixtures = player.fixture_projections
    .filter((fixture) => fixture.gameweek_number === gameweek)
    .map((fixture) => {
      if (fixture.opponent_team_short_name === null) {
        return "TBD";
      }
      if (fixture.is_home === true) {
        return `${fixture.opponent_team_short_name} (H)`;
      }
      if (fixture.is_home === false) {
        return `${fixture.opponent_team_short_name} (A)`;
      }
      return fixture.opponent_team_short_name;
    });

  if (fixtures.length === 0) {
    return "-";
  }

  return fixtures.join(", ");
}

function validateStartingLineup(
  selections: SaveMyTeamPlayerSelection[],
  playersById: Map<number, MyTeamPlayerItem>
): string | null {
  const starters = selections.filter((player) => player.is_starting);
  const bench = selections.filter((player) => !player.is_starting);

  if (starters.length !== 11) {
    return "Your squad must contain exactly 11 starting players.";
  }
  if (bench.length !== 4) {
    return "Your squad must contain exactly 4 bench players.";
  }

  const benchOrders = bench.map((player) => player.bench_order).sort();
  if (benchOrders.join(",") !== "1,2,3,4") {
    return "Bench players must have unique bench order values 1, 2, 3, and 4.";
  }

  const counts: Record<Position, number> = { GK: 0, DEF: 0, MID: 0, FWD: 0 };
  for (const starter of starters) {
    const player = playersById.get(starter.player_id);
    if (!player) {
      return "Starting XI has unknown players.";
    }
    counts[player.position] += 1;
  }

  if (counts.GK !== 1) {
    return "Starting XI must contain exactly 1 goalkeeper.";
  }
  if (counts.DEF < 3) {
    return "Starting XI must contain at least 3 defenders.";
  }
  if (counts.MID < 3) {
    return "Starting XI must contain at least 3 midfielders.";
  }
  if (counts.FWD < 1) {
    return "Starting XI must contain at least 1 forward.";
  }

  return null;
}

function findOptimisedSelectionForGameweek(
  baseSelections: SaveMyTeamPlayerSelection[],
  playersById: Map<number, MyTeamPlayerItem>,
  gameweek: number,
  mode: "xpts" | "difficulty",
  difficultyByShortName: Map<string, number>
): SaveMyTeamPlayerSelection[] {
  function score(player: MyTeamPlayerItem): number {
    if (mode === "xpts") {
      return pointsForGameweek(player, gameweek);
    }

    const fixtures = player.fixture_projections.filter(
      (fixture) => fixture.gameweek_number === gameweek
    );
    if (fixtures.length === 0) {
      return Number.NEGATIVE_INFINITY;
    }

    // Lower opponent difficulty is better; invert onto a "higher is better" scale like xPts.
    return fixtures.reduce((sum, fixture) => {
      const difficulty = fixture.opponent_team_short_name
        ? (difficultyByShortName.get(fixture.opponent_team_short_name) ?? 3)
        : 3;
      return sum + (6 - difficulty);
    }, 0);
  }

  const squadPlayers = baseSelections
    .map((selection) => {
      const player = playersById.get(selection.player_id);
      if (!player) {
        return null;
      }
      return { selection, player, points: score(player) };
    })
    .filter(
      (item): item is { selection: SaveMyTeamPlayerSelection; player: MyTeamPlayerItem; points: number } =>
        item !== null
    );

  const goalkeepers = squadPlayers
    .filter((item) => item.player.position === "GK")
    .sort((a, b) => b.points - a.points);
  const defenders = squadPlayers
    .filter((item) => item.player.position === "DEF")
    .sort((a, b) => b.points - a.points);
  const midfielders = squadPlayers
    .filter((item) => item.player.position === "MID")
    .sort((a, b) => b.points - a.points);
  const forwards = squadPlayers
    .filter((item) => item.player.position === "FWD")
    .sort((a, b) => b.points - a.points);

  let bestStarterIds = new Set<number>();
  let bestTotal = Number.NEGATIVE_INFINITY;

  for (const formation of VALID_FORMATIONS) {
    if (
      defenders.length < formation.DEF ||
      midfielders.length < formation.MID ||
      forwards.length < formation.FWD ||
      goalkeepers.length < 1
    ) {
      continue;
    }

    const starters = [
      goalkeepers[0],
      ...defenders.slice(0, formation.DEF),
      ...midfielders.slice(0, formation.MID),
      ...forwards.slice(0, formation.FWD),
    ];

    const starterPoints = starters.reduce((sum, item) => sum + item.points, 0);
    const captainPoints = starters.reduce((max, item) => Math.max(max, item.points), 0);
    const total = starterPoints + captainPoints;

    if (total > bestTotal) {
      bestTotal = total;
      bestStarterIds = new Set(starters.map((item) => item.player.player_id));
    }
  }

  const recommended = baseSelections.map((selection) => ({
    ...selection,
    is_starting: bestStarterIds.has(selection.player_id),
    bench_order: bestStarterIds.has(selection.player_id) ? null : selection.bench_order,
    is_captain: false,
    is_vice_captain: false,
  }));

  const starterRows = recommended
    .filter((selection) => selection.is_starting)
    .map((selection) => {
      const player = playersById.get(selection.player_id)!;
      return { selection, points: score(player), position: player.position };
    })
    .sort((a, b) => b.points - a.points);

  if (starterRows[0]) {
    starterRows[0].selection.is_captain = true;
  }
  if (starterRows[1]) {
    starterRows[1].selection.is_vice_captain = true;
  }

  const benchRows = recommended
    .filter((selection) => !selection.is_starting)
    .map((selection) => {
      const player = playersById.get(selection.player_id)!;
      return { selection, points: score(player), position: player.position };
    });
  const benchGoalkeeper = benchRows.find((row) => row.position === "GK");
  const benchOutfield = benchRows
    .filter((row) => row.position !== "GK")
    .sort((a, b) => b.points - a.points);

  const benchOrderRows = [
    ...(benchGoalkeeper ? [benchGoalkeeper] : []),
    ...benchOutfield,
  ];
  benchOrderRows.forEach((row, index) => {
    row.selection.bench_order = index + 1;
  });

  return recommended;
}

function lineupPointsForGameweek(
  selections: SaveMyTeamPlayerSelection[],
  playersById: Map<number, MyTeamPlayerItem>,
  gameweek: number
): number {
  const starters = selections.filter((selection) => selection.is_starting);
  const captain = starters.find((selection) => selection.is_captain);

  const starterPoints = starters.reduce((sum, selection) => {
    const player = playersById.get(selection.player_id);
    if (!player) {
      return sum;
    }
    return sum + pointsForGameweek(player, gameweek);
  }, 0);

  const captainPoints = captain ? pointsForGameweek(playersById.get(captain.player_id)!, gameweek) : 0;
  return starterPoints + captainPoints;
}

function canSwapStarterWithBench(
  starterId: number,
  benchId: number,
  selections: SaveMyTeamPlayerSelection[],
  playersById: Map<number, MyTeamPlayerItem>
): boolean {
  const starterSelection = selections.find((selection) => selection.player_id === starterId);
  const benchSelection = selections.find((selection) => selection.player_id === benchId);
  if (!starterSelection || !benchSelection || !starterSelection.is_starting || benchSelection.is_starting) {
    return false;
  }

  const starterPlayer = playersById.get(starterId);
  const benchPlayer = playersById.get(benchId);
  if (!starterPlayer || !benchPlayer) {
    return false;
  }

  if ((starterPlayer.position === "GK") !== (benchPlayer.position === "GK")) {
    return false;
  }

  const starterIds = new Set(
    selections.filter((selection) => selection.is_starting).map((selection) => selection.player_id)
  );
  starterIds.delete(starterId);
  starterIds.add(benchId);

  const counts: Record<Position, number> = { GK: 0, DEF: 0, MID: 0, FWD: 0 };
  for (const playerId of starterIds) {
    const player = playersById.get(playerId);
    if (!player) {
      return false;
    }
    counts[player.position] += 1;
  }

  return (
    starterIds.size === 11 &&
    counts.GK === 1 &&
    counts.DEF >= 3 &&
    counts.MID >= 3 &&
    counts.FWD >= 1
  );
}

export function MyTeamBoard(): JSX.Element {
  const [state, setState] = useState<LoadState>({ type: "loading" });
  const [createState, setCreateState] = useState<CreateStarterSquadState>({ type: "idle" });
  const [editState, setEditState] = useState<EditState>({ type: "idle" });
  const [refreshState, setRefreshState] = useState<RefreshState>({ type: "idle" });
  const [draft, setDraft] = useState<SaveMyTeamRequest | null>(null);
  const [selectedGameweekIndex, setSelectedGameweekIndex] = useState(0);
  const [optimiseMode, setOptimiseMode] = useState<OptimiseMode>("none");
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [swapTargetStarterId, setSwapTargetStarterId] = useState<number | null>(null);
  const [swapChoiceBenchId, setSwapChoiceBenchId] = useState<number | null>(null);
  const [transferPlayerPool, setTransferPlayerPool] = useState<PlayerItem[] | null>(null);
  const [transferTargetPlayerId, setTransferTargetPlayerId] = useState<number | null>(null);
  const [transferChoicePlayerId, setTransferChoicePlayerId] = useState<number | null>(null);
  const [transferSavingPlayerId, setTransferSavingPlayerId] = useState<number | null>(null);
  const [transferError, setTransferError] = useState<string | null>(null);

  async function loadMyTeam(): Promise<MyTeamResponse | null> {
    try {
      const data = await fetchMyTeam();

      if (data === null || data.players.length === 0) {
        setState({ type: "empty" });
        setDraft(null);
        return null;
      }

      setState({ type: "loaded", team: data });
      setSelectedGameweekIndex(0);
      return data;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load my team";
      setState({ type: "error", message });
      setDraft(null);
      return null;
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

        if (data === null || data.players.length === 0) {
          setState({ type: "empty" });
          return;
        }

        setState({ type: "loaded", team: data });
        setSelectedGameweekIndex(0);
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

  useEffect(() => {
    let cancelled = false;

    async function run(): Promise<void> {
      try {
        const data = await fetchTeams();
        if (!cancelled) {
          setTeams(data.items);
        }
      } catch {
        // Fixture-difficulty optimisation just falls back to a neutral rating if teams fail to load.
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

  async function handleRefreshPoints(): Promise<void> {
    setRefreshState({ type: "running" });
    try {
      const summary = await refreshProjections();
      await loadMyTeam();
      setRefreshState({
        type: "success",
        message: `Refreshed xPts (${summary.projections_generated} projections).`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to refresh xPts";
      setRefreshState({ type: "error", message });
    }
  }

  async function ensureTransferPlayerPool(): Promise<PlayerItem[] | null> {
    if (transferPlayerPool !== null) {
      return transferPlayerPool;
    }

    try {
      const [gk, def, mid, fwd] = await Promise.all([
        fetchPlayers({ position: "GK", status: "a", sort: "price_desc", page_size: 60 }),
        fetchPlayers({ position: "DEF", status: "a", sort: "price_desc", page_size: 150 }),
        fetchPlayers({ position: "MID", status: "a", sort: "price_desc", page_size: 150 }),
        fetchPlayers({ position: "FWD", status: "a", sort: "price_desc", page_size: 100 }),
      ]);
      const pool = [...gk.items, ...def.items, ...mid.items, ...fwd.items];
      setTransferPlayerPool(pool);
      return pool;
    } catch (error) {
      setTransferError(error instanceof Error ? error.message : "Failed to load player pool");
      return null;
    }
  }

  function handleOpenTransfer(playerId: number): void {
    setTransferError(null);
    const isOpen = transferTargetPlayerId === playerId;
    setTransferTargetPlayerId(isOpen ? null : playerId);
    setTransferChoicePlayerId(null);
    if (!isOpen) {
      void ensureTransferPlayerPool();
    }
  }

  function handleStartEditing(team: MyTeamResponse): void {
    setOptimiseMode("none");
    setSwapTargetStarterId(null);
    setSwapChoiceBenchId(null);
    setTransferTargetPlayerId(null);
    setTransferChoicePlayerId(null);
    setTransferError(null);
    setDraft(draftFromTeam(team));
    setEditState({ type: "editing" });
  }

  function handleCancelEditing(): void {
    setSwapTargetStarterId(null);
    setSwapChoiceBenchId(null);
    setTransferTargetPlayerId(null);
    setTransferChoicePlayerId(null);
    setTransferError(null);
    setDraft(null);
    setEditState({ type: "idle" });
  }

  function clearEditError(): void {
    if (editState.type === "error") {
      setEditState({ type: "editing" });
    }
  }

  function applyStarterBenchSwap(starterId: number, benchId: number): void {
    clearEditError();
    setDraft((currentDraft) => {
      if (!currentDraft) {
        return currentDraft;
      }

      const starter = currentDraft.players.find((player) => player.player_id === starterId);
      const bench = currentDraft.players.find((player) => player.player_id === benchId);
      if (!starter || !bench) {
        return currentDraft;
      }

      if (!canSwapStarterWithBench(starterId, benchId, currentDraft.players, playersById)) {
        return currentDraft;
      }

      return {
        ...currentDraft,
        players: currentDraft.players.map((player) => {
          if (player.player_id === starterId) {
            return {
              ...player,
              is_starting: false,
              bench_order: bench.bench_order,
              is_captain: false,
              is_vice_captain: false,
            };
          }

          if (player.player_id === benchId) {
            return {
              ...player,
              is_starting: true,
              bench_order: null,
              is_captain: starter.is_captain,
              is_vice_captain: starter.is_vice_captain,
            };
          }

          return player;
        }),
      };
    });

    setSwapTargetStarterId(null);
    setSwapChoiceBenchId(null);
  }

  async function handleSaveChanges(): Promise<void> {
    if (draft === null || state.type !== "loaded") {
      return;
    }

    const validationMessage = validateStartingLineup(draft.players, playersById);
    if (validationMessage) {
      setEditState({ type: "error", message: validationMessage });
      return;
    }

    const totalCost = loadedTeam.players.reduce((sum, player) => sum + player.current_price, 0);
    const computedBank = Number((BUDGET_CAP - totalCost).toFixed(1));
    if (computedBank < 0) {
      setEditState({ type: "error", message: "Squad value cannot exceed 100.0m." });
      return;
    }

    setEditState({ type: "saving" });
    try {
      await saveMyTeam({
        ...draft,
        bank: computedBank,
        free_transfers: loadedTeam.free_transfers,
      });
      const reloadedTeam = await loadMyTeam();
      if (reloadedTeam !== null) {
        setDraft(draftFromTeam(reloadedTeam));
      }
      setEditState({ type: "idle" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save squad changes";
      setEditState({ type: "error", message });
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

  const loadedTeam = state.team;

  const activeDraft =
    editState.type === "editing" || editState.type === "saving" || editState.type === "error"
      ? draft
      : null;

  const userSelections = activeDraft ? activeDraft.players : draftFromTeam(loadedTeam).players;
  const playersById = new Map(loadedTeam.players.map((player) => [player.player_id, player]));
  const difficultyByShortName = new Map(teams.map((team) => [team.short_name, team.difficulty]));

  const gameweekNumbers = loadedTeam.gameweek_numbers;
  const currentGameweek = gameweekNumbers[selectedGameweekIndex] ?? null;

  const effectiveSelections =
    optimiseMode !== "none" && currentGameweek !== null
      ? findOptimisedSelectionForGameweek(
          userSelections,
          playersById,
          currentGameweek,
          optimiseMode,
          difficultyByShortName
        )
      : userSelections;

  const selectionByPlayerId = selectionMap(effectiveSelections);

  const playerRows = loadedTeam.players.map((player) => {
    const selection = selectionByPlayerId.get(player.player_id);
    return {
      player,
      selection: selection ?? {
        player_id: player.player_id,
        is_starting: false,
        bench_order: null,
        is_captain: false,
        is_vice_captain: false,
      },
    };
  });

  const starters = playerRows.filter((row) => row.selection.is_starting);
  const bench = playerRows
    .filter((row) => !row.selection.is_starting)
    .sort((left, right) => (left.selection.bench_order ?? 99) - (right.selection.bench_order ?? 99));

  const startersByPosition = new Map<Position, typeof starters>();
  const benchByPosition = new Map<Position, typeof bench>();
  for (const position of POSITION_ORDER) {
    startersByPosition.set(position, starters.filter((row) => row.player.position === position));
    benchByPosition.set(position, bench.filter((row) => row.player.position === position));
  }

  function horizonTotal(horizonSize: number): number | null {
    if (gameweekNumbers.length === 0 || currentGameweek === null) {
      return null;
    }

    const slice = gameweekNumbers.slice(selectedGameweekIndex, selectedGameweekIndex + horizonSize);
    if (slice.length === 0) {
      return null;
    }

    if (optimiseMode !== "none") {
      return slice.reduce((sum, gameweek) => {
        const recommended = findOptimisedSelectionForGameweek(
          userSelections,
          playersById,
          gameweek,
          optimiseMode,
          difficultyByShortName
        );
        return sum + lineupPointsForGameweek(recommended, playersById, gameweek);
      }, 0);
    }

    return slice.reduce((sum, gameweek) => sum + lineupPointsForGameweek(userSelections, playersById, gameweek), 0);
  }

  const oneGwTotal = horizonTotal(1);
  const threeGwTotal = horizonTotal(3);
  const fiveGwTotal = horizonTotal(5);

  const projectionCards = [
    { label: "1 GW xPts", value: oneGwTotal },
    { label: "3 GW xPts", value: threeGwTotal },
    { label: "5 GW xPts", value: fiveGwTotal },
  ];

  const totalCost = loadedTeam.players.reduce((sum, player) => sum + player.current_price, 0);
  const bank = Number((BUDGET_CAP - totalCost).toFixed(1));

  function eligibleBenchOptionsForStarter(starterId: number): MyTeamPlayerItem[] {
    const sourceSelections = activeDraft ? activeDraft.players : userSelections;
    return loadedTeam.players.filter((candidate) => {
      const selection = sourceSelections.find((item) => item.player_id === candidate.player_id);
      if (!selection || selection.is_starting) {
        return false;
      }
      return canSwapStarterWithBench(starterId, candidate.player_id, sourceSelections, playersById);
    });
  }

  function eligibleTransferOptions(outgoing: MyTeamPlayerItem): PlayerItem[] {
    if (!transferPlayerPool) {
      return [];
    }

    const rosteredIds = new Set(loadedTeam.players.map((player) => player.player_id));
    const teamCounts = new Map<string, number>();
    for (const player of loadedTeam.players) {
      if (player.player_id === outgoing.player_id) {
        continue;
      }
      teamCounts.set(player.team_short_name, (teamCounts.get(player.team_short_name) ?? 0) + 1);
    }

    const availableBudget = Number((bank + outgoing.current_price).toFixed(1));

    return transferPlayerPool
      .filter((candidate) => candidate.position === outgoing.position)
      .filter((candidate) => !rosteredIds.has(candidate.id))
      .filter((candidate) => candidate.current_price <= availableBudget)
      .filter((candidate) => (teamCounts.get(candidate.team_short_name) ?? 0) < 3)
      .sort((a, b) => b.current_price - a.current_price);
  }

  async function handleConfirmTransfer(outgoingPlayerId: number): Promise<void> {
    if (transferChoicePlayerId === null) {
      return;
    }

    const outgoing = playersById.get(outgoingPlayerId);
    const incoming = transferPlayerPool?.find((player) => player.id === transferChoicePlayerId);
    if (!outgoing || !incoming) {
      return;
    }

    const newBank = Number((bank + outgoing.current_price - incoming.current_price).toFixed(1));
    if (newBank < 0) {
      setTransferError("Not enough budget for that transfer.");
      return;
    }

    setTransferSavingPlayerId(outgoingPlayerId);
    setTransferError(null);
    try {
      const sourceSelections = activeDraft ? activeDraft.players : userSelections;
      const players = sourceSelections.map((selection) =>
        selection.player_id === outgoingPlayerId ? { ...selection, player_id: incoming.id } : selection
      );

      await saveMyTeam({
        bank: newBank,
        free_transfers: loadedTeam.free_transfers,
        players,
      });

      const reloadedTeam = await loadMyTeam();
      if (reloadedTeam !== null) {
        setDraft(draftFromTeam(reloadedTeam));
      }
      setTransferTargetPlayerId(null);
      setTransferChoicePlayerId(null);
    } catch (error) {
      setTransferError(error instanceof Error ? error.message : "Failed to complete transfer");
    } finally {
      setTransferSavingPlayerId(null);
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">{loadedTeam.name}</h2>
          <p className="mt-1 text-sm text-slate-600">Starting XI and bench projections across upcoming gameweeks.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={() => void handleRefreshPoints()}
            disabled={refreshState.type === "running" || editState.type === "saving"}
          >
            {refreshState.type === "running" ? "Refreshing xPts..." : "Refresh xPts"}
          </button>
          {editState.type === "editing" || editState.type === "saving" || editState.type === "error" ? (
            <>
              <button
                type="button"
                className="rounded-md border border-emerald-300 bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                onClick={() => void handleSaveChanges()}
                disabled={editState.type === "saving"}
              >
                {editState.type === "saving" ? "Saving..." : "Save Changes"}
              </button>
              <button
                type="button"
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
                onClick={handleCancelEditing}
                disabled={editState.type === "saving"}
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              type="button"
              className="rounded-md border border-slate-300 bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
              onClick={() => handleStartEditing(loadedTeam)}
            >
              Edit Team
            </button>
          )}
          <span className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-700">Cost: {totalCost.toFixed(1)}</span>
          <span className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-700">Bank: {bank.toFixed(1)}</span>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          disabled={selectedGameweekIndex <= 0}
          onClick={() => setSelectedGameweekIndex((value) => Math.max(0, value - 1))}
        >
          Previous Game
        </button>
        <span className="text-sm font-medium text-slate-700">
          {currentGameweek !== null ? `Gameweek ${currentGameweek}` : "No gameweek data"}
        </span>
        <button
          type="button"
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          disabled={selectedGameweekIndex >= gameweekNumbers.length - 1}
          onClick={() =>
            setSelectedGameweekIndex((value) => Math.min(gameweekNumbers.length - 1, value + 1))
          }
        >
          Next Game
        </button>

        <label className="ml-auto flex items-center gap-2 text-sm text-slate-700">
          Optimise starting 11 by
          <select
            aria-label="Optimise starting 11 by"
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900"
            value={optimiseMode}
            onChange={(event) => {
              setOptimiseMode(event.target.value as OptimiseMode);
              setSwapTargetStarterId(null);
              setSwapChoiceBenchId(null);
            }}
          >
            <option value="none">None</option>
            <option value="xpts">xPts</option>
            <option value="difficulty">Fixture difficulty</option>
          </select>
        </label>
      </div>

      {refreshState.type === "success" && <p className="mb-4 text-sm text-emerald-700">{refreshState.message}</p>}
      {refreshState.type === "error" && <p className="mb-4 text-sm text-red-700">{refreshState.message}</p>}
      {editState.type === "error" && <p className="mb-4 text-sm text-red-700">{editState.message}</p>}

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
          <div className="space-y-5">
            {POSITION_ORDER.map((position) => {
              const rows = startersByPosition.get(position) ?? [];
              if (rows.length === 0) {
                return null;
              }

              return (
                <section key={`starters-${position}`}>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {position}
                  </h4>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {rows.map((row) => {
                      const badge = badgeLabel(row.selection.is_captain, row.selection.is_vice_captain);
                      const gwPoints =
                        currentGameweek !== null ? pointsForGameweek(row.player, currentGameweek) : null;
                      const opposition =
                        currentGameweek !== null
                          ? opponentLabelForGameweek(row.player, currentGameweek)
                          : "-";

                      return (
                        <article key={row.player.player_id} className="rounded-lg border border-slate-200 p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-slate-900">{row.player.web_name}</p>
                              <p className="text-xs text-slate-600">
                                {row.player.team_short_name} · {row.player.position}
                              </p>
                            </div>
                            {badge && (
                              <span className="rounded-full bg-slate-900 px-2 py-1 text-[10px] font-semibold text-white">
                                {badge}
                              </span>
                            )}
                          </div>
                          <p className="mt-2 text-xs text-slate-600">Opponent: {opposition}</p>
                          <p className="mt-1 text-xs text-slate-600">
                            GW xPts: {gwPoints?.toFixed(1) ?? "-"}
                          </p>
                          {activeDraft && optimiseMode === "none" && (
                            <div className="mt-3 space-y-2 text-xs text-slate-700">
                              <div className="flex flex-wrap gap-2">
                                <button
                                  type="button"
                                  aria-label={`Swap ${row.player.web_name} with bench`}
                                  className="rounded-md border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50"
                                  onClick={() => {
                                    const isOpen = swapTargetStarterId === row.player.player_id;
                                    setSwapTargetStarterId(isOpen ? null : row.player.player_id);
                                    setSwapChoiceBenchId(null);
                                  }}
                                >
                                  Swap With Bench
                                </button>
                                <button
                                  type="button"
                                  aria-label={`Transfer ${row.player.web_name}`}
                                  className="rounded-md border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50"
                                  onClick={() => handleOpenTransfer(row.player.player_id)}
                                >
                                  Transfer
                                </button>
                              </div>

                              {swapTargetStarterId === row.player.player_id && (
                                <div className="space-y-2">
                                  <label className="block">
                                    Bench Player
                                    <select
                                      aria-label={`Bench Player for ${row.player.web_name}`}
                                      className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1"
                                      value={swapChoiceBenchId ?? ""}
                                      onChange={(event) => setSwapChoiceBenchId(Number(event.target.value))}
                                    >
                                      <option value="">Select bench player</option>
                                      {eligibleBenchOptionsForStarter(row.player.player_id).map((benchPlayer) => (
                                        <option key={benchPlayer.player_id} value={benchPlayer.player_id}>
                                          {benchPlayer.web_name} ({benchPlayer.position})
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                  <button
                                    type="button"
                                    className="rounded-md border border-emerald-300 bg-emerald-600 px-2 py-1 text-white hover:bg-emerald-500 disabled:opacity-50"
                                    disabled={swapChoiceBenchId === null}
                                    onClick={() => {
                                      if (swapChoiceBenchId !== null) {
                                        applyStarterBenchSwap(row.player.player_id, swapChoiceBenchId);
                                      }
                                    }}
                                  >
                                    Confirm Swap
                                  </button>
                                </div>
                              )}

                              {transferTargetPlayerId === row.player.player_id && (
                                <div className="space-y-2">
                                  <label className="block">
                                    Replacement Player
                                    <select
                                      aria-label={`Replacement Player for ${row.player.web_name}`}
                                      className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1"
                                      value={transferChoicePlayerId ?? ""}
                                      disabled={transferPlayerPool === null}
                                      onChange={(event) =>
                                        setTransferChoicePlayerId(Number(event.target.value))
                                      }
                                    >
                                      <option value="">
                                        {transferPlayerPool === null ? "Loading players..." : "Select replacement"}
                                      </option>
                                      {eligibleTransferOptions(row.player).map((candidate) => (
                                        <option key={candidate.id} value={candidate.id}>
                                          {candidate.web_name} ({candidate.team_short_name}) £
                                          {candidate.current_price.toFixed(1)}m
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                  <button
                                    type="button"
                                    className="rounded-md border border-emerald-300 bg-emerald-600 px-2 py-1 text-white hover:bg-emerald-500 disabled:opacity-50"
                                    disabled={
                                      transferChoicePlayerId === null ||
                                      transferSavingPlayerId === row.player.player_id
                                    }
                                    onClick={() => void handleConfirmTransfer(row.player.player_id)}
                                  >
                                    {transferSavingPlayerId === row.player.player_id
                                      ? "Saving..."
                                      : "Confirm Transfer"}
                                  </button>
                                  {transferError && <p className="text-red-700">{transferError}</p>}
                                </div>
                              )}
                            </div>
                          )}
                        </article>
                      );
                    })}
                  </div>
                </section>
              );
            })}
          </div>
        </div>

        <div>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Bench</h3>
          <div className="space-y-5">
            {POSITION_ORDER.map((position) => {
              const rows = benchByPosition.get(position) ?? [];
              if (rows.length === 0) {
                return null;
              }

              return (
                <section key={`bench-${position}`}>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {position}
                  </h4>
                  <div className="space-y-3">
                    {rows.map((row) => {
                      const gwPoints =
                        currentGameweek !== null ? pointsForGameweek(row.player, currentGameweek) : null;
                      const opposition =
                        currentGameweek !== null
                          ? opponentLabelForGameweek(row.player, currentGameweek)
                          : "-";

                      return (
                        <article key={row.player.player_id} className="rounded-lg border border-slate-200 p-3">
                          <p className="text-sm font-semibold text-slate-900">{row.player.web_name}</p>
                          <p className="text-xs text-slate-600">
                            Bench {row.selection.bench_order} · {row.player.team_short_name} · {row.player.position}
                          </p>
                          <p className="mt-2 text-xs text-slate-600">Opponent: {opposition}</p>
                          <p className="mt-1 text-xs text-slate-600">
                            GW xPts: {gwPoints?.toFixed(1) ?? "-"}
                          </p>
                          {activeDraft && optimiseMode === "none" && (
                            <div className="mt-3 space-y-2 text-xs text-slate-700">
                              <button
                                type="button"
                                aria-label={`Transfer ${row.player.web_name}`}
                                className="rounded-md border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50"
                                onClick={() => handleOpenTransfer(row.player.player_id)}
                              >
                                Transfer
                              </button>

                              {transferTargetPlayerId === row.player.player_id && (
                                <div className="space-y-2">
                                  <label className="block">
                                    Replacement Player
                                    <select
                                      aria-label={`Replacement Player for ${row.player.web_name}`}
                                      className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1"
                                      value={transferChoicePlayerId ?? ""}
                                      disabled={transferPlayerPool === null}
                                      onChange={(event) =>
                                        setTransferChoicePlayerId(Number(event.target.value))
                                      }
                                    >
                                      <option value="">
                                        {transferPlayerPool === null ? "Loading players..." : "Select replacement"}
                                      </option>
                                      {eligibleTransferOptions(row.player).map((candidate) => (
                                        <option key={candidate.id} value={candidate.id}>
                                          {candidate.web_name} ({candidate.team_short_name}) £
                                          {candidate.current_price.toFixed(1)}m
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                  <button
                                    type="button"
                                    className="rounded-md border border-emerald-300 bg-emerald-600 px-2 py-1 text-white hover:bg-emerald-500 disabled:opacity-50"
                                    disabled={
                                      transferChoicePlayerId === null ||
                                      transferSavingPlayerId === row.player.player_id
                                    }
                                    onClick={() => void handleConfirmTransfer(row.player.player_id)}
                                  >
                                    {transferSavingPlayerId === row.player.player_id
                                      ? "Saving..."
                                      : "Confirm Transfer"}
                                  </button>
                                  {transferError && <p className="text-red-700">{transferError}</p>}
                                </div>
                              )}
                            </div>
                          )}
                        </article>
                      );
                    })}
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
