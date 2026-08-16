import { POSITION_ORDER, type Position } from "@/components/team/types";

export function SquadPitch<T>({
  title,
  itemsByPosition,
  keyFor,
  renderCard,
}: {
  title: string;
  itemsByPosition: Map<Position, T[]>;
  keyFor: (item: T) => string | number;
  renderCard: (item: T) => React.ReactNode;
}): JSX.Element {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <div className="space-y-5">
        {POSITION_ORDER.map((position) => {
          const rows = itemsByPosition.get(position) ?? [];
          if (rows.length === 0) {
            return null;
          }

          return (
            <section key={`pitch-${position}`}>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                {position}
              </h4>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
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
