import type { MyTeamPlayerItem } from "@/lib/api";

export function pointsForGameweek(player: MyTeamPlayerItem, gameweek: number): number {
  return player.fixture_projections
    .filter((fixture) => fixture.gameweek_number === gameweek)
    .reduce((sum, fixture) => sum + fixture.projected_points, 0);
}

export function opponentLabelForGameweek(player: MyTeamPlayerItem, gameweek: number): string {
  const fixtures = player.fixture_projections
    .filter((fixture) => fixture.gameweek_number === gameweek)
    .map((fixture) => {
      if (fixture.opponent_team_short_name === null) {
        return "TBD";
      }
      if (fixture.is_home === true) {
        return `${fixture.opponent_team_short_name} (H)`;
      }
      if (fixture.is_home === false) {
        return `${fixture.opponent_team_short_name} (A)`;
      }
      return fixture.opponent_team_short_name;
    });

  if (fixtures.length === 0) {
    return "-";
  }

  return fixtures.join(", ");
}
