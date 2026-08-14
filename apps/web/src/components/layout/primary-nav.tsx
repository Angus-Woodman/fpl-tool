"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavDestination = {
  href: string;
  label: string;
};

const DESTINATIONS: NavDestination[] = [
  { href: "/my-team", label: "My Team" },
  { href: "/transfers", label: "Transfers" },
  { href: "/plans", label: "Planner" },
  { href: "/fixtures", label: "Fixtures" },
  { href: "/players", label: "Players" },
];

function isActiveDestination(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function PrimaryNav(): JSX.Element {
  const pathname = usePathname();

  return (
    <nav aria-label="Primary" className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center gap-1 overflow-x-auto px-4 py-3 sm:px-10">
        <Link
          href="/"
          className="mr-4 shrink-0 text-lg font-bold tracking-tight text-slate-900"
        >
          FPL Tool
        </Link>
        {DESTINATIONS.map((destination) => {
          const active = isActiveDestination(pathname, destination.href);
          return (
            <Link
              key={destination.href}
              href={destination.href}
              aria-current={active ? "page" : undefined}
              className={`shrink-0 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? "bg-slate-900 text-white"
                  : "text-slate-700 hover:bg-slate-100"
              }`}
            >
              {destination.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
