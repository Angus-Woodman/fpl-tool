"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import {
  PlanChip,
  PlanDecision,
  PlanGameweek,
  PlanPlayer,
  PlanResponse,
  PlanIntent,
  PlayerItem,
  fetchPlan,
  fetchPlayers,
} from "@/lib/api";
import {
  PlanSaveCoordinator,
  PlanSaveSnapshot,
  getPlanSaveCoordinator,
} from "@/lib/plan-save-coordinator";

const EMPTY_SUBSCRIBE = () => () => {};
const EMPTY_SNAPSHOT = () => null;

type Position = "GK" | "DEF" | "MID" | "FWD";

type LoadState =
  | { type: "loading" }
  | { type: "error"; message: string }
  | { type: "missing" }
  | { type: "loaded"; plan: PlanResponse };

const POSITION_ORDER: Position[] = ["GK", "DEF", "MID", "FWD"];
const CHIPS: { value: PlanChip; label: string }[] = [
  { value: "WILDCARD", label: "Wildcard" },
  { value: "FREE_HIT", label: "Free Hit" },
  { value: "BENCH_BOOST", label: "Bench Boost" },
  { value: "TRIPLE_CAPTAIN", label: "Triple Captain" },
];
function opponentLabel(player: PlanPlayer): string {
  if (player.fixtures.length === 0) {
    return "-";
  }
  return player.fixtures
    .map((fixture) => {
      if (fixture.opponent_team_short_name === null) {
        return "TBD";
      }
      const venue =
        fixture.is_home === null ? "" : fixture.is_home ? " (H)" : " (A)";
      return `${fixture.opponent_team_short_name}${venue}`;
    })
    .join(", ");
}

type RepairOrigin = "saved" | "rejected";

