export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: React.ReactNode;
}): JSX.Element {
  return (
    <header className="mb-6">
      <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
      {description ? <p className="mt-2 max-w-3xl text-slate-700">{description}</p> : null}
      {children}
    </header>
  );
}
