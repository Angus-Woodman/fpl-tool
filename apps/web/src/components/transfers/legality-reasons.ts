const LEGALITY_REASON_TEXT: Record<string, string> = {
  insufficient_bank: "Insufficient budget",
  club_limit_exceeded: "You already have 3 players from that club",
  invalid_position_composition: "This would break the squad composition rules",
};

const GENERIC_REASON_TEXT = "This transfer breaks a squad rule";

export function describeLegalityReason(code: string): string {
  return LEGALITY_REASON_TEXT[code] ?? GENERIC_REASON_TEXT;
}

/** De-duplicates so several unknown codes read as one generic reason. */
export function describeLegalityReasons(codes: readonly string[]): string[] {
  return Array.from(new Set(codes.map(describeLegalityReason)));
}
