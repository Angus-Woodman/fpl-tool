"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import {
  MyTeamResponse,
  TransferExplorerResponse,
  TransferHorizon,
  fetchMyTeam,
  fetchTransferExplorer,
} from "@/lib/api";
import { ProjectionRunBadge } from "@/components/team/projection-run-badge";
import { HorizonSelector } from "@/components/transfers/horizon-selector";
import { OutgoingPlayerSelector } from "@/components/transfers/outgoing-player-selector";
import { ReplacementTable } from "@/components/transfers/replacement-table";

type SquadState =
  | { type: "loading" }
  | { type: "empty" }
  | { type: "error"; message: string }
  | { type: "loaded"; team: MyTeamResponse };

type ExplorerState =
  | { type: "idle" }
  | { type: "loading" }
  | { type: "no_squad" }
  | { type: "player_not_found" }
  | { type: "unavailable"; code: string; message: string; missingPlayerIds: number[] }
  | { type: "error"; message: string }
  | { type: "ready"; data: TransferExplorerResponse };

export function TransferExplorer(): JSX.Element {
  const searchParams = useSearchParams();
  const router = useRouter();
  const outParam = searchParams.get("out");
  const playerOutId = outParam !== null ? Number(outParam) : null;
  const hasValidOutParam = playerOutId !== null && !Number.isNaN(playerOutId);

  const [squadState, setSquadState] = useState<SquadState>({ type: "loading" });
  const [explorerState, setExplorerState] = useState<ExplorerState>({ type: "idle" });
  const [horizon, setHorizon] = useState<TransferHorizon>(5);

  useEffect(() => {
    let cancelled = false;

    async function run(): Promise<void> {
      try {
        const data = await fetchMyTeam();
        if (cancelled) {
          return;
        }
        if (data === null || data.players.length === 0) {
          setSquadState({ type: "empty" });
          return;
        }
        setSquadState({ type: "loaded", team: data });
      } catch (error) {
        if (cancelled) {
          return;
        }
        const message = error instanceof Error ? error.message : "Failed to load your squad";
        setSquadState({ type: "error", message });
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!hasValidOutParam) {
      setExplorerState({ type: "idle" });
      return;
    }

    let cancelled = false;
    setExplorerState({ type: "loading" });

    async function run(): Promise<void> {
      try {
        const result = await fetchTransferExplorer(playerOutId as number, 5);
        if (cancelled) {
          return;
        }

        if (result.type === "ok") {
          setExplorerState({ type: "ready", data: result.data });
        } else if (result.type === "no_squad") {
          setExplorerState({ type: "no_squad" });
        } else if (result.type === "player_not_found") {
          setExplorerState({ type: "player_not_found" });
        } else {
          setExplorerState({
            type: "unavailable",
            code: result.code,
            message: result.message,
            missingPlayerIds: result.missingPlayerIds,
          });
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        const message = error instanceof Error ? error.message : "Failed to load transfer options";
        setExplorerState({ type: "error", message });
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, [hasValidOutParam, playerOutId]);

  function handleSelectOutgoingPlayer(id: number): void {
    router.push(`/transfers?out=${id}`);
  }

  if (squadState.type === "loading") {
    return <p className="text-sm text-slate-600">Loading your squad...</p>;
  }

  if (squadState.type === "error") {
    return <p className="text-sm text-red-700">{squadState.message}</p>;
  }

  if (squadState.type === "empty") {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
        Save a squad on My Team before exploring transfers.
      </p>
    );
  }

  if (!hasValidOutParam) {
    return (
      <OutgoingPlayerSelector
        players={squadState.team.players}
        onSelect={handleSelectOutgoingPlayer}
      />
    );
  }

  if (explorerState.type === "idle" || explorerState.type === "loading") {
    return <p className="text-sm text-slate-600">Loading replacements...</p>;
  }

  if (explorerState.type === "no_squad") {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
        Save a squad on My Team before exploring transfers.
      </p>
    );
  }

  if (explorerState.type === "player_not_found") {
    return <p className="text-sm text-red-700">That player does not exist.</p>;
  }

  if (explorerState.type === "error") {
    return <p className="text-sm text-red-700">{explorerState.message}</p>;
  }

  if (explorerState.type === "unavailable") {
    const message =
      explorerState.code === "player_not_in_squad"
        ? `${explorerState.message}. Choose a player from your current squad instead.`
        : explorerState.code === "no_projection_run"
          ? "Projections need to be refreshed before transfers can be explored."
          : explorerState.message;

    return (
      <div className="space-y-4">
        <p className="text-sm text-red-700">{message}</p>
        <OutgoingPlayerSelector
          players={squadState.team.players}
          onSelect={handleSelectOutgoingPlayer}
        />
      </div>
    );
  }

  const { data } = explorerState;

  return (
    <section className="space-y-5">
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              Replacing {data.outgoing.web_name}
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              {data.outgoing.team_short_name} · {data.outgoing.position} · £
              {data.outgoing.current_price.toFixed(1)}m
            </p>
          </div>
          <ProjectionRunBadge
            modelVersion={data.model_version}
            generatedAt={data.generated_at}
            projectionRunId={data.projection_run_id}
          />
        </div>
        <p className="mt-3 text-sm text-slate-700">
          Bank: £{data.bank.toFixed(1)}m
          {data.selling_price_is_approximate && (
            <span className="text-slate-500"> (selling value approximated as current price)</span>
          )}
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Ranked replacements
        </h3>
        <HorizonSelector value={horizon} onChange={setHorizon} />
      </div>

      <ReplacementTable candidates={data.candidates} horizon={horizon} />
    </section>
  );
}
