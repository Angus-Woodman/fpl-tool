"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  PlanRuleError,
  PlanSummary,
  createPlan,
  deletePlan,
  fetchPlans,
  updatePlan,
} from "@/lib/api";

type LoadState =
  | { type: "loading" }
  | { type: "error"; message: string }
  | { type: "loaded"; plans: PlanSummary[] };

const DEFAULT_START_GAMEWEEK = 1;
const DEFAULT_END_GAMEWEEK = 8;

export function PlansList(): JSX.Element {
  const [state, setState] = useState<LoadState>({ type: "loading" });
  const [name, setName] = useState("");
  const [startGameweek, setStartGameweek] = useState(DEFAULT_START_GAMEWEEK);
  const [endGameweek, setEndGameweek] = useState(DEFAULT_END_GAMEWEEK);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");

  async function load(): Promise<void> {
    try {
      const response = await fetchPlans();
      setState({ type: "loaded", plans: response.plans });
    } catch (error) {
      setState({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to load plans",
      });
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function run(action: () => Promise<unknown>): Promise<void> {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      await load();
    } catch (error) {
      setActionError(
        error instanceof PlanRuleError || error instanceof Error
          ? error.message
          : "Something went wrong",
      );
    } finally {
      setBusy(false);
    }
  }

  if (state.type === "loading") {
    return <p className="text-sm text-slate-600">Loading plans...</p>;
  }

  if (state.type === "error") {
    return <p className="text-sm text-red-700">{state.message}</p>;
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold">New plan</h2>
        <p className="mt-1 text-sm text-slate-600">
          A plan starts from your saved team and lets you work gameweek by gameweek.
        </p>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm text-slate-700">
            Plan name
            <input
              type="text"
              aria-label="Plan name"
              className="w-64 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900"
              placeholder="No Haaland GW1"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-700">
            From GW
            <input
              type="number"
              aria-label="Start gameweek"
              min={1}
              max={38}
              className="w-24 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900"
              value={startGameweek}
              onChange={(event) => setStartGameweek(Number(event.target.value))}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-700">
            To GW
            <input
              type="number"
              aria-label="End gameweek"
              min={1}
              max={38}
              className="w-24 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900"
              value={endGameweek}
              onChange={(event) => setEndGameweek(Number(event.target.value))}
            />
          </label>
          <button
            type="button"
            className="rounded-md border border-slate-300 bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            disabled={busy || name.trim().length === 0}
            onClick={() =>
              void run(async () => {
                await createPlan({
                  name: name.trim(),
                  start_gameweek: startGameweek,
                  end_gameweek: endGameweek,
                });
                setName("");
              })
            }
          >
            Create Plan
          </button>
        </div>
        {actionError && <p className="mt-3 text-sm text-red-700">{actionError}</p>}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold">Your plans</h2>
        {state.plans.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600">No plans yet.</p>
        ) : (
          <ul className="mt-4 space-y-3">
            {state.plans.map((plan) => (
              <li
                key={plan.plan_id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 p-3"
              >
                {renamingId === plan.plan_id ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      type="text"
                      aria-label={`Rename ${plan.name}`}
                      className="w-64 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900"
                      value={renameValue}
                      onChange={(event) => setRenameValue(event.target.value)}
                    />
                    <button
                      type="button"
                      className="rounded-md border border-emerald-300 bg-emerald-600 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                      disabled={busy || renameValue.trim().length === 0}
                      onClick={() =>
                        void run(async () => {
                          await updatePlan(plan.plan_id, { name: renameValue.trim() });
                          setRenamingId(null);
                        })
                      }
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-800 hover:bg-slate-50"
                      onClick={() => setRenamingId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div>
                    <Link
                      href={`/plans/${plan.plan_id}`}
                      className="text-sm font-semibold text-slate-900 underline"
                    >
                      {plan.name}
                    </Link>
                    <p className="text-xs text-slate-600">
                      GW {plan.start_gameweek} - GW {plan.end_gameweek}
                    </p>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    aria-label={`Rename ${plan.name}`}
                    className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-800 hover:bg-slate-50"
                    onClick={() => {
                      setRenamingId(plan.plan_id);
                      setRenameValue(plan.name);
                    }}
                  >
                    Rename
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${plan.name}`}
                    className="rounded-md border border-red-300 bg-white px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                    disabled={busy}
                    onClick={() => void run(() => deletePlan(plan.plan_id))}
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
