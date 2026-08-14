import { HealthCard } from "@/components/health-card";
import { PageHeader } from "@/components/layout/page-header";
import Link from "next/link";

export default function HomePage(): JSX.Element {
  return (
    <>
      <PageHeader
        title="FPL Decision Support"
        description="Phase 0 foundation: a local-first stack with typed API, isolated domain engine, and test-first engineering."
      >
        <div className="mt-4 flex flex-wrap gap-3">
          <Link
            href="/my-team"
            className="inline-block rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-50"
          >
            Open My Team
          </Link>
          <Link
            href="/players"
            className="inline-block rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-50"
          >
            Open Player Browser
          </Link>
          <Link
            href="/fixtures"
            className="inline-block rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-50"
          >
            Open Fixture Ticker
          </Link>
        </div>
      </PageHeader>
      <HealthCard />
    </>
  );
}
