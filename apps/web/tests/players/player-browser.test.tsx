import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PlayerBrowser } from "@/components/players/player-browser";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function mockPlayersResponse(payload: unknown): void {
  vi.spyOn(global, "fetch").mockResolvedValue({
    ok: true,
    json: async () => payload,
  } as Response);
}

describe("PlayerBrowser", () => {
  it("renders players table when data loads", async () => {
    mockPlayersResponse({
      items: [
        {
          id: 1,
          web_name: "Saka",
          first_name: "Bukayo",
          second_name: "Saka",
          team_name: "Arsenal",
          team_short_name: "ARS",
          position: "MID",
          current_price: 10.5,
          status: "a",
        },
      ],
      total: 1,
      page: 1,
      page_size: 25,
    });

    render(<PlayerBrowser />);

    await waitFor(() => {
      expect(screen.getByText("Saka")).toBeInTheDocument();
      expect(screen.getByText("Showing 1 of 1 players")).toBeInTheDocument();
    });
  });

  it("renders empty state", async () => {
    mockPlayersResponse({
      items: [],
      total: 0,
      page: 1,
      page_size: 25,
    });

    render(<PlayerBrowser />);

    await waitFor(() => {
      expect(screen.getByText("No players match your filters.")).toBeInTheDocument();
    });
  });

  it("renders error state when fetch fails", async () => {
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("network"));

    render(<PlayerBrowser />);

    await waitFor(() => {
      expect(screen.getByText("network")).toBeInTheDocument();
    });
  });

  it("triggers fetch with updated search and position", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, page: 1, page_size: 25 }),
    } as Response);

    render(<PlayerBrowser />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    fireEvent.change(screen.getByLabelText("Search players"), {
      target: { value: "sak" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    fireEvent.change(screen.getByLabelText("Filter by position"), {
      target: { value: "MID" },
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    const lastUrl = String(fetchMock.mock.calls.at(-1)?.[0] ?? "");
    expect(lastUrl).toContain("search=sak");
    expect(lastUrl).toContain("position=MID");
  });
});
