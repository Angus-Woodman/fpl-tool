"use client";

import { useSearchParams } from "next/navigation";

export function TransferExplorerPlaceholder(): JSX.Element {
  const searchParams = useSearchParams();
  const outgoingPlayerId = searchParams.get("out");

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm text-slate-600">
        Transfer Explorer is coming soon.
        {outgoingPlayerId ? (
          <>
            {" "}
            Preselected outgoing player: <span className="font-medium">#{outgoingPlayerId}</span>.
          </>
        ) : null}
      </p>
    </section>
  );
}
