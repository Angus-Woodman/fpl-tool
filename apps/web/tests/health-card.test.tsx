import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HealthCard } from "@/components/health-card";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("HealthCard", () => {
  it("renders backend status on success", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        status: "ok",
        service: "api",
        environment: "test"
      })
    } as Response);

    render(<HealthCard />);

    await waitFor(() => {
      expect(screen.getByText("ok")).toBeInTheDocument();
      expect(screen.getByText("api")).toBeInTheDocument();
    });
  });

  it("renders error message when backend is unavailable", async () => {
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("network"));

    render(<HealthCard />);

    await waitFor(() => {
      expect(screen.getByText("Could not reach backend")).toBeInTheDocument();
    });
  });
});
