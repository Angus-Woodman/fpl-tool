"use client";

import { useEffect, useState } from "react";

import {
  MyTeamPlayerItem,
  MyTeamRecommendationResponse,
  MyTeamRecommendationUnavailableError,
  MyTeamResponse,
  PlayerItem,
  SaveMyTeamRequest,
  SaveMyTeamPlayerSelection,
  TeamItem,
  fetchMyTeam,
  fetchMyTeamRecommendation,
  fetchPlayers,
  fetchTeams,
  refreshProjections,
  saveMyTeam,
} from "@/lib/api";
import { Bench } from "@/components/team/bench";
import { opponentLabelForGameweek, pointsForGameweek } from "@/components/team/projection-helpers";
import { RecommendationSummary, RecommendationState, ViewMode } from "@/components/team/recommendation-summary";
import { RecommendedSquadView } from "@/components/team/recommended-squad-view";
import { SquadPitch } from "@/components/team/squad-pitch";
import {
  ClearSelectionButton,
  NoTargetsNotice,
  SwapAnnouncement,
} from "@/components/team/rearrangement-controls";
import { SquadPlayerCard, type SelectionState } from "@/components/team/squad-player-card";
import { POSITION_ORDER, type Position } from "@/components/team/types";
import {
  hasTargets,
  resolveSelection,
  selectionStateFor,
  sortByBenchOrder,
  swapAnnouncement,
  type RearrangementKind,
} from "@/lib/squad-rearrangement";

type LoadState =
  | { type: "loading" }
  | { type: "error"; message: string }
  | { type: "empty" }
  | { type: "loaded"; team: MyTeamResponse };

type CreateStarterSquadState =
  | { type: "idle" }
  | { type: "saving" }
  | { type: "error"; message: string };

type SwapState =
  | { type: "idle" }
  | { type: "saving" }
  | { type: "error"; message: string };

type RefreshState =
  | { type: "idle" }
  | { type: "running" }
  | { type: "success"; message: string }
  | { type: "error"; message: string };

type OptimiseMode = "none" | "xpts" | "difficulty";

const BUDGET_CAP = 100;
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

