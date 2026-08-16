import type { MyTeamPlayerItem, MyTeamRecommendationResponse } from "@/lib/api";
import { opponentLabelForGameweek } from "@/components/team/projection-helpers";
import { SquadPitch } from "@/components/team/squad-pitch";
import { SquadPlayerCard } from "@/components/team/squad-player-card";
import { POSITION_ORDER, type Position } from "@/components/team/types";

function projectedPointsFor(
  recommendation: MyTeamRecommendationResponse,
  playerId: number,
): number | null {
  const value = recommendation.player_projected_points[String(playerId)];
  return value === undefined ? null : value;
}

function changeTag(
  player: MyTeamPlayerItem,
  isRecommendedStarter: boolean,
): "promoted" | "dropped" | null {
  if (isRecommendedStarter && !player.is_starting) {
    return "promoted";
  }
  if (!isRecommendedStarter && player.is_starting) {
    return "dropped";
  }
  return null;
}

export function RecommendedSquadView({
  recommendation,
  players,
}: {
  recommendation: MyTeamRecommendationResponse;
  players: MyTeamPlayerItem[];
}): JSX.Element {
  const playersById = new Map(players.map((player) => [player.player_id, player]));
  const gameweek = recommendation.target_gameweek_number;

  function badgeFor(playerId: number): "C" | "VC" | null {
    if (playerId === recommendation.captain) {
      return "C";
    }
    if (playerId === recommendation.vice_captain) {
      return "VC";
    }
    return null;
  }

  function renderCard(player: MyTeamPlayerItem, isRecommendedStarter: boolean, benchOrder?: number) {
    return (
      <SquadPlayerCard
        webName={player.web_name}
        teamShortName={player.team_short_name}
        position={player.position}
        projectedPoints={projectedPointsFor(recommendation, player.player_id)}
        opponentLabel={opponentLabelForGameweek(player, gameweek)}
        badge={badgeFor(player.player_id)}
        benchOrder={benchOrder}
        changeTag={changeTag(player, isRecommendedStarter)}
        transferHref={`/transfers?out=${player.player_id}`}
      />
    );
  }

  const starterRows = recommendation.starting_xi
    .map((playerId) => playersById.get(playerId))
    .filter((player): player is MyTeamPlayerItem => player !== undefined);

  const startersByPosition = new Map<Position, MyTeamPlayerItem[]>();
  for (const position of POSITION_ORDER) {
    startersByPosition.set(
      position,
      starterRows.filter((player) => player.position === position),
    );
  }

  const benchGoalkeeper = playersById.get(recommendation.bench_goalkeeper);
  const benchOutfieldRows = recommendation.bench_outfield
    .map((playerId) => playersById.get(playerId))
    .filter((player): player is MyTeamPlayerItem => player !== undefined);

  return (
    <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
      <SquadPitch
        title="Recommended Starting XI"
        itemsByPosition={startersByPosition}
        keyFor={(player) => player.player_id}
        renderCard={(player) => renderCard(player, true)}
      />

      <div>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Recommended Bench
        </h3>
        <div className="space-y-5">
          {benchGoalkeeper && (
            <section>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Goalkeeper
              </h4>
              <div className="space-y-3">{renderCard(benchGoalkeeper, false)}</div>
            </section>
          )}

          <section>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Outfield (auto-sub order)
            </h4>
            <div className="space-y-3">
              {benchOutfieldRows.map((player, index) => (
                <div key={player.player_id}>{renderCard(player, false, index + 1)}</div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
