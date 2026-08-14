import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PrimaryNav } from "@/components/layout/primary-nav";

const { usePathname } = vi.hoisted(() => ({
  usePathname: vi.fn(() => "/"),
}));

vi.mock("next/navigation", () => ({
  usePathname,
}));

describe("PrimaryNav", () => {
  it("renders every primary destination", () => {
    usePathname.mockReturnValue("/");

    render(<PrimaryNav />);

    expect(screen.getByRole("link", { name: "My Team" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Transfers" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Planner" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fixtures" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Players" })).toBeInTheDocument();
  });

  it("links to the expected routes", () => {
    usePathname.mockReturnValue("/");

    render(<PrimaryNav />);

    expect(screen.getByRole("link", { name: "My Team" })).toHaveAttribute("href", "/my-team");
    expect(screen.getByRole("link", { name: "Transfers" })).toHaveAttribute("href", "/transfers");
    expect(screen.getByRole("link", { name: "Planner" })).toHaveAttribute("href", "/plans");
    expect(screen.getByRole("link", { name: "Fixtures" })).toHaveAttribute("href", "/fixtures");
    expect(screen.getByRole("link", { name: "Players" })).toHaveAttribute("href", "/players");
  });

  it("marks the current route as active via aria-current", () => {
    usePathname.mockReturnValue("/my-team");

    render(<PrimaryNav />);

    expect(screen.getByRole("link", { name: "My Team" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Transfers" })).not.toHaveAttribute("aria-current");
  });

  it("treats nested routes as active for their top-level destination", () => {
    usePathname.mockReturnValue("/plans/42");

    render(<PrimaryNav />);

    expect(screen.getByRole("link", { name: "Planner" })).toHaveAttribute("aria-current", "page");
  });

  it("does not mark any destination active on an unrelated route", () => {
    usePathname.mockReturnValue("/");

    render(<PrimaryNav />);

    for (const label of ["My Team", "Transfers", "Planner", "Fixtures", "Players"]) {
      expect(screen.getByRole("link", { name: label })).not.toHaveAttribute("aria-current");
    }
  });

  it("renders as a horizontally scrollable row rather than a collapsed menu", () => {
    // No hamburger/collapsed-state toggle exists for this MVP shell -- the
    // nav relies on horizontal overflow scrolling on narrow viewports.
    usePathname.mockReturnValue("/");

    render(<PrimaryNav />);

    expect(screen.queryByRole("button", { name: /menu/i })).not.toBeInTheDocument();
  });
});
