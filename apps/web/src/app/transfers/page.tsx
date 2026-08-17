import { Suspense } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { TransferExplorer } from "@/components/transfers/transfer-explorer";

export default function TransfersPage(): JSX.Element {
  return (
    <>
      <PageHeader
        title="Transfers"
        description="Explore legal replacements for any squad player over 1, 3, and 5 gameweeks."
      />
      <Suspense fallback={<p className="text-sm text-slate-600">Loading...</p>}>
        <TransferExplorer />
      </Suspense>
    </>
  );
}
