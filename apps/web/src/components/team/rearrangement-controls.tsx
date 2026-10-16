import { noTargetsMessage } from "@/lib/squad-rearrangement";

export function SwapAnnouncement({
  message,
}: {
  message: string;
}): JSX.Element {
  return (
    <p
      aria-live="polite"
      data-testid="swap-confirmation"
      className={message ? "mb-4 text-sm text-emerald-700" : "sr-only"}
    >
      {message}
    </p>
  );
}

export function ClearSelectionButton({
  onClick,
  disabled,
}: {
  onClick: () => void;
  disabled?: boolean;
}): JSX.Element {
  return (
    <button
      type="button"
      className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
      onClick={onClick}
      disabled={disabled}
    >
      Clear selection
    </button>
  );
}

export function NoTargetsNotice({ name }: { name: string }): JSX.Element {
  return (
    <p className="mb-4 text-sm text-slate-700">{noTargetsMessage(name)}</p>
  );
}
