const PLANNER_REASON_LABELS: Record<string, string> = {
  financial_shortfall: "Not enough money in the plan for this swap",
  club_limit: "Would put more than 3 players from one club in the squad",
  sold_this_gameweek:
    "Sold in this gameweek by another planned transfer, so it cannot be bought back",
  squad_positions: "Would break the required squad positions",
  formation: "Would leave no legal starting formation",
  captain: "Would leave the squad without a valid captain",
  vice_captain: "Would leave the squad without a valid vice-captain",
};

/**
 * Plain-language reasons for server-provided Planner unavailable codes. An
 * unrecognised code is shown verbatim rather than hidden or guessed at.
 */
export function describePlannerReasons(codes: string[]): string[] {
  return codes.map((code) => PLANNER_REASON_LABELS[code] ?? code);
}
