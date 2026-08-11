import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FixtureTicker } from "@/components/fixtures/fixture-ticker";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("FixtureTicker", () => {
  it("renders loaded fixture rows", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return {
          ok: true,
          json: async () => ({
            items: [{ id: 1, name: "Arsenal", short_name: "ARS" }],
            total: 1,
          }),
        } as Response;
      }

      if (url.endsWith("/gameweeks")) {
        return {
          ok: true,
          json: async () => ({
            items: [
              {
                id: 1,
                number: 1,
                name: "Gameweek 1",
                is_current: true,
                is_next: false,
                is_finished: false,
              },
            ],
            total: 1,
          }),
        } as Response;
      }

      return {
        ok: true,
        json: async () => ({
          items: [
            {
              fixture_id: 1,
              gameweek_number: 2,
              kickoff_time: "2026-08-21T18:30:00+00:00",
              home_team_short_name: "ARS",
              away_team_short_name: "AVL",
              finished: false,
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        }),
      } as Response;
    });

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("ARS vs AVL")).toBeInTheDocument();
      expect(screen.getByText("Showing 1 of 1 fixtures")).toBeInTheDocument();
    });

    expect(fetchSpy).toHaveBeenCalledWith("http://127.0.0.1:8000/teams");
    expect(fetchSpy).toHaveBeenCalledWith("http://127.0.0.1:8000/gameweeks");
    expect(fetchSpy).toHaveBeenCalledWith("http://127.0.0.1:8000/fixtures/ticker?page=1&limit=20&gameweek=1");
  });

  it("applies filters and refetches ticker", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return {
          ok: true,
          json: async () => ({
            items: [
              { id: 1, name: "Arsenal", short_name: "ARS" },
              { id: 2, name: "Aston Villa", short_name: "AVL" },
            ],
            total: 2,
          }),
        } as Response;
      }

      if (url.endsWith("/gameweeks")) {
        return {
          ok: true,
          json: async () => ({
            items: [
              {
                id: 1,
                number: 1,
                name: "Gameweek 1",
                is_current: true,
                is_next: false,
                is_finished: false,
              },
              {
                id: 2,
                number: 2,
                name: "Gameweek 2",
                is_current: false,
                is_next: true,
                is_finished: false,
              },
            ],
            total: 2,
          }),
        } as Response;
      }

      return {
        ok: true,
        json: async () => ({
          items: [],
          total: 4,
          page: 1,
          page_size: 20,
        }),
      } as Response;
    });

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(3);
    });

    expect(fetchSpy).toHaveBeenLastCalledWith("http://127.0.0.1:8000/fixtures/ticker?page=1&limit=20&gameweek=2");

    fireEvent.change(screen.getByLabelText("Fixture limit"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Filter by team"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Filter by gameweek"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenLastCalledWith(
        "http://127.0.0.1:8000/fixtures/ticker?page=1&limit=5&team_id=2&gameweek=2"
      );
    });

    expect(screen.getByRole("button", { name: "Limit: 5 x" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Team: AVL x" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "GW: 2 x" })).not.toBeInTheDocument();
  });

  it("clears all applied filters via chip action", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return {
          ok: true,
          json: async () => ({
            items: [{ id: 2, name: "Aston Villa", short_name: "AVL" }],
            total: 1,
          }),
        } as Response;
      }

      if (url.endsWith("/gameweeks")) {
        return {
          ok: true,
          json: async () => ({
            items: [
              {
                id: 2,
                number: 2,
                name: "Gameweek 2",
                is_current: false,
                is_next: true,
                is_finished: false,
              },
            ],
            total: 1,
          }),
        } as Response;
      }

      return {
        ok: true,
        json: async () => ({
          items: [],
          total: 4,
          page: 1,
          page_size: 20,
        }),
      } as Response;
    });

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(3);
    });

    expect(fetchSpy).toHaveBeenLastCalledWith("http://127.0.0.1:8000/fixtures/ticker?page=1&limit=20&gameweek=2");

    fireEvent.change(screen.getByLabelText("Fixture limit"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Filter by team"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Filter by gameweek"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenLastCalledWith(
        "http://127.0.0.1:8000/fixtures/ticker?page=1&limit=5&team_id=2&gameweek=2"
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Clear all" }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenLastCalledWith("http://127.0.0.1:8000/fixtures/ticker?page=1&limit=20&gameweek=2");
    });
  });

  it("resets filters to next gameweek baseline", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return {
          ok: true,
          json: async () => ({
            items: [{ id: 2, name: "Aston Villa", short_name: "AVL" }],
            total: 1,
          }),
        } as Response;
      }

      if (url.endsWith("/gameweeks")) {
        return {
          ok: true,
          json: async () => ({
            items: [
              {
                id: 1,
                number: 1,
                name: "Gameweek 1",
                is_current: true,
                is_next: false,
                is_finished: false,
              },
              {
                id: 2,
                number: 2,
                name: "Gameweek 2",
                is_current: false,
                is_next: true,
                is_finished: false,
              },
            ],
            total: 2,
          }),
        } as Response;
      }

      return {
        ok: true,
        json: async () => ({
          items: [],
          total: 4,
          page: 1,
          page_size: 20,
        }),
      } as Response;
    });

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenLastCalledWith("http://127.0.0.1:8000/fixtures/ticker?page=1&limit=20&gameweek=2");
    });

    fireEvent.change(screen.getByLabelText("Filter by gameweek"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenLastCalledWith("http://127.0.0.1:8000/fixtures/ticker?page=1&limit=20&gameweek=1");
    });

    fireEvent.click(screen.getByRole("button", { name: "Reset to next GW" }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenLastCalledWith("http://127.0.0.1:8000/fixtures/ticker?page=1&limit=20&gameweek=2");
    });
  });

  it("navigates to next fixture ticker page", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return {
          ok: true,
          json: async () => ({
            items: [],
            total: 0,
          }),
        } as Response;
      }

      if (url.endsWith("/gameweeks")) {
        return {
          ok: true,
          json: async () => ({
            items: [],
            total: 0,
          }),
        } as Response;
      }

      return {
        ok: true,
        json: async () => ({
          items: [
            {
              fixture_id: 1,
              gameweek_number: 2,
              kickoff_time: "2026-08-21T18:30:00+00:00",
              home_team_short_name: "ARS",
              away_team_short_name: "AVL",
              finished: false,
            },
          ],
          total: 40,
          page: url.includes("page=2") ? 2 : 1,
          page_size: 20,
        }),
      } as Response;
    });

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenLastCalledWith("http://127.0.0.1:8000/fixtures/ticker?page=2&limit=20");
      expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    });
  });

  it("renders empty state", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return {
          ok: true,
          json: async () => ({
            items: [],
            total: 0,
          }),
        } as Response;
      }

      if (url.endsWith("/gameweeks")) {
        return {
          ok: true,
          json: async () => ({
            items: [],
            total: 0,
          }),
        } as Response;
      }

      return {
        ok: true,
        json: async () => ({
          items: [],
          total: 4,
          page: 1,
          page_size: 20,
        }),
      } as Response;
    });

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("No upcoming fixtures found.")).toBeInTheDocument();
    });
  });

  it("renders error state", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return {
          ok: true,
          json: async () => ({
            items: [],
            total: 0,
          }),
        } as Response;
      }

      if (url.endsWith("/gameweeks")) {
        return {
          ok: true,
          json: async () => ({
            items: [],
            total: 0,
          }),
        } as Response;
      }

      throw new Error("fixtures unavailable");
    });

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("fixtures unavailable")).toBeInTheDocument();
    });
  });

  it("shows teams load warning when teams request fails", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        throw new Error("teams unavailable");
      }

      if (url.endsWith("/gameweeks")) {
        return {
          ok: true,
          json: async () => ({
            items: [],
            total: 0,
          }),
        } as Response;
      }

      return {
        ok: true,
        json: async () => ({
          items: [],
          total: 4,
          page: 1,
          page_size: 20,
        }),
      } as Response;
    });

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("teams unavailable")).toBeInTheDocument();
    });
  });

  it("shows gameweeks load warning when gameweeks request fails", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/teams")) {
        return {
          ok: true,
          json: async () => ({
            items: [],
            total: 0,
          }),
        } as Response;
      }

      if (url.endsWith("/gameweeks")) {
        throw new Error("gameweeks unavailable");
      }

      return {
        ok: true,
        json: async () => ({
          items: [],
          total: 4,
          page: 1,
          page_size: 20,
        }),
      } as Response;
    });

    render(<FixtureTicker />);

    await waitFor(() => {
      expect(screen.getByText("gameweeks unavailable")).toBeInTheDocument();
    });
  });
});
