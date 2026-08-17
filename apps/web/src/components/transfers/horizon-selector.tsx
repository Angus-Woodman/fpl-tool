import type { TransferHorizon } from "@/lib/api";

const HORIZONS: TransferHorizon[] = [1, 3, 5];

export function HorizonSelector({
  value,
  onChange,
}: {
  value: TransferHorizon;
  onChange: (horizon: TransferHorizon) => void;
}): JSX.Element {
  return (
    <div
      role="group"
      aria-label="Ranking horizon"
      className="inline-flex overflow-hidden rounded-md border border-slate-300"
    >
      {HORIZONS.map((horizon) => (
        <button
          key={horizon}
          type="button"
          aria-pressed={value === horizon}
          className={`px-3 py-1.5 text-sm font-medium ${
            value === horizon ? "bg-slate-900 text-white" : "bg-white text-slate-700"
          }`}
          onClick={() => onChange(horizon)}
        >
          {horizon} GW{horizon > 1 ? "s" : ""}
        </button>
      ))}
    </div>
  );
}
