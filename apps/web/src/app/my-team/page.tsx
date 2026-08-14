import Link from "next/link";

import { PageHeader } from "@/components/layout/page-header";
import { MyTeamBoard } from "@/components/team/my-team-board";

export default function MyTeamPage(): JSX.Element {
  return (
    <>
      <PageHeader
        title="My Team"
        description="Persisted squad state is the foundation for upcoming projected points, captaincy, and transfer explorer work."
      >
        <Link href="/plans" className="mt-2 inline-block text-sm text-slate-700 underline">
          Team plans
        </Link>
      </PageHeader>
      <MyTeamBoard />
    </>
  );
}
