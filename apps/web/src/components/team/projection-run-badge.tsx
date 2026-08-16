function formatGeneratedAt(generatedAt: string): string {
  const parsed = new Date(generatedAt);
  if (Number.isNaN(parsed.getTime())) {
    return generatedAt;
  }

  const datePart = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" }).format(
    parsed,
  );
  const timePart = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(parsed);

  return `${datePart} ${timePart}`;
}

export function ProjectionRunBadge({
  modelVersion,
  generatedAt,
  projectionRunId,
}: {
  modelVersion: string;
  generatedAt: string;
  projectionRunId: number;
}): JSX.Element {
  return (
    <span
      className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600"
      title={`Projection run #${projectionRunId} (${modelVersion})`}
    >
      {modelVersion} · generated {formatGeneratedAt(generatedAt)}
    </span>
  );
}
