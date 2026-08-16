import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MyTeamRecommendationResponse } from "@/lib/api";
import { RecommendationSummary, type RecommendationState } from "@/components/team/recommendation-summary";

afterEach(() => {
  cleanup();
});

function buildRecommendation(
  overrides: Partial<MyTeamRecommendationResponse> = {},
): MyTeamRecommendationResponse {
  return {
    model_version: "component_v3",
    projection_run_id: 42,
    generated_at: "2026-08-16T08:10:00+00:00",
    target_gameweek_number: 5,
    starting_xi_points: 55.2,
    captain_adjusted_points: 60.1,
    starting_xi: [1, 3, 4, 5, 8, 9, 10, 12, 13, 14, 15],
    bench_goalkeeper: 2,
    bench_outfield: [6, 7, 11],
    captain: 13,
    vice_captain: 14,
    player_projected_points: {},
    current_captain_adjusted_points: 55.8,
    ...overrides,
  };
}

const noop = (): void => {};

describe("RecommendationSummary", () => {
  it("renders nothing when there is no saved squad", () => {
    const { container } = render(
      <RecommendationSummary
        state={{ type: "no_squad" }}
        viewMode="current"
        onViewModeChange={noop}
        onRefreshProjections={noop}
        refreshing={false}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("shows a loading indicator while the recommendation is being retrieved", () => {
    render(
      <RecommendationSummary
        state={{ type: "loading" }}
        viewMode="current"
        onViewModeChange={noop}
        onRefreshProjections={noop}
        refreshing={false}
      />,
    );

    expect(screen.getByText("Loading recommendation...")).toBeInTheDocument();
  });

  it("renders GW, projection totals, model/run badge, and captain/vice when ready", () => {
    render(
      <RecommendationSummary
        state={{ type: "ready", data: buildRecommendation() }}
        captainName="FWD One"
        viceCaptainName="FWD Two"
        viewMode="current"
        onViewModeChange={noop}
        onRefreshProjections={noop}
        refreshing={false}
      />,
    );

    expect(screen.getByText("GW 5")).toBeInTheDocument();
    expect(screen.getByText(/component_v3 · generated/)).toBeInTheDocument();
    expect(screen.getByText(/component_v3 · generated/)).toHaveAttribute(
      "title",
      "Projection run #42 (component_v3)",
    );
    expect(screen.getByText("55.2")).toBeInTheDocument();
    expect(screen.getByText("60.1")).toBeInTheDocument();
    expect(screen.getByText(/Recommended captain:/)).toBeInTheDocument();
    expect(screen.getByText("FWD One")).toBeInTheDocument();
    expect(screen.getByText("FWD Two")).toBeInTheDocument();
    // captain_adjusted_points (60.1) - current_captain_adjusted_points (55.8) = +4.3
    expect(screen.getByText("+4.3 xPts")).toBeInTheDocument();
  });

  it("shows a structured 422 failure with missing player names and a refresh action", () => {
    const onRefreshProjections = vi.fn();
    render(
      <RecommendationSummary
        state={{
          type: "unavailable",
          code: "missing_player_projections",
          message: "2 squad player(s) have no component_v3 projection in run 42",
          missingPlayerIds: [9, 12],
        }}
        missingPlayerNames={["MID Two", "MID Five"]}
        viewMode="current"
        onViewModeChange={noop}
        onRefreshProjections={onRefreshProjections}
        refreshing={false}
      />,
    );

    expect(
      screen.getByText("2 squad player(s) have no component_v3 projection in run 42"),
    ).toBeInTheDocument();
    expect(screen.getByText("Missing projections for: MID Two, MID Five.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Refresh xPts" }));
    expect(onRefreshProjections).toHaveBeenCalledOnce();
  });

  it("disables the Recommended toggle until a recommendation is ready", () => {
    const onViewModeChange = vi.fn();
    const { rerender } = render(
      <RecommendationSummary
        state={{ type: "loading" }}
        viewMode="current"
        onViewModeChange={onViewModeChange}
        onRefreshProjections={noop}
        refreshing={false}
      />,
    );

    expect(screen.getByRole("button", { name: "Recommended" })).toBeDisabled();

    rerender(
      <RecommendationSummary
        state={{ type: "ready", data: buildRecommendation() }}
        viewMode="current"
        onViewModeChange={onViewModeChange}
        onRefreshProjections={noop}
        refreshing={false}
      />,
    );

    const recommendedButton = screen.getByRole("button", { name: "Recommended" });
    expect(recommendedButton).not.toBeDisabled();
    fireEvent.click(recommendedButton);
    expect(onViewModeChange).toHaveBeenCalledWith("recommended");
  });
});
