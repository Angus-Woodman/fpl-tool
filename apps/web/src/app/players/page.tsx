import { PlayerBrowser } from "@/components/players/player-browser";

export default function PlayersPage(): JSX.Element {
  return (
    <main className="mx-auto min-h-screen max-w-6xl p-6 sm:p-10">
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Player Browser</h1>
        <p className="mt-2 max-w-3xl text-slate-700">
          Search and filter imported Premier League players by team, position, status, and current
          price.
        </p>
      </header>
      <PlayerBrowser />
    </main>
  );
}
