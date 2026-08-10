"use client";

import { useEffect, useMemo, useState } from "react";

import { PlayerItem, fetchPlayers } from "@/lib/api";

type SortOption = "web_name" | "price_desc" | "price_asc";
type PositionFilter = "" | "GK" | "DEF" | "MID" | "FWD";

type LoadState =
  | { type: "loading" }
  | { type: "error"; message: string }
  | {
      type: "loaded";
      items: PlayerItem[];
      total: number;
      page: number;
      pageSize: number;
    };

export function PlayerBrowser(): JSX.Element {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [position, setPosition] = useState<PositionFilter>("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState<SortOption>("web_name");
  const [page, setPage] = useState(1);
  const [state, setState] = useState<LoadState>({ type: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function run(): Promise<void> {
      setState({ type: "loading" });
      try {
        const data = await fetchPlayers({
          search: search || undefined,
          position: position || undefined,
          status: status || undefined,
          sort,
          page,
          page_size: 25,
        });

        if (cancelled) {
          return;
        }

        setState({
          type: "loaded",
          items: data.items,
          total: data.total,
          page: data.page,
          pageSize: data.page_size,
        });
      } catch (error) {
        if (cancelled) {
          return;
        }

        const message = error instanceof Error ? error.message : "Failed to load players";
        setState({ type: "error", message });
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, [search, position, status, sort, page]);

  const totalPages = useMemo(() => {
    if (state.type !== "loaded") {
      return 1;
    }
    return Math.max(1, Math.ceil(state.total / state.pageSize));
  }, [state]);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <input
          aria-label="Search players"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          placeholder="Search by name"
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              setPage(1);
              setSearch(searchInput.trim());
            }
          }}
        />
        <button
          className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50"
          onClick={() => {
            setPage(1);
            setSearch(searchInput.trim());
          }}
          type="button"
        >
          Search
        </button>
        <select
          aria-label="Filter by position"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          value={position}
          onChange={(event) => {
            setPage(1);
            setPosition(event.target.value as PositionFilter);
          }}
        >
          <option value="">All Positions</option>
          <option value="GK">Goalkeepers</option>
          <option value="DEF">Defenders</option>
          <option value="MID">Midfielders</option>
          <option value="FWD">Forwards</option>
        </select>
        <input
          aria-label="Filter by status"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          placeholder="Status e.g. a"
          value={status}
          onChange={(event) => {
            setPage(1);
            setStatus(event.target.value.trim());
          }}
        />
        <select
          aria-label="Sort players"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          value={sort}
          onChange={(event) => {
            setPage(1);
            setSort(event.target.value as SortOption);
          }}
        >
          <option value="web_name">Name (A-Z)</option>
          <option value="price_desc">Price (high-low)</option>
          <option value="price_asc">Price (low-high)</option>
        </select>
      </div>

      {state.type === "loading" && <p className="text-sm text-slate-600">Loading players...</p>}
      {state.type === "error" && <p className="text-sm text-red-700">{state.message}</p>}
      {state.type === "loaded" && state.items.length === 0 && (
        <p className="text-sm text-slate-600">No players match your filters.</p>
      )}
      {state.type === "loaded" && state.items.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-slate-600">
                  <th className="px-3 py-2 font-medium">Player</th>
                  <th className="px-3 py-2 font-medium">Team</th>
                  <th className="px-3 py-2 font-medium">Position</th>
                  <th className="px-3 py-2 font-medium">Price</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {state.items.map((item) => (
                  <tr key={item.id} className="border-b border-slate-100">
                    <td className="px-3 py-2 font-medium text-slate-900">{item.web_name}</td>
                    <td className="px-3 py-2 text-slate-700">{item.team_short_name}</td>
                    <td className="px-3 py-2 text-slate-700">{item.position}</td>
                    <td className="px-3 py-2 text-slate-700">{item.current_price.toFixed(1)}</td>
                    <td className="px-3 py-2 text-slate-700">{item.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <p className="text-xs text-slate-600">
              Showing {state.items.length} of {state.total} players
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                className="rounded-md border border-slate-300 px-3 py-1 text-xs disabled:opacity-40"
                disabled={state.page <= 1}
                onClick={() => setPage((value) => Math.max(1, value - 1))}
              >
                Previous
              </button>
              <span className="self-center text-xs text-slate-600">
                Page {state.page} / {totalPages}
              </span>
              <button
                type="button"
                className="rounded-md border border-slate-300 px-3 py-1 text-xs disabled:opacity-40"
                disabled={state.page >= totalPages}
                onClick={() => setPage((value) => value + 1)}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
