import { MyTeamBoard } from "@/components/team/my-team-board";

export default function MyTeamPage(): JSX.Element {
  return (
    <main className="mx-auto min-h-screen max-w-6xl p-6 sm:p-10">
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">My Team</h1>
        <p className="mt-2 max-w-3xl text-slate-700">
          Persisted squad state is the foundation for upcoming projected points, captaincy, and
          transfer explorer work.
        </p>
      </header>
      <MyTeamBoard />
    </main>
  );
}