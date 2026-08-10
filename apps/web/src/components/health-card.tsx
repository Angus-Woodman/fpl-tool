"use client";

import { useEffect, useState } from "react";

type HealthResponse = {
  status: string;
  service: string;
  environment: string;
};

type HealthState =
  | { type: "loading" }
  | { type: "error"; message: string }
  | { type: "loaded"; data: HealthResponse };

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function HealthCard(): JSX.Element {
  const [state, setState] = useState<HealthState>({ type: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    async function fetchHealth(): Promise<void> {
      try {
        const response = await fetch(`${apiBaseUrl}/health`, { signal: controller.signal });
        if (!response.ok) {
          setState({ type: "error", message: `Backend returned ${response.status}` });
          return;
        }

        const data = (await response.json()) as HealthResponse;
        setState({ type: "loaded", data });
      } catch {
        setState({ type: "error", message: "Could not reach backend" });
      }
    }

    void fetchHealth();
    return () => controller.abort();
  }, []);

  return (
    <section className="rounded-lg border border-slate-300 bg-white p-6 shadow-sm">
      <h2 className="text-xl font-semibold">Backend Health</h2>
      {state.type === "loading" && <p className="mt-3 text-slate-600">Loading health status...</p>}
      {state.type === "error" && <p className="mt-3 text-red-700">{state.message}</p>}
      {state.type === "loaded" && (
        <dl className="mt-4 grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
          <div>
            <dt className="font-medium text-slate-500">Status</dt>
            <dd className="text-accent">{state.data.status}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Service</dt>
            <dd>{state.data.service}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Environment</dt>
            <dd>{state.data.environment}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}
