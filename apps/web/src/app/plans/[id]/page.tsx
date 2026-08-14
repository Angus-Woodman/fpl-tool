import Link from "next/link";

import { PlanBoard } from "@/components/plans/plan-board";

export default async function PlanDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<JSX.Element> {
  const { id } = await params;

  return (
    <>
      <header className="mb-6">
        <Link href="/plans" className="text-sm text-slate-700 underline">
          Back to plans
        </Link>
      </header>
      <PlanBoard planId={Number(id)} />
    </>
  );
}

