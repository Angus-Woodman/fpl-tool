import Link from "next/link";

import { PageHeader } from "@/components/layout/page-header";
import { PlansList } from "@/components/plans/plans-list";

export default function PlansPage(): JSX.Element {
  return (
    <>
      <PageHeader
        title="Team Plans"
        description="Plan your squad across multiple gameweeks, within the transfer and chip rules."
      >
        <Link href="/my-team" className="mt-2 inline-block text-sm text-slate-700 underline">
          Back to My Team
        </Link>
      </PageHeader>
      <PlansList />
    </>
  );
}

