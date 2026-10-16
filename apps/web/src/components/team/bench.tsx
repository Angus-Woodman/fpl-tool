export function Bench<T>({
  items,
  keyFor,
  renderCard,
}: {
  /** Already in substitute-priority order; rendered exactly in that order. */
  items: T[];
  keyFor: (item: T) => string | number;
  renderCard: (item: T) => React.ReactNode;
}): JSX.Element {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Bench</h3>
      <div className="space-y-3">
        {items.map((item) => (
          <div key={keyFor(item)}>{renderCard(item)}</div>
        ))}
      </div>
    </div>
  );
}
