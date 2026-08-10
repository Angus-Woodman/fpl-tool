import { HealthCard } from "@/components/health-card";

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
      </header>
      <HealthCard />
    </main>
  );
}