function TransferRepairPanel({
  plan,
  rejection,
  disabled,
  onApply,
}: {
  plan: PlanResponse;
  rejection: PlanSaveSnapshot["rejection"];
  disabled: boolean;
  onApply: (intents: PlanIntent[]) => void;
}): JSX.Element | null {
  const [choices, setChoices] = useState<Record<string, string>>({});
  const acquisitions = (rejection?.intents ?? []).flatMap((intent) => {
    if (
      intent.kind !== "edit_transfer" ||
      intent.incoming_player_id === undefined
    )
      return [];
    const sourceWeek = plan.gameweeks.find((week) =>
      week.decisions.some(
        (decision) =>
          decision.decision_id === intent.decision_id &&
          decision.incoming_player_id !== intent.incoming_player_id,
      ),
    );
    return sourceWeek
      ? [
          {
            decisionId: intent.decision_id,
            playerId: intent.incoming_player_id,
            gameweek: sourceWeek.gameweek_number,
          },
        ]
      : [];
  });
  const diagnosticKey = (error: PlanResponse["decision_errors"][number]) =>
    JSON.stringify([
      error.code,
      error.gameweek_number,
      error.decision_id,
      error.conflicting_gameweek,
      error.player_id,
      error.message,
    ]);
  const savedKeys = new Set(plan.decision_errors.map(diagnosticKey));
  const diagnosticEntries = new Map<
    string,
    { error: PlanResponse["decision_errors"][number]; origin: RepairOrigin }
  >();
  for (const error of rejection?.diagnostics ?? [])
    diagnosticEntries.set(diagnosticKey(error), {
      error,
      origin: savedKeys.has(diagnosticKey(error)) ? "saved" : "rejected",
    });
  for (const error of plan.decision_errors)
    diagnosticEntries.set(diagnosticKey(error), { error, origin: "saved" });
  const diagnostics = [...diagnosticEntries.values()];
  // A decision cited by a saved issue is repaired as saved state, never with rejected intents.
  const decisionOrigin = new Map<string, RepairOrigin>();
  for (const { error, origin } of diagnostics)
    if (error.decision_id && decisionOrigin.get(error.decision_id) !== "saved")
      decisionOrigin.set(error.decision_id, origin);
  const affected = plan.gameweeks.flatMap((week) =>
    week.decisions.flatMap((decision) => {
      const origin = decisionOrigin.get(decision.decision_id);
      return origin ? [{ decision, week, origin }] : [];
    }),
  );
  const repairFor = (
    decision: PlanDecision,
    week: PlanGameweek,
    origin: RepairOrigin,
  ): PlanIntent[] => {
    const choice = choices[decision.decision_id];
    if (choice === "remove")
      return [{ kind: "remove_transfer", decision_id: decision.decision_id }];
    const acquisition = (origin === "rejected" ? acquisitions : []).find(
      (source) =>
        choice === `source:${source.decisionId}` &&
        source.gameweek < week.gameweek_number,
    );
    if (acquisition)
      return [
        {
          kind: "edit_transfer",
          decision_id: decision.decision_id,
          outgoing_player_id: acquisition.playerId,
          outgoing_source_decision_id: acquisition.decisionId,
        },
      ];
    const options = week.players.length
      ? week.players
      : (plan.starting_state?.players ?? []);
    const player = options.find((item) => item.ownership_id === choice);
    return player?.ownership_id
      ? [
          {
            kind: "edit_transfer",
            decision_id: decision.decision_id,
            outgoing_player_id: player.player_id,
            outgoing_ownership_id: player.ownership_id,
          },
        ]
      : [];
  };
  if (!diagnostics.length) return null;
  return (
    <section
      aria-label="Transfer diagnostics"
      className="space-y-3 border-y border-red-200 py-3 text-sm text-red-800"
    >
      {diagnostics.map(({ error, origin }, index) => (
        <p key={`${error.decision_id}-${error.code}-${index}`}>
          {origin === "saved" ? "Saved plan" : "Rejected edit"}
          {" · "}GW{error.gameweek_number}: {error.message}
        </p>
      ))}
      {(
        [
          ["saved", "Saved plan repairs"],
          ["rejected", "Rejected edit repairs"],
        ] as const
      ).map(([origin, label]) => {
        const group = affected.filter((item) => item.origin === origin);
        if (group.length === 0) return null;
        const repairs = group.flatMap(({ decision, week }) =>
          repairFor(decision, week, origin),
        );
        return (
          <fieldset
            key={origin}
            role="group"
            aria-label={label}
            disabled={disabled}
            className="min-w-0 space-y-3"
          >
            {group.map(({ decision, week }) => (
              <label
                key={decision.decision_id}
                className="flex max-w-lg flex-col gap-1"
              >
                GW{week.gameweek_number}: outgoing {decision.outgoing_player_id}{" "}
                → {decision.incoming_player_id}
                <select
                  aria-label={`Repair transfer GW${week.gameweek_number}: ${decision.outgoing_player_id} to ${decision.incoming_player_id}`}
                  value={choices[decision.decision_id] ?? ""}
                  onChange={(event) =>
                    setChoices({
                      ...choices,
                      [decision.decision_id]: event.target.value,
                    })
                  }
                  className="min-w-0 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-slate-900"
                >
                  <option value="">Keep transfer</option>
                  <option value="remove">Remove transfer</option>
                  {(origin === "rejected" ? acquisitions : [])
                    .filter((source) => source.gameweek < week.gameweek_number)
                    .map((source) => (
                      <option
                        key={`source:${source.decisionId}`}
                        value={`source:${source.decisionId}`}
                      >
                        Proposed incoming player {source.playerId} from GW
                        {source.gameweek}
                      </option>
                    ))}
                  {(week.players.length
                    ? week.players
                    : (plan.starting_state?.players ?? [])
                  ).map((player) => (
                    <option
                      key={player.ownership_id ?? player.player_id}
                      value={player.ownership_id ?? ""}
                      disabled={!player.ownership_id}
                    >
                      Replace outgoing with {player.web_name} (
                      {player.player_id})
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <button
              type="button"
              disabled={repairs.length === 0}
              onClick={() =>
                onApply([
                  ...(origin === "rejected" ? (rejection?.intents ?? []) : []),
                  ...repairs,
                ])
              }
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-slate-900 disabled:opacity-40"
            >
              Apply transfer repair
            </button>
          </fieldset>
        );
      })}
    </section>
  );
}

function StartingStatePanel({
  plan,
  coordinator,
  disabled,
  onError,
}: {
  plan: PlanResponse;
  coordinator: PlanSaveCoordinator | null;
  disabled: boolean;
  onError: (message: string | null) => void;
}): JSX.Element | null {
  const boundary = plan.starting_state;
  if (!boundary) return null;
  const start = plan.start_gameweek;

  return (
    <section
      className="space-y-4 border-y border-slate-200 py-4"
      aria-labelledby={`starting-${plan.plan_id}`}
    >
      <h3 id={`starting-${plan.plan_id}`} className="text-base font-semibold">
        Starting state at GW{start}
      </h3>
      <fieldset disabled={disabled} className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-end gap-6 text-sm">
          <div>
            <span className="block text-slate-600">Starting bank</span>
            <span>{(boundary.bank_tenths / 10).toFixed(1)}</span>
          </div>
          {start === 1 ? (
            <p>Free transfers: N/A (unlimited)</p>
          ) : (
            <label className="flex flex-col gap-1 text-slate-700">
              Remaining free transfers
              <input
                type="number"
                aria-label="Starting free transfers"
                min={0}
                max={5}
                step={1}
                key={`ft-${start}-${boundary.free_transfers}`}
                defaultValue={boundary.free_transfers ?? ""}
                className="w-24 rounded-md border border-slate-300 px-2 py-1.5 text-slate-900"
                onBlur={(event) => {
                  const value = Number(event.currentTarget.value);
                  if (
                    !event.currentTarget.value ||
                    !Number.isInteger(value) ||
                    value < 0 ||
                    value > 5
                  ) {
                    onError(
                      "Remaining free transfers must be a whole number from 0 to 5",
                    );
                    return;
                  }
                  onError(null);
                  if (value !== boundary.free_transfers)
                    coordinator?.enqueue([
                      { kind: "set_starting_transfers", value },
                    ]);
                }}
              />
            </label>
          )}
        </div>
        {![1, 20].includes(start) && (
          <fieldset className="min-w-0">
            <legend className="mb-2 text-sm font-medium">
              Chips used before GW{start} ({start < 20 ? "GW1-19" : "GW20-38"})
            </legend>
            <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
              {CHIPS.map((chip) => (
                <label key={chip.value} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={`${chip.label} used before this plan`}
                    checked={boundary.used_chips.includes(chip.value)}
                    onChange={(event) => {
                      onError(null);
                      coordinator?.enqueue([
                        {
                          kind: "set_starting_chip",
                          chip: chip.value,
                          used: event.target.checked,
                        },
                      ]);
                    }}
                  />
                  {chip.label}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        {start === 20 && (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              aria-label="Free Hit used in GW19"
              checked={boundary.free_hit_gameweek_19}
              onChange={(event) => {
                onError(null);
                coordinator?.enqueue([
                  { kind: "set_free_hit_19", used: event.target.checked },
                ]);
              }}
            />
            Free Hit used in GW19
          </label>
        )}
        <ul
          aria-label="Starting purchase prices"
          className="grid gap-x-6 md:grid-cols-2 xl:grid-cols-3"
        >
          {boundary.players.map((player) => (
            <li
              key={player.ownership_id}
              className="min-w-0 space-y-1 border-b border-slate-100 py-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0 text-sm">
                  <span className="break-words font-medium">
                    {player.web_name}
                  </span>
                  <span className="ml-2 text-xs text-slate-600">
                    {player.provenance.basis_kind === "planned_acquisition"
                      ? "Planned acquisition"
                      : player.provenance.confirmation === "assumed"
                        ? "Estimated"
                        : player.provenance.confirmation === "authoritative"
                          ? "Authoritative"
                          : "Confirmed"}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    aria-label={`${player.web_name} purchase price`}
                    min={0.1}
                    step={0.1}
                    key={`${player.ownership_id}-${player.purchase_price_tenths}`}
                    defaultValue={(player.purchase_price_tenths / 10).toFixed(
                      1,
                    )}
                    className="w-20 rounded-md border border-slate-300 px-2 py-1 text-sm"
                    onBlur={(event) => {
                      const match = /^(\d+)(?:\.(\d))?$/.exec(
                        event.currentTarget.value,
                      );
                      const price = match
                        ? Number(match[1]) * 10 + Number(match[2] ?? 0)
                        : NaN;
                      if (!Number.isSafeInteger(price) || price <= 0) {
                        onError(
                          "Purchase price must be positive with at most one decimal place",
                        );
                        return;
                      }
                      onError(null);
                      if (price !== player.purchase_price_tenths)
                        coordinator?.enqueue([
                          {
                            kind: "correct_purchase_price",
                            ownership_id: player.ownership_id,
                            price_tenths: price,
                          },
                        ]);
                    }}
                  />
                  {player.provenance.confirmation === "assumed" && (
                    <button
                      type="button"
                      aria-label={`Confirm ${player.web_name} purchase price`}
                      className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
                      onClick={() => {
                        onError(null);
                        coordinator?.enqueue([
                          {
                            kind: "confirm_purchase_price",
                            ownership_id: player.ownership_id,
                          },
                        ]);
                      }}
                    >
                      Confirm
                    </button>
                  )}
                </div>
              </div>
              <p className="break-all text-xs text-slate-600">
                Original{" "}
                {(player.provenance.original_price_tenths / 10).toFixed(1)} ·{" "}
                {player.provenance.source.replaceAll("_", " ")}
              </p>
            </li>
          ))}
        </ul>
      </fieldset>
    </section>
  );
}

export function PlanBoard({ planId }: { planId: number }): JSX.Element {
  const [state, setState] = useState<LoadState>({ type: "loading" });
  const [selectedGameweek, setSelectedGameweek] = useState<number | null>(null);
  const [coordinator, setCoordinator] = useState<PlanSaveCoordinator | null>(
    null,
  );
  const [actionError, setActionError] = useState<string | null>(null);
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
        setCoordinator(getPlanSaveCoordinator(plan));
        setSelectedGameweek(
          (current) => current ?? plan.gameweeks[0]?.gameweek_number ?? null,
        );
      } catch (error) {
        if (!cancelled) {
          setState({
            type: "error",
            message:
              error instanceof Error ? error.message : "Failed to load plan",
          });
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [planId]);

  const snapshot = useSyncExternalStore(
    coordinator?.subscribe ?? EMPTY_SUBSCRIBE,
    coordinator?.getSnapshot ?? EMPTY_SNAPSHOT,
    EMPTY_SNAPSHOT,
  );
  const plan =
    snapshot?.displayPlan ?? (state.type === "loaded" ? state.plan : null);
  const gameweek: PlanGameweek | null = useMemo(() => {
    if (plan === null || selectedGameweek === null) {
      return null;
    }
    return (
      plan.gameweeks.find(
        (item) => item.gameweek_number === selectedGameweek,
      ) ?? null
    );
  }, [plan, selectedGameweek]);

  useEffect(() => {
    setSwapStarterId(null);
    setTransferOutId(null);
  }, [gameweek]);

  useEffect(() => {
    if (
      plan &&
      !plan.gameweeks.some((week) => week.gameweek_number === selectedGameweek)
    ) {
      setSelectedGameweek(plan.gameweeks[0]?.gameweek_number ?? null);
    }
    if (
      renaming &&
      snapshot?.status === "saved" &&
      snapshot.acknowledged.name === renameValue.trim()
    ) {
      setRenaming(false);
    }
  }, [plan, selectedGameweek, renaming, renameValue, snapshot]);

  function send(intents: PlanIntent[]): void {
    setActionError(null);
    coordinator?.enqueue(intents);
  }

  function handleHorizonChange(
    field: "start_gameweek" | "end_gameweek",
    value: number,
  ): void {
    setActionError(null);
    coordinator?.enqueue([{ kind: "set_horizon_bound", field, value }]);
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
      setActionError(
        error instanceof Error
          ? error.message
          : "Failed to load transfer options",
      );
    }
  }

  function handleTransfer(outgoing: PlanPlayer, incoming: PlayerItem): void {
    if (!gameweek || !outgoing.ownership_id) return;
    const acquisition = gameweek.decisions.find(
      (decision) => decision.decision_id === outgoing.source_decision_id,
    );
    send([
      acquisition
        ? {
            kind: "edit_transfer",
            decision_id: acquisition.decision_id,
            incoming_player_id: incoming.id,
          }
        : {
            kind: "add_transfer",
            gameweek_number: gameweek.gameweek_number,
            outgoing_player_id: outgoing.player_id,
            outgoing_ownership_id: outgoing.ownership_id,
            incoming_player_id: incoming.id,
          },
    ]);
    setTransferOutId(null);
  }

  function handleSwap(starterId: number, benchId: number): void {
    if (!gameweek) return;
    send([
      {
        kind: "swap_lineup_players",
        gameweek_number: gameweek.gameweek_number,
        first_player_id: starterId,
        second_player_id: benchId,
      },
    ]);
    setSwapStarterId(null);
  }

  function handleCaptain(playerId: number, role: "captain" | "vice"): void {
    if (!gameweek) return;
    send([
      {
        kind: role === "captain" ? "change_captain" : "change_vice_captain",
        gameweek_number: gameweek.gameweek_number,
        player_id: playerId,
      },
    ]);
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

  const currentPlan = plan ?? state.plan;
  const draft = gameweek?.players ?? null;
  const draftChip = gameweek?.chip ?? null;
  const editingUnavailable =
    currentPlan.foundation_state !== "ready" ||
    snapshot?.status === "not_saved" ||
    snapshot?.status === "conflict";
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
                    send([{ kind: "rename_plan", name: renameValue.trim() }])
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
                  disabled={editingUnavailable}
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
              Plan xPts: {currentPlan.total_points?.toFixed(1) ?? "Unavailable"}{" "}
              · Hits taken: {currentPlan.total_points_hit ?? "Unavailable"}
            </p>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm text-slate-700">
              From GW
              <input
                type="number"
                aria-label="Plan start gameweek"
                disabled={editingUnavailable}
                min={1}
                max={38}
                className="w-24 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900"
                value={currentPlan.start_gameweek}
                onChange={(event) =>
                  void handleHorizonChange(
                    "start_gameweek",
                    Number(event.target.value),
                  )
                }
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-slate-700">
              To GW
              <input
                type="number"
                aria-label="Plan end gameweek"
                disabled={editingUnavailable}
                min={1}
                max={38}
                className="w-24 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900"
                value={currentPlan.end_gameweek}
                onChange={(event) =>
                  void handleHorizonChange(
                    "end_gameweek",
                    Number(event.target.value),
                  )
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
            <span className="block font-semibold">
              GW {item.gameweek_number}
            </span>
            <span className="block">
              {item.total_points?.toFixed(1) ?? "Unavailable"} xPts
            </span>
            <span className="block">
              {item.unlimited_transfers
                ? "Unlimited"
                : `${item.free_transfers_available ?? "Unavailable"} FT`}
              {item.points_hit !== null && item.points_hit > 0
                ? ` · -${item.points_hit}`
                : ""}
            </span>
            {item.chip && (
              <span className="block font-semibold">{item.chip}</span>
            )}
          </button>
        ))}
      </nav>

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <p role="status">
          {currentPlan.foundation_state !== "ready"
            ? "Initialization required"
            : snapshot?.status === "saving"
              ? "Saving..."
              : snapshot?.status === "not_saved" || snapshot?.status === "error"
                ? "Not saved"
                : snapshot?.status === "conflict"
                  ? "Needs reconciliation"
                  : "Saved"}
        </p>
        {currentPlan.financial_status.provisional && (
          <span className="text-slate-600">Estimated bases</span>
        )}
        {currentPlan.financial_status.requires_resolution && (
          <span className="text-red-700">Requires resolution</span>
        )}
        {snapshot?.status === "not_saved" && (
          <button
            type="button"
            className="rounded-md border px-2 py-1"
            onClick={() => coordinator?.retry()}
          >
            Retry Same Edit
          </button>
        )}
        {snapshot?.status === "conflict" && (
          <button
            type="button"
            className="rounded-md border px-2 py-1"
            onClick={() => void coordinator?.revalidate()}
          >
            Revalidate With Current Data
          </button>
        )}
      </div>
      {(snapshot?.message || actionError) && (
        <p role="alert" className="text-sm text-red-700">
          {snapshot?.message || actionError}
        </p>
      )}
      <TransferRepairPanel
        key={`${currentPlan.revision}-${JSON.stringify(snapshot?.rejection?.intents ?? [])}`}
        plan={currentPlan}
        rejection={snapshot?.rejection ?? null}
        disabled={editingUnavailable || snapshot?.status === "saving"}
        onApply={send}
      />
      {currentPlan.foundation_state !== "ready" && (
        <p className="text-sm text-amber-800">
          {currentPlan.initialization.reason}
        </p>
      )}

      <StartingStatePanel
        plan={currentPlan}
        coordinator={coordinator}
        disabled={editingUnavailable}
        onError={setActionError}
      />

      {gameweek !== null && draft !== null && (
        <fieldset disabled={editingUnavailable} className="min-w-0 space-y-5">
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm text-slate-700">
                <p className="font-semibold text-slate-900">
                  Gameweek {gameweek.gameweek_number}
                </p>
                <p>
                  Bank {gameweek.bank?.toFixed(1) ?? "Unavailable"} · Free
                  transfers{" "}
                  {gameweek.unlimited_transfers
                    ? "unlimited"
                    : (gameweek.accounting?.free_transfers_available ??
                      "Unavailable")}{" "}
                  · Transfers made{" "}
                  {gameweek.accounting?.transfers_made ?? "Unavailable"}
                  {" · Next FT "}
                  {gameweek.accounting?.next_free_transfers ?? "Unavailable"}
                  {" · Hit "}
                  {gameweek.accounting?.points_hit == null
                    ? "Unavailable"
                    : gameweek.accounting.points_hit > 0
                      ? `-${gameweek.accounting.points_hit}`
                      : 0}
                </p>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {CHIPS.map((chip) => {
                const availability = gameweek.chip_availability[chip.value];
                const unavailable =
                  !availability ||
                  !["available", "planned_here"].includes(availability.state);
                const active = draftChip === chip.value;
                return (
                  <div key={chip.value} className="max-w-64">
                    <button
                      type="button"
                      aria-label={chip.label}
                      aria-pressed={active}
                      title={availability?.reason ?? undefined}
                      disabled={unavailable}
                      className={`rounded-md border px-3 py-1.5 text-xs font-medium disabled:opacity-40 ${
                        active
                          ? "border-slate-900 bg-slate-900 text-white"
                          : "border-slate-300 bg-white text-slate-800 hover:bg-slate-50"
                      }`}
                      onClick={() =>
                        send([
                          {
                            kind: active ? "remove_chip" : "activate_chip",
                            gameweek_number: gameweek.gameweek_number,
                            chip: chip.value,
                          },
                        ])
                      }
                    >
                      {chip.label}
                    </button>
                    {availability?.reason && (
                      <p className="mt-1 text-xs text-slate-600">
                        {availability.reason}
                      </p>
                    )}
                    {availability?.state === "planned_elsewhere" &&
                      availability.conflicting_gameweek !== null &&
                      !gameweek.chip && (
                        <button
                          type="button"
                          className="mt-1 text-xs underline"
                          aria-label={`Move ${chip.label} from GW${availability.conflicting_gameweek} to GW${gameweek.gameweek_number}`}
                          onClick={() =>
                            send([
                              {
                                kind: "move_chip",
                                chip: chip.value,
                                source_gameweek:
                                  availability.conflicting_gameweek!,
                                target_gameweek: gameweek.gameweek_number,
                              },
                            ])
                          }
                        >
                          Move Here
                        </button>
                      )}
                  </div>
                );
              })}
            </div>

            {(gameweek.transfers_in.length > 0 ||
              gameweek.transfers_out.length > 0) && (
              <p className="mt-3 text-xs text-slate-600">
                Transfers:{" "}
                {gameweek.transfers_out
                  .map((item) => item.web_name)
                  .join(", ") || "-"}{" "}
                →{" "}
                {gameweek.transfers_in
                  .map((item) => item.web_name)
                  .join(", ") || "-"}
              </p>
            )}
            {gameweek.decisions.map((decision) => (
              <button
                key={decision.decision_id}
                type="button"
                className="mt-2 mr-3 text-xs underline"
                aria-label={`Remove transfer ${decision.outgoing_player_id} to ${decision.incoming_player_id}`}
                onClick={() =>
                  send([
                    {
                      kind: "remove_transfer",
                      decision_id: decision.decision_id,
                    },
                  ])
                }
              >
                Remove Transfer
              </button>
            ))}
          </section>

          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <section>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Starting XI
              </h3>
              <div className="space-y-5">
                {POSITION_ORDER.map((position) => {
                  const rows = starters.filter(
                    (player) => player.position === position,
                  );
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
                              {(player.is_captain ||
                                player.is_vice_captain) && (
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
                                    swapStarterId === player.player_id
                                      ? null
                                      : player.player_id,
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
                                onClick={() =>
                                  handleCaptain(player.player_id, "captain")
                                }
                              >
                                C
                              </button>
                              <button
                                type="button"
                                aria-label={`Make ${player.web_name} vice-captain`}
                                className="rounded-md border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50"
                                onClick={() =>
                                  handleCaptain(player.player_id, "vice")
                                }
                              >
                                VC
                              </button>
                            </div>

                            {swapStarterId === player.player_id && (
                              <ul className="mt-3 space-y-1 text-xs">
                                {bench
                                  .filter((benchPlayer) =>
                                    gameweek.legal_rearrangements.some(
                                      (choice) =>
                                        (choice.first_player_id ===
                                          player.player_id &&
                                          choice.second_player_id ===
                                            benchPlayer.player_id) ||
                                        (choice.second_player_id ===
                                          player.player_id &&
                                          choice.first_player_id ===
                                            benchPlayer.player_id),
                                    ),
                                  )
                                  .map((benchPlayer) => (
                                    <li key={benchPlayer.player_id}>
                                      <button
                                        type="button"
                                        aria-label={`Swap ${player.web_name} for ${benchPlayer.web_name}`}
                                        className="w-full rounded-md border border-slate-200 px-2 py-1 text-left hover:bg-slate-50"
                                        onClick={() =>
                                          handleSwap(
                                            player.player_id,
                                            benchPlayer.player_id,
                                          )
                                        }
                                      >
                                        {benchPlayer.web_name} (
                                        {benchPlayer.position})
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
                                        (selected) =>
                                          selected.player_id === option.id,
                                      ),
                                  )
                                  .map((option) => (
                                    <li key={option.id}>
                                      <button
                                        type="button"
                                        aria-label={`Transfer in ${option.web_name}`}
                                        className="w-full rounded-md border border-slate-200 px-2 py-1 text-left hover:bg-slate-50"
                                        onClick={() =>
                                          handleTransfer(player, option)
                                        }
                                      >
                                        {option.web_name} ·{" "}
                                        {option.team_short_name} ·{" "}
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
                  <article
                    key={player.player_id}
                    className="rounded-lg border border-slate-200 p-3"
                  >
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
          </div>
        </fieldset>
      )}
    </section>
  );
}