function badgeLabel(isCaptain: boolean, isViceCaptain: boolean): "C" | "VC" | null {
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

function applySwap(
  kind: RearrangementKind,
  firstId: number,
  secondId: number,
  selections: SaveMyTeamPlayerSelection[]
): SaveMyTeamPlayerSelection[] {
  const first = selections.find((selection) => selection.player_id === firstId);
  const second = selections.find((selection) => selection.player_id === secondId);
  if (!first || !second) {
    return selections;
  }

  if (kind === "bench_priority") {
    return selections.map((selection) => {
      if (selection.player_id === firstId) {
        return { ...selection, bench_order: second.bench_order };
      }
      if (selection.player_id === secondId) {
        return { ...selection, bench_order: first.bench_order };
      }
      return selection;
    });
  }

  const starter = first.is_starting ? first : second;
  const bench = first.is_starting ? second : first;
  return selections.map((selection) => {
    if (selection.player_id === starter.player_id) {
      return {
        ...selection,
        is_starting: false,
        bench_order: bench.bench_order,
        is_captain: false,
        is_vice_captain: false,
      };
    }
    if (selection.player_id === bench.player_id) {
      return {
        ...selection,
        is_starting: true,
        bench_order: null,
        is_captain: starter.is_captain,
        is_vice_captain: starter.is_vice_captain,
      };
    }
    return selection;
  });
}

export function MyTeamBoard(): JSX.Element {
  const [state, setState] = useState<LoadState>({ type: "loading" });
  const [createState, setCreateState] = useState<CreateStarterSquadState>({ type: "idle" });
  const [refreshState, setRefreshState] = useState<RefreshState>({ type: "idle" });
  const [selectedGameweekIndex, setSelectedGameweekIndex] = useState(0);
  const [optimiseMode, setOptimiseMode] = useState<OptimiseMode>("none");
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [selectedPlayerId, setSelectedPlayerId] = useState<number | null>(null);
  const [swapState, setSwapState] = useState<SwapState>({ type: "idle" });
  const [swapConfirmation, setSwapConfirmation] = useState("");
  const [recommendation, setRecommendation] = useState<RecommendationState>({ type: "loading" });
  const [viewMode, setViewMode] = useState<ViewMode>("current");
  // Client-only and deliberately not persisted: figures are hidden again on reload or revisit.
  const [pointsRevealed, setPointsRevealed] = useState(false);

  async function loadRecommendation(): Promise<void> {
    setRecommendation({ type: "loading" });
    try {
      const data = await fetchMyTeamRecommendation();
      if (data === null) {
        setRecommendation({ type: "no_squad" });
        return;
      }
      setRecommendation({ type: "ready", data });
    } catch (error) {
      if (error instanceof MyTeamRecommendationUnavailableError) {
        setRecommendation({
          type: "unavailable",
          code: error.code,
          message: error.message,
          missingPlayerIds: error.missingPlayerIds,
        });
        return;
      }
      const message = error instanceof Error ? error.message : "Failed to load recommendation";
      setRecommendation({ type: "error", message });
    }
  }

  async function loadMyTeam(options?: { keepGameweek?: boolean }): Promise<MyTeamResponse | null> {
    try {
      const data = await fetchMyTeam();

      if (data === null || data.players.length === 0) {
        setState({ type: "empty" });
        return null;
      }

      setState({ type: "loaded", team: data });
      if (!options?.keepGameweek) {
        setSelectedGameweekIndex(0);
      }
      return data;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load my team";
      setState({ type: "error", message });
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

  useEffect(() => {
    void loadRecommendation();
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
      await loadRecommendation();
      setRefreshState({
        type: "success",
        message: `Refreshed xPts (${summary.projections_generated} projections).`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to refresh xPts";
      setRefreshState({ type: "error", message });
    }
  }

  function clearSelection(): void {
    setSelectedPlayerId(null);
    setSwapState((current) => (current.type === "error" ? { type: "idle" } : current));
  }

  async function performSwap(
    kind: RearrangementKind,
    firstId: number,
    secondId: number,
    team: MyTeamResponse
  ): Promise<void> {
    const first = team.players.find((player) => player.player_id === firstId);
    const second = team.players.find((player) => player.player_id === secondId);
    if (!first || !second) {
      return;
    }

    setSwapState({ type: "saving" });
    try {
      // The saved bank and free transfers are sent back exactly as loaded: a lineup change must not alter them.
      await saveMyTeam({
        bank: team.bank,
        free_transfers: team.free_transfers,
        players: applySwap(kind, firstId, secondId, draftFromTeam(team).players),
      });
      await loadMyTeam({ keepGameweek: true });
      setSelectedPlayerId(null);
      setSwapConfirmation(swapAnnouncement(kind, first.web_name, second.web_name));
      setSwapState({ type: "idle" });
    } catch (error) {
      setSelectedPlayerId(null);
      setSwapConfirmation("");
      const message = error instanceof Error ? error.message : "Failed to save squad changes";
      setSwapState({ type: "error", message });
    }
  }

  async function handleSelect(playerId: number, team: MyTeamResponse): Promise<void> {
    if (swapState.type === "saving" || optimiseMode !== "none") {
      return;
    }

    setSwapState((current) => (current.type === "error" ? { type: "idle" } : current));
    const outcome = resolveSelection(team.legal_rearrangements, selectedPlayerId, playerId);
    if (outcome.type === "swap") {
      await performSwap(outcome.kind, outcome.firstPlayerId, outcome.secondPlayerId, team);
      return;
    }

    setSelectedPlayerId(outcome.type === "clear" ? null : outcome.playerId);
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

  const userSelections = draftFromTeam(loadedTeam).players;
  const playersById = new Map(loadedTeam.players.map((player) => [player.player_id, player]));
  const difficultyByShortName = new Map(teams.map((team) => [team.short_name, team.difficulty]));

  const recommendationMissingPlayerNames =
    recommendation.type === "unavailable"
      ? recommendation.missingPlayerIds.map((id) => playersById.get(id)?.web_name ?? `#${id}`)
      : [];
  const recommendationCaptainName =
    recommendation.type === "ready" ? playersById.get(recommendation.data.captain)?.web_name : undefined;
  const recommendationViceCaptainName =
    recommendation.type === "ready"
      ? playersById.get(recommendation.data.vice_captain)?.web_name
      : undefined;

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
  const bench = sortByBenchOrder(
    playerRows
      .filter((row) => !row.selection.is_starting)
      .map((row) => ({ ...row, bench_order: row.selection.bench_order }))
  );

  const startersByPosition = new Map<Position, typeof starters>();
  for (const position of POSITION_ORDER) {
    startersByPosition.set(position, starters.filter((row) => row.player.position === position));
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
  // The saved bank is shown as-is; it is never recomputed from current squad prices.
  const bank = loadedTeam.bank;

  // Rearrangement applies only to the actual saved lineup, not to a hypothetical optimiser view.
  const selectionEnabled = optimiseMode === "none";

  const selectedPlayer = selectedPlayerId !== null ? playersById.get(selectedPlayerId) : undefined;
  const selectedHasNoTargets =
    selectedPlayerId !== null && !hasTargets(loadedTeam.legal_rearrangements, selectedPlayerId);

  function selectionProps(playerId: number): {
    selectionState: SelectionState;
    onSelect: (() => void) | undefined;
    selectionDisabled: boolean;
  } {
    return {
      selectionState: selectionStateFor(loadedTeam.legal_rearrangements, selectedPlayerId, playerId),
      onSelect: selectionEnabled ? () => void handleSelect(playerId, loadedTeam) : undefined,
      selectionDisabled: swapState.type === "saving",
    };
  }

  function togglePointsRevealed(): void {
    if (pointsRevealed) {
      setViewMode("current");
    }
    setPointsRevealed(!pointsRevealed);
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
            disabled={refreshState.type === "running" || swapState.type === "saving"}
          >
            {refreshState.type === "running" ? "Refreshing xPts..." : "Refresh xPts"}
          </button>
          <button
            type="button"
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
            onClick={togglePointsRevealed}
          >
            {pointsRevealed ? "Hide projected points" : "Show projected points"}
          </button>
          {selectedPlayerId !== null && (
            <ClearSelectionButton onClick={clearSelection} disabled={swapState.type === "saving"} />
          )}
          <span className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-700">Cost: {totalCost.toFixed(1)}</span>
          <span className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-700">Bank: {bank.toFixed(1)}</span>
        </div>
      </div>

      {pointsRevealed && (
        <RecommendationSummary
          state={recommendation}
          captainName={recommendationCaptainName}
          viceCaptainName={recommendationViceCaptainName}
          missingPlayerNames={recommendationMissingPlayerNames}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          onRefreshProjections={() => void handleRefreshPoints()}
          refreshing={refreshState.type === "running"}
        />
      )}

      {pointsRevealed && viewMode === "recommended" ? (
        recommendation.type === "ready" ? (
          <RecommendedSquadView recommendation={recommendation.data} players={loadedTeam.players} />
        ) : (
          <p className="text-sm text-slate-600">
            The recommended team will appear here once a recommendation is available.
          </p>
        )
      ) : (
        <>
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
                  setSelectedPlayerId(null);
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
          <SwapAnnouncement message={swapConfirmation} />
          {swapState.type === "error" && <p className="mb-4 text-sm text-red-700">{swapState.message}</p>}
          <NoTargetsNotice name={selectedPlayer && selectedHasNoTargets ? selectedPlayer.web_name : null} />

          {pointsRevealed && (
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
          )}

          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <SquadPitch
              title="Starting XI"
              itemsByPosition={startersByPosition}
              keyFor={(row) => row.player.player_id}
              renderCard={(row) => {
                const gwPoints =
                  currentGameweek !== null ? pointsForGameweek(row.player, currentGameweek) : null;
                const opposition =
                  currentGameweek !== null
                    ? opponentLabelForGameweek(row.player, currentGameweek)
                    : "-";

                return (
                  <SquadPlayerCard
                    webName={row.player.web_name}
                    teamShortName={row.player.team_short_name}
                    position={row.player.position}
                    badge={badgeLabel(row.selection.is_captain, row.selection.is_vice_captain)}
                    projectedPoints={gwPoints}
                    showProjectedPoints={pointsRevealed}
                    opponentLabel={opposition}
                    transferHref={`/transfers?out=${row.player.player_id}`}
                    {...selectionProps(row.player.player_id)}
                  />
                );
              }}
            />

            <Bench
              items={bench}
              keyFor={(row) => row.player.player_id}
              renderCard={(row) => {
                const gwPoints =
                  currentGameweek !== null ? pointsForGameweek(row.player, currentGameweek) : null;
                const opposition =
                  currentGameweek !== null
                    ? opponentLabelForGameweek(row.player, currentGameweek)
                    : "-";

                return (
                  <SquadPlayerCard
                    webName={row.player.web_name}
                    teamShortName={row.player.team_short_name}
                    position={row.player.position}
                    benchOrder={row.selection.bench_order}
                    projectedPoints={gwPoints}
                    showProjectedPoints={pointsRevealed}
                    opponentLabel={opposition}
                    transferHref={`/transfers?out=${row.player.player_id}`}
                    {...selectionProps(row.player.player_id)}
                  />
                );
              }}
            />
          </div>
        </>
      )}
    </section>
  );
}
