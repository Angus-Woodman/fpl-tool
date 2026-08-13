import { FixtureTicker } from "@/components/fixtures/fixture-ticker";

export default function FixturesPage(): JSX.Element {
  return (
    <main className="mx-auto min-h-screen max-w-6xl p-6 sm:p-10">
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Fixture Ticker</h1>
        <p className="mt-2 max-w-3xl text-slate-700">
          A gameweek-by-gameweek grid of every team&apos;s fixtures, colour-coded by opponent
          difficulty to help spot good and bad runs.
        </p>
      </header>
      <FixtureTicker />
    </main>
  );
}
