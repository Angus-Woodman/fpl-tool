import Link from "next/link";

import { PlansList } from "@/components/plans/plans-list";

export default function PlansPage(): JSX.Element {
  return (
    <main className="mx-auto min-h-screen max-w-6xl p-6 sm:p-10">
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Team Plans</h1>
        <p className="mt-2 max-w-3xl text-slate-700">
          Plan your squad across multiple gameweeks, within the transfer and chip rules.
        </p>
        <Link href="/my-team" className="mt-2 inline-block text-sm text-slate-700 underline">
          Back to My Team
        </Link>
      </header>
      <PlansList />
    </main>
  );
}
