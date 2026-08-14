import { FixtureTicker } from "@/components/fixtures/fixture-ticker";
import { PageHeader } from "@/components/layout/page-header";

export default function FixturesPage(): JSX.Element {
  return (
    <>
      <PageHeader
        title="Fixture Ticker"
        description="A gameweek-by-gameweek grid of every team's fixtures, colour-coded by opponent difficulty to help spot good and bad runs."
      />
      <FixtureTicker />
    </>
  );
}

