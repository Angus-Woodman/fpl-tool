"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { PlannerTransferExplorer } from "@/components/transfers/planner/planner-transfer-explorer";
import { TransferExplorer } from "@/components/transfers/transfer-explorer";
import { parsePlannerExplorerRoute } from "@/lib/planner-explorer-url";

/**
 * Chooses the Explorer mode from the address: a `plan` parameter selects
 * Planner mode (or an explicit invalid-link state), otherwise the existing
 * My Team Explorer renders unchanged.
 */
export function TransferExplorerEntry(): JSX.Element {
  const searchParams = useSearchParams();
  const route = parsePlannerExplorerRoute(searchParams);

  if (route.mode === "my_team") {
    return <TransferExplorer />;
  }
  if (route.mode === "invalid") {
    return (
      <div
        role="alert"
        className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
      >
        <p className="font-medium">Invalid Planner link.</p>
        <p className="mt-1">{route.reason}</p>
        <Link href="/plans" className="mt-2 inline-block font-medium underline">
          Open the Planner
        </Link>
      </div>
    );
  }
  return (
    <PlannerTransferExplorer
      planId={route.planId}
      gameweek={route.gameweek}
      playerOutId={route.playerOutId}
      horizon={route.horizon}
      runId={route.runId}
    />
  );
}
