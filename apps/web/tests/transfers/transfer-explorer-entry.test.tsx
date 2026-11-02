import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TransferExplorerEntry } from "@/components/transfers/transfer-explorer-entry";

const { useSearchParams } = vi.hoisted(() => ({ useSearchParams: vi.fn() }));

vi.mock("next/navigation", () => ({ useSearchParams }));
vi.mock("@/components/transfers/transfer-explorer", () => ({
  TransferExplorer: () => <p>My Team explorer</p>,
}));
vi.mock("@/components/transfers/planner/planner-transfer-explorer", () => ({
  PlannerTransferExplorer: (props: Record<string, unknown>) => (
    <p data-testid="planner-explorer">{JSON.stringify(props)}</p>
  ),
}));

afterEach(() => {
  cleanup();
  useSearchParams.mockReset();
});

function renderAt(query: string) {
  useSearchParams.mockReturnValue(new URLSearchParams(query));
  return render(<TransferExplorerEntry />);
}

describe("TransferExplorerEntry", () => {
  it("renders the existing My Team explorer when there is no plan parameter", () => {
    renderAt("");
    expect(screen.getByText("My Team explorer")).toBeInTheDocument();
    expect(screen.queryByTestId("planner-explorer")).not.toBeInTheDocument();
  });

  it("keeps My Team mode for a My Team address with other parameters", () => {
    renderAt("out=9&h=3");
    expect(screen.getByText("My Team explorer")).toBeInTheDocument();
  });

  it("renders Planner mode with parsed parameters when plan and gameweek are present", () => {
    renderAt("plan=7&gw=9&out=6&h=3&run=42");

    expect(screen.queryByText("My Team explorer")).not.toBeInTheDocument();
    expect(
      JSON.parse(screen.getByTestId("planner-explorer").textContent ?? "{}"),
    ).toEqual({
      planId: 7,
      gameweek: 9,
      playerOutId: 6,
      horizon: 3,
      runId: 42,
    });
  });

  it("renders Planner mode without an outgoing player", () => {
    renderAt("plan=7&gw=9");
    expect(
      JSON.parse(screen.getByTestId("planner-explorer").textContent ?? "{}"),
    ).toMatchObject({ planId: 7, gameweek: 9, playerOutId: null, horizon: 5 });
  });

  it.each(["plan=abc&gw=9", "plan=7", "plan=7&gw=9&out=x", "plan=7&gw=9&h=2"])(
    "shows an invalid link for %s and never falls back to My Team",
    (query) => {
      renderAt(query);

      expect(screen.getByRole("alert")).toHaveTextContent(
        /invalid planner link/i,
      );
      expect(screen.queryByText("My Team explorer")).not.toBeInTheDocument();
      expect(screen.queryByTestId("planner-explorer")).not.toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /open the planner/i }),
      ).toHaveAttribute("href", "/plans");
    },
  );
});
