import { PrimaryNav } from "@/components/layout/primary-nav";

export function AppShell({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <div className="min-h-screen bg-white">
      <PrimaryNav />
      <main className="mx-auto max-w-6xl p-6 sm:p-10">{children}</main>
    </div>
  );
}
