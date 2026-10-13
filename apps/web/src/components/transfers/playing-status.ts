const PLAYING_STATUS_LABELS: Record<string, string> = {
  a: "Available",
  d: "Doubtful",
  i: "Injured",
  s: "Suspended",
  u: "Unavailable",
  n: "Not in squad",
};

const UNKNOWN_STATUS_LABEL = "Status unknown";

export function describePlayingStatus(code: string): string {
  return PLAYING_STATUS_LABELS[code] ?? UNKNOWN_STATUS_LABEL;
}

/** Advisory only: "a" needs no warning, and no status ever affects legality. */
export function playingStatusWarning(code: string): string | null {
  return code === "a" ? null : describePlayingStatus(code);
}
