import { HealthCard } from "@/components/health-card";
import Link from "next/link";

export default function HomePage(): JSX.Element {
  return (
    <main className="mx-auto min-h-screen max-w-5xl p-6 sm:p-10">
      <header className="mb-10">
        <h1 className="text-4xl font-bold tracking-tight">
          FPL Decision Support
        </h1>
        <p className="mt-2 max-w-2xl text-slate-700">
          Phase 0 foundation: a local-first stack with typed API, isolated
          domain engine, and test-first engineering.
        </p>
        <Link
          href="/players"
          className="mt-4 inline-block rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-50"
        >
          Open Player Browser
        </Link>
      </header>
      <HealthCard />
    </main>
  );
}
