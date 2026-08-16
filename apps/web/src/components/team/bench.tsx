import { POSITION_ORDER, type Position } from "@/components/team/types";

export function Bench<T>({
  itemsByPosition,
  keyFor,
  renderCard,
}: {
  itemsByPosition: Map<Position, T[]>;
  keyFor: (item: T) => string | number;
  renderCard: (item: T) => React.ReactNode;
}): JSX.Element {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Bench</h3>
      <div className="space-y-5">
        {POSITION_ORDER.map((position) => {
          const rows = itemsByPosition.get(position) ?? [];
          if (rows.length === 0) {
            return null;
          }

          return (
            <section key={`bench-${position}`}>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                {position}
              </h4>
              <div className="space-y-3">
                {rows.map((row) => (
                  <div key={keyFor(row)}>{renderCard(row)}</div>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
