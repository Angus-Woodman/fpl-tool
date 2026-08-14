import { PageHeader } from "@/components/layout/page-header";
import { PlayerBrowser } from "@/components/players/player-browser";

export default function PlayersPage(): JSX.Element {
  return (
    <>
      <PageHeader
        title="Player Browser"
        description="Search and filter imported Premier League players by team, position, status, and current price."
      />
      <PlayerBrowser />
    </>
  );
}

