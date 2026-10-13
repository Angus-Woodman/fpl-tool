import { Suspense } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { TransferExplorer } from "@/components/transfers/transfer-explorer";

export default function TransfersPage(): JSX.Element {
  return (
    <>
      <PageHeader
        title="Transfers"
        description="Compare replacements for any squad player over 1, 3, and 5 gameweeks, including ones that are currently unavailable to apply."
      />
      <Suspense fallback={<p className="text-sm text-slate-600">Loading...</p>}>
        <TransferExplorer />
      </Suspense>
    </>
  );
}
