import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { MyTeamPlayerItem, MyTeamRecommendationResponse } from "@/lib/api";
import { RecommendedSquadView } from "@/components/team/recommended-squad-view";

afterEach(() => {
  cleanup();
});

function player(
  id: number,
  webName: string,
  position: MyTeamPlayerItem["position"],
  isStarting: boolean,
): MyTeamPlayerItem {
  return {
    player_id: id,
    web_name: webName,
    first_name: webName,
    second_name: webName,
    team_name: "Team",
    team_short_name: "TMX",
    position,
    current_price: 5.0,
    status: "a",
    is_starting: isStarting,
    bench_order: isStarting ? null : 1,
    is_captain: false,
    is_vice_captain: false,
    projection_totals: null,
    fixture_projections: [
      {
        fixture_id: id * 10,
        gameweek_number: 5,
        projected_points: 0,
        kickoff_time: "2026-09-20T15:00:00+00:00",
        opponent_team_short_name: "CHE",
        is_home: true,
      },
    ],
  };
}

function buildPlayers(): MyTeamPlayerItem[] {
  return [
    player(1, "GK One", "GK", true),
    player(2, "GK Two", "GK", false),
    player(3, "DEF One", "DEF", true),
    player(4, "DEF Two", "DEF", true),
    player(5, "DEF Three", "DEF", true),
    player(6, "DEF Four", "DEF", true),
    player(7, "DEF Five", "DEF", false),
    player(8, "MID One", "MID", true),
    player(9, "MID Two", "MID", true),
    player(10, "MID Three", "MID", true),
    player(11, "MID Four", "MID", false),
    player(12, "MID Five", "MID", true),
    player(13, "FWD One", "FWD", true),
    player(14, "FWD Two", "FWD", true),
    player(15, "FWD Three", "FWD", false),
  ];
}

function buildRecommendation(): MyTeamRecommendationResponse {
  return {
    model_version: "component_v3",
    projection_run_id: 42,
    generated_at: "2026-08-16T08:10:00+00:00",
    target_gameweek_number: 5,
    starting_xi_points: 30.1,
    captain_adjusted_points: 34.6,
    // 12 (currently a starter) drops to the bench; 15 (currently benched) is promoted.
    starting_xi: [1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15],
    bench_goalkeeper: 2,
    bench_outfield: [7, 11, 12],
    captain: 13,
    vice_captain: 14,
    player_projected_points: {
      "1": 3.6,
      "2": 1.8,
      "3": 3.0,
      "4": 2.8,
      "5": 2.5,
      "6": 2.2,
      "7": 1.0,
      "8": 3.5,
      "9": 3.3,
      "10": 2.9,
      "11": 1.5,
      "12": 2.6,
      "13": 4.5,
      "14": 4.0,
      "15": 3.8,
    },
    current_captain_adjusted_points: 32.0,
  };
}

describe("RecommendedSquadView", () => {
  it("marks the recommended captain and vice-captain", () => {
    render(<RecommendedSquadView recommendation={buildRecommendation()} players={buildPlayers()} />);

    const captainCard = screen.getByText("FWD One").closest("article");
    const viceCard = screen.getByText("FWD Two").closest("article");
    expect(captainCard).not.toBeNull();
    expect(viceCard).not.toBeNull();
    expect(captainCard).toHaveTextContent("C");
    expect(viceCard).toHaveTextContent("VC");
  });

  it("renders the bench goalkeeper and the ordered outfield bench", () => {
    render(<RecommendedSquadView recommendation={buildRecommendation()} players={buildPlayers()} />);

    expect(screen.getByText("Goalkeeper")).toBeInTheDocument();
    expect(screen.getByText("GK Two")).toBeInTheDocument();

    const outfieldSection = screen.getByText("Outfield (auto-sub order)").closest("section");
    expect(outfieldSection).not.toBeNull();
    const names = Array.from(outfieldSection!.querySelectorAll("p.text-sm.font-semibold")).map(
      (node) => node.textContent,
    );
    expect(names).toEqual(["DEF Five", "MID Four", "MID Five"]);
  });

  it("flags players whose recommended status differs from their current selection", () => {
    render(<RecommendedSquadView recommendation={buildRecommendation()} players={buildPlayers()} />);

    expect(screen.getByText("MID Five").closest("article")).toHaveTextContent("Now on the bench");
    expect(screen.getByText("FWD Three").closest("article")).toHaveTextContent("Now a starter");
    expect(screen.getByText("FWD One").closest("article")).not.toHaveTextContent("Now a starter");
  });

  it("shows each starter's component_v3 projected points from the recommendation response", () => {
    render(<RecommendedSquadView recommendation={buildRecommendation()} players={buildPlayers()} />);

    expect(screen.getByText("FWD One").closest("article")).toHaveTextContent("GW xPts: 4.5");
  });

  it("links each player card to the Transfer Explorer with their player id", () => {
    render(<RecommendedSquadView recommendation={buildRecommendation()} players={buildPlayers()} />);

    const link = screen.getByText("FWD One").closest("article")?.querySelector("a");
    expect(link).toHaveAttribute("href", "/transfers?out=13");
  });
});
