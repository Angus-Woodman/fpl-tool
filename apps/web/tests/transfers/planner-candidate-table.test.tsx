import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PlannerCandidateTable } from "@/components/transfers/planner/planner-candidate-table";
import type {
  PlanExplorerCandidate,
  PlanExplorerHorizonInfo,
  TransferHorizon,
} from "@/lib/api";

import {
  buildExplorerHorizons,
  buildRealisticCandidatePool,
} from "../fixtures/planner-explorer";

afterEach(cleanup);

/** The server's order for the five-gameweek ranking: gain over five gameweeks, then player id. */
const SERVER_ORDER = [
  207, 201, 202, 203, 204, 205, 206, 208, 209, 210, 211, 212,
];

type TableProps = {
  candidates?: PlanExplorerCandidate[];
  horizons?: PlanExplorerHorizonInfo[];
  horizon?: TransferHorizon;
};

function elements(props: TableProps, onPreview: (id: number) => void) {
  return (
    <PlannerCandidateTable
      candidates={props.candidates ?? buildRealisticCandidatePool()}
      horizons={props.horizons ?? buildExplorerHorizons()}
      horizon={props.horizon ?? 5}
      bankIsEstimated={false}
      onPreview={onPreview}
    />
  );
}

function renderTable(props: TableProps = {}) {
  const onPreview = vi.fn();
  const view = render(elements(props, onPreview));
  return {
    onPreview,
    rerenderWith: (next: TableProps) =>
      view.rerender(elements(next, onPreview)),
  };
}

const ids = (): number[] =>
  Array.from(document.querySelectorAll("tbody tr")).map((row) =>
    Number(row.getAttribute("data-player-id")),
  );

const rowFor = (id: number): HTMLElement =>
  document.querySelector(`tbody tr[data-player-id="${id}"]`) as HTMLElement;

const search = () => screen.getByRole("searchbox", { name: "Search players" });
const club = () => screen.getByRole("combobox", { name: "Club" });
const maxPrice = () =>
  screen.getByRole("textbox", { name: "Maximum price (£m)" });
const availableOnly = () =>
  screen.getByRole("checkbox", { name: "Available to apply only" });
const playingStatus = () =>
  screen.getByRole("combobox", { name: "Playing status" });
const sortBy = () => screen.getByRole("combobox", { name: "Sort by" });
const direction = () =>
  screen.getByRole("button", { name: /^Sort direction: / });
const activeFilters = () =>
  screen.getByRole("list", { name: "Active filters" });

function type(element: HTMLElement, value: string) {
  fireEvent.change(element, { target: { value } });
}

function fixturesOf(id: number): HTMLElement {
  return within(rowFor(id)).getByTestId("fixtures");
}

const gameweekItem = (id: number, gameweek: number): HTMLElement =>
  fixturesOf(id).querySelector(
    `li[data-gameweek="${gameweek}"]`,
  ) as HTMLElement;

describe("PlannerCandidateTable default presentation", () => {
  it("lists every candidate in exactly the order the server returned", () => {
    renderTable();

    expect(ids()).toEqual(SERVER_ORDER);
    expect(sortBy()).toHaveValue("default");
    expect(screen.queryByRole("list", { name: "Active filters" })).toBeNull();
    expect(screen.getByTestId("result-count")).toHaveTextContent(
      "Showing 12 of 12 candidates",
    );
  });

  it("keeps the server order whatever the data would sort to, so a different ranking is the server's to give", () => {
    const reversed = [...buildRealisticCandidatePool()].reverse();
    renderTable({ candidates: reversed });

    expect(ids()).toEqual([...SERVER_ORDER].reverse());
  });

  it("shows unavailable and blocked candidates by default, with their states", () => {
    renderTable();

    expect(rowFor(207)).toHaveAttribute("data-state", "unavailable");
    expect(rowFor(206)).toHaveAttribute(
      "data-state",
      "blocked_by_later_decision",
    );
    expect(within(rowFor(207)).getByText(/Unavailable:/)).toBeInTheDocument();
    expect(
      within(rowFor(206)).getByText(/Blocked by GW11 planned transfer/),
    ).toBeInTheDocument();
  });

  it("offers a club for every club in the pool, once, and a status for every status present", () => {
    renderTable();

    expect(
      within(club())
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual([
      "All clubs",
      "BOU",
      "BRE",
      "CHE",
      "LIV",
      "MCI",
      "NEW",
      "TOT",
      "WHU",
    ]);
    expect(
      within(playingStatus())
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual([
      "Any status",
      "Available",
      "Doubtful",
      "Injured",
      "Suspended",
      "Unavailable",
    ]);
  });
});

describe("PlannerCandidateTable search and filters", () => {
  it("searches names case-insensitively, by any part of the name", () => {
    renderTable();

    type(search(), "OKAF");
    expect(ids()).toEqual([201]);

    type(search(), "jamie");
    expect(ids()).toEqual([201, 211]);

    type(search(), "mie o");
    expect(ids()).toEqual([201]);

    type(search(), "  ok  ");
    expect(ids()).toEqual([201, 210]);
  });

  it("restores every candidate when the search is cleared", () => {
    renderTable();
    type(search(), "ward");
    expect(ids()).toEqual([211]);

    type(search(), "");

    expect(ids()).toEqual(SERVER_ORDER);
  });

  it("filters by club, keeping the server's relative order", () => {
    renderTable();

    type(club(), "CHE");
    expect(ids()).toEqual([202, 209]);

    type(club(), "LIV");
    expect(ids()).toEqual([201, 210]);
  });

  it("filters by a maximum price in £m, inclusive, using integer tenths", () => {
    renderTable();

    type(maxPrice(), "5.5");
    expect(ids()).toEqual([205, 208, 209, 210, 211]);

    type(maxPrice(), "5.2");
    expect(ids()).toEqual([208, 209, 210, 211]);

    type(maxPrice(), "6");
    expect(ids()).toEqual([203, 204, 205, 206, 208, 209, 210, 211]);

    type(maxPrice(), "12.5");
    expect(ids()).toEqual(SERVER_ORDER);
  });

  it("does not apply an unreadable price, and says so", () => {
    renderTable();

    for (const bad of ["5.55", "abc", "-1", "6,5"]) {
      type(maxPrice(), bad);
      expect(ids()).toEqual(SERVER_ORDER);
      expect(maxPrice()).toHaveAttribute("aria-invalid", "true");
      expect(screen.getByText(/Enter a price in £m/)).toBeInTheDocument();
      expect(screen.queryByRole("list", { name: "Active filters" })).toBeNull();
    }

    type(maxPrice(), "");
    expect(maxPrice()).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByText(/Enter a price in £m/)).toBeNull();
  });

  it("combines club and a maximum price to find affordable candidates from one club", () => {
    renderTable();

    type(club(), "CHE");
    type(maxPrice(), "6.0");
    expect(ids()).toEqual([209]);

    type(maxPrice(), "6.2");
    expect(ids()).toEqual([202, 209]);
  });

  it("limits to candidates the server says are available to apply, regardless of playing status", () => {
    renderTable();

    fireEvent.click(availableOnly());

    expect(ids()).toEqual([201, 202, 203, 204, 205, 208, 209, 210, 211]);
    for (const id of [204, 205, 210, 211]) {
      // Doubtful, injured, suspended and unavailable players are still selectable.
      expect(rowFor(id)).toHaveAttribute("data-state", "available");
    }
    expect(ids()).not.toContain(206);
  });

  it("filters by the advisory playing status without changing any candidate's state", () => {
    renderTable();

    type(playingStatus(), "i");
    expect(ids()).toEqual([205]);
    expect(rowFor(205)).toHaveAttribute("data-state", "available");

    type(playingStatus(), "d");
    expect(ids()).toEqual([204]);

    type(playingStatus(), "s");
    expect(ids()).toEqual([210]);

    type(playingStatus(), "u");
    expect(ids()).toEqual([211]);

    type(playingStatus(), "a");
    // Fully fit players still include a blocked and unavailable candidate.
    expect(ids()).toEqual([207, 201, 202, 203, 206, 208, 209, 212]);
    expect(rowFor(206)).toHaveAttribute(
      "data-state",
      "blocked_by_later_decision",
    );
    expect(rowFor(207)).toHaveAttribute("data-state", "unavailable");
  });

  it("combines every filter", () => {
    renderTable();

    type(club(), "LIV");
    fireEvent.click(availableOnly());
    expect(ids()).toEqual([201, 210]);

    type(playingStatus(), "s");
    expect(ids()).toEqual([210]);

    type(search(), "okon");
    type(maxPrice(), "4.5");
    expect(ids()).toEqual([210]);

    type(maxPrice(), "4.4");
    expect(ids()).toEqual([]);
  });
});

describe("PlannerCandidateTable sorting", () => {
  const cases: [string, string, number[]][] = [
    [
      "gain-1",
      "Best-XI gain over 1 GW",
      [207, 201, 202, 205, 203, 204, 206, 208, 209, 210, 211, 212],
    ],
    [
      "gain-3",
      "Best-XI gain over 3 GWs",
      [207, 201, 202, 203, 204, 208, 205, 206, 209, 210, 211, 212],
    ],
    ["gain-5", "Best-XI gain over 5 GWs", SERVER_ORDER],
    [
      "price",
      "Price",
      [211, 210, 208, 209, 205, 206, 203, 204, 202, 201, 212, 207],
    ],
    [
      "bank",
      "Resulting bank",
      [211, 210, 208, 209, 205, 206, 203, 204, 202, 201, 207, 212],
    ],
    [
      "difficulty",
      "Fixture difficulty",
      [207, 212, 204, 201, 202, 208, 209, 203, 205, 206, 210, 211],
    ],
  ];

  it.each(cases)(
    "sorts by %s with the documented default direction",
    (value, label, expected) => {
      renderTable();

      type(sortBy(), value);

      expect(ids()).toEqual(expected);
      expect(
        within(activeFilters()).getByText(new RegExp(`Sorted by ${label}`)),
      ).toBeInTheDocument();
    },
  );

  it("names each default direction plainly", () => {
    renderTable();
    const expectations: [string, RegExp][] = [
      ["gain-1", /highest first/],
      ["gain-3", /highest first/],
      ["gain-5", /highest first/],
      ["price", /lowest first/],
      ["bank", /highest first/],
      ["difficulty", /easiest first/],
    ];

    for (const [value, direction_] of expectations) {
      type(sortBy(), value);
      expect(direction()).toHaveAccessibleName(direction_);
    }
  });

  it("reverses each sort when the direction is toggled and keeps nulls last", () => {
    renderTable();

    type(sortBy(), "price");
    fireEvent.click(direction());
    expect(ids()).toEqual([
      207, 212, 201, 202, 204, 203, 206, 205, 208, 209, 210, 211,
    ]);

    type(sortBy(), "bank");
    expect(direction()).toHaveAccessibleName(/highest first/);
    fireEvent.click(direction());
    // The two candidates without a resulting bank stay last, whatever the direction.
    expect(ids()).toEqual([
      201, 202, 204, 203, 206, 205, 208, 209, 210, 211, 207, 212,
    ]);

    type(sortBy(), "gain-3");
    fireEvent.click(direction());
    expect(ids()).toEqual([
      212, 211, 210, 209, 206, 205, 203, 204, 208, 202, 201, 207,
    ]);

    type(sortBy(), "gain-5");
    fireEvent.click(direction());
    expect(ids()).toEqual([
      212, 211, 210, 209, 208, 206, 205, 203, 204, 202, 201, 207,
    ]);

    type(sortBy(), "difficulty");
    fireEvent.click(direction());
    // Candidates with no difficulty at all still come last when hardest is first.
    expect(ids()).toEqual([
      205, 206, 203, 208, 209, 201, 202, 204, 212, 207, 210, 211,
    ]);
  });

  it("breaks ties by ascending player id in both directions", () => {
    renderTable();

    // 208 and 209 share a price and a resulting bank; 203 and 204 share a 5-gameweek gain.
    type(sortBy(), "price");
    expect(ids().indexOf(208)).toBeLessThan(ids().indexOf(209));
    fireEvent.click(direction());
    expect(ids().indexOf(208)).toBeLessThan(ids().indexOf(209));

    type(sortBy(), "gain-5");
    fireEvent.click(direction());
    expect(ids().indexOf(203)).toBeLessThan(ids().indexOf(204));
    fireEvent.click(direction());
    expect(ids().indexOf(203)).toBeLessThan(ids().indexOf(204));
  });

  it("is stable however many times the same sort is applied", () => {
    renderTable();

    type(sortBy(), "bank");
    const first = ids();
    type(sortBy(), "price");
    type(sortBy(), "bank");

    expect(ids()).toEqual(first);
  });

  it("gives the same order for the same data whatever order the server sent it in", () => {
    const shuffled = [...buildRealisticCandidatePool()].sort(
      (left, right) =>
        ((left.player_id * 7) % 11) - ((right.player_id * 7) % 11),
    );
    renderTable({ candidates: shuffled });

    type(sortBy(), "price");
    expect(ids()).toEqual([
      211, 210, 208, 209, 205, 206, 203, 204, 202, 201, 212, 207,
    ]);
    type(sortBy(), "difficulty");
    expect(ids()).toEqual([
      207, 212, 204, 201, 202, 208, 209, 203, 205, 206, 210, 211,
    ]);
  });

  it("sorts by gain at every horizon whichever horizon the server ranked on", () => {
    renderTable({ horizon: 3 });

    expect(ids()).toEqual(SERVER_ORDER);
    type(sortBy(), "gain-1");
    expect(ids().slice(0, 5)).toEqual([207, 201, 202, 205, 203]);
    type(sortBy(), "gain-5");
    expect(ids()).toEqual(SERVER_ORDER);
  });

  it("restores the server's order from the default option, the chip and the reset control", () => {
    renderTable();
    type(sortBy(), "price");
    expect(ids()).not.toEqual(SERVER_ORDER);

    type(sortBy(), "default");
    expect(ids()).toEqual(SERVER_ORDER);

    type(sortBy(), "bank");
    fireEvent.click(
      within(activeFilters()).getByRole("button", {
        name: /^Remove Sorted by/,
      }),
    );
    expect(ids()).toEqual(SERVER_ORDER);
    expect(sortBy()).toHaveValue("default");

    type(sortBy(), "difficulty");
    fireEvent.click(
      screen.getByRole("button", { name: "Reset filters and sort" }),
    );
    expect(ids()).toEqual(SERVER_ORDER);
    expect(sortBy()).toHaveValue("default");
  });

  it("disables the direction control while the server ranking is shown", () => {
    renderTable();

    expect(direction()).toBeDisabled();
    type(sortBy(), "price");
    expect(direction()).toBeEnabled();
  });

  it("marks the sorted column header and clears it on reset", () => {
    renderTable();

    type(sortBy(), "price");
    const priceHeader = screen.getByRole("columnheader", { name: "Price" });
    expect(priceHeader).toHaveAttribute("aria-sort", "ascending");
    fireEvent.click(direction());
    expect(priceHeader).toHaveAttribute("aria-sort", "descending");

    type(sortBy(), "gain-3");
    expect(priceHeader).not.toHaveAttribute("aria-sort");
    expect(
      screen.getByRole("columnheader", { name: /^Best-XI gain GW9-11/ }),
    ).toHaveAttribute("aria-sort", "descending");

    type(sortBy(), "difficulty");
    expect(
      screen.getByRole("columnheader", { name: /^Fixtures/ }),
    ).toHaveAttribute("aria-sort", "ascending");

    type(sortBy(), "default");
    expect(document.querySelector("[aria-sort]")).toBeNull();
  });

  it("sorts the filtered candidates only", () => {
    renderTable();

    type(club(), "TOT");
    type(sortBy(), "price");
    expect(ids()).toEqual([205, 212]);
    fireEvent.click(direction());
    expect(ids()).toEqual([212, 205]);
  });
});

describe("PlannerCandidateTable fixture difficulty sort", () => {
  it("ranks by the mean of the supplied difficulties across the horizon's fixtures", () => {
    renderTable({ horizon: 3, horizons: buildExplorerHorizons() });

    type(sortBy(), "difficulty");

    // GW9-11. 212 mean 2.0; 204 (double GW11) 10/4=2.5; 201, 202, 207 2.667 (tie by id);
    // 203 (blank GW10) and 209 3.0; 208 3.33; 206 3.5 (a missing value is ignored); 205 4.0.
    expect(ids()).toEqual([
      212, 204, 201, 202, 207, 203, 209, 208, 206, 205, 210, 211,
    ]);
    expect(
      screen.getByText(/mean of the supplied difficulties over GW9-11/i),
    ).toBeInTheDocument();
  });

  it("counts every fixture of a double gameweek and none for a blank", () => {
    const pool = buildRealisticCandidatePool().filter((candidate) =>
      [203, 204].includes(candidate.player_id),
    );
    renderTable({ candidates: pool, horizon: 3 });

    // GW9-11: 203 averages 4, 2 (6/2, the blank GW10 adds nothing); 204 averages 2, 3, 2, 3 (10/4).
    // A per-gameweek total would instead rank 203 (6) ahead of 204 (10).
    type(sortBy(), "difficulty");
    expect(ids()).toEqual([204, 203]);
  });

  it("ranks candidates without any difficulty after every other candidate, in both directions", () => {
    renderTable();

    type(sortBy(), "difficulty");
    expect(ids().slice(-2)).toEqual([210, 211]);
    fireEvent.click(direction());
    expect(ids().slice(-2)).toEqual([210, 211]);
  });

  it("uses only the horizon's fixtures", () => {
    const pool = buildRealisticCandidatePool().map((candidate) =>
      candidate.player_id === 201
        ? {
            ...candidate,
            fixtures: candidate.fixtures.map((fixture) =>
              fixture.gameweek === 13 ? { ...fixture, difficulty: 5 } : fixture,
            ),
          }
        : candidate,
    );
    renderTable({ candidates: pool, horizon: 3 });

    type(sortBy(), "difficulty");

    // The hard GW13 fixture lies beyond the 3-gameweek horizon.
    expect(ids().indexOf(201)).toBeLessThan(ids().indexOf(203));
  });
});

describe("PlannerCandidateTable active filters, reset and empty state", () => {
  it("shows each active filter and the active sort, and removes them one by one", () => {
    renderTable();

    type(search(), "jamie");
    type(club(), "LIV");
    type(maxPrice(), "6.7");
    fireEvent.click(availableOnly());
    type(playingStatus(), "a");
    type(sortBy(), "price");

    const list = activeFilters();
    const labels = within(list)
      .getAllByRole("listitem")
      .map((item) => item.textContent);
    expect(labels).toEqual([
      expect.stringContaining('Search: "jamie"'),
      expect.stringContaining("Club: LIV"),
      expect.stringContaining("Maximum price: £6.7m"),
      expect.stringContaining("Available to apply only"),
      expect.stringContaining("Playing status: Available"),
      expect.stringContaining("Sorted by Price, lowest first"),
    ]);
    expect(ids()).toEqual([201]);

    fireEvent.click(
      within(list).getByRole("button", { name: 'Remove Search: "jamie"' }),
    );
    expect(search()).toHaveValue("");
    expect(ids()).toEqual([201]);

    fireEvent.click(
      within(list).getByRole("button", { name: "Remove Club: LIV" }),
    );
    expect(club()).toHaveValue("");
    fireEvent.click(
      within(list).getByRole("button", { name: "Remove Maximum price: £6.7m" }),
    );
    expect(maxPrice()).toHaveValue("");
    fireEvent.click(
      within(list).getByRole("button", {
        name: "Remove Available to apply only",
      }),
    );
    expect(availableOnly()).not.toBeChecked();
    fireEvent.click(
      within(list).getByRole("button", {
        name: "Remove Playing status: Available",
      }),
    );
    expect(playingStatus()).toHaveValue("");

    expect(sortBy()).toHaveValue("price");
    expect(ids()).toEqual([
      211, 210, 208, 209, 205, 206, 203, 204, 202, 201, 212, 207,
    ]);
  });

  it("resets every control with one action", () => {
    renderTable();
    type(search(), "jamie");
    type(club(), "LIV");
    type(maxPrice(), "6.7");
    fireEvent.click(availableOnly());
    type(playingStatus(), "a");
    type(sortBy(), "bank");

    fireEvent.click(
      screen.getByRole("button", { name: "Reset filters and sort" }),
    );

    expect(search()).toHaveValue("");
    expect(club()).toHaveValue("");
    expect(maxPrice()).toHaveValue("");
    expect(availableOnly()).not.toBeChecked();
    expect(playingStatus()).toHaveValue("");
    expect(sortBy()).toHaveValue("default");
    expect(ids()).toEqual(SERVER_ORDER);
    expect(screen.queryByRole("list", { name: "Active filters" })).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Reset filters and sort" }),
    ).toBeNull();
  });

  it("reports the number shown out of the number the server returned", () => {
    renderTable();

    type(club(), "CHE");

    expect(screen.getByTestId("result-count")).toHaveTextContent(
      "Showing 2 of 12 candidates",
    );
  });

  it("explains an empty result and offers to clear the filters", () => {
    renderTable();
    type(sortBy(), "price");
    type(search(), "zzz");

    expect(ids()).toEqual([]);
    expect(
      screen.queryByRole("table", { name: "Replacement candidates" }),
    ).toBeNull();
    const empty = screen.getByTestId("no-matches");
    expect(empty).toHaveTextContent("No candidates match these filters.");
    expect(screen.getByTestId("result-count")).toHaveTextContent(
      "Showing 0 of 12 candidates",
    );

    fireEvent.click(
      within(empty).getByRole("button", { name: "Clear filters" }),
    );

    expect(screen.queryByTestId("no-matches")).toBeNull();
    expect(ids()).toEqual([
      211, 210, 208, 209, 205, 206, 203, 204, 202, 201, 212, 207,
    ]);
    expect(sortBy()).toHaveValue("price");
  });

  it("returns to the new server ranking when the primary horizon changes, keeping the filters", () => {
    const view = renderTable({ horizon: 5 });
    type(sortBy(), "price");
    type(club(), "LIV");

    const reranked = [...buildRealisticCandidatePool()].reverse();
    view.rerenderWith({ horizon: 3, candidates: reranked });

    expect(sortBy()).toHaveValue("default");
    expect(club()).toHaveValue("LIV");
    expect(ids()).toEqual([210, 201]);
  });
});

describe("PlannerCandidateTable fixtures over the selected horizon", () => {
  it("shows opponent, home or away and difficulty for each gameweek from the selected gameweek", () => {
    renderTable({ horizon: 5 });

    expect(
      screen.getByRole("columnheader", { name: /^Fixtures GW9-13/ }),
    ).toBeInTheDocument();
    const items = Array.from(fixturesOf(201).querySelectorAll("li"));
    expect(items.map((item) => item.getAttribute("data-gameweek"))).toEqual([
      "9",
      "10",
      "11",
      "12",
      "13",
    ]);
    expect(
      items.map((item) => item.textContent?.replace(/\s+/g, " ").trim()),
    ).toEqual([
      "GW9 BOU (H) Diff 2",
      "GW10 CHE (A) Diff 4",
      "GW11 EVE (H) Diff 2",
      "GW12 TOT (A) Diff 4",
      "GW13 WHU (H) Diff 2",
    ]);
  });

  it("shows only the gameweeks of the selected horizon", () => {
    const view = renderTable({ horizon: 3 });
    expect(
      Array.from(fixturesOf(201).querySelectorAll("li")).map((item) =>
        item.getAttribute("data-gameweek"),
      ),
    ).toEqual(["9", "10", "11"]);

    view.rerenderWith({ horizon: 1 });
    expect(
      Array.from(fixturesOf(201).querySelectorAll("li")).map((item) =>
        item.getAttribute("data-gameweek"),
      ),
    ).toEqual(["9"]);
  });

  it("starts at the selected gameweek, not at the first fixture the server happened to send", () => {
    const horizons = buildExplorerHorizons({
      3: {
        requested_gameweeks: [10, 11, 12],
        evaluated_gameweeks: [10, 11, 12],
      },
    });
    renderTable({ horizon: 3, horizons });

    expect(
      Array.from(fixturesOf(201).querySelectorAll("li")).map((item) =>
        item.getAttribute("data-gameweek"),
      ),
    ).toEqual(["10", "11", "12"]);
    expect(
      screen.getByRole("columnheader", { name: /^Fixtures GW10-12/ }),
    ).toBeInTheDocument();
  });

  it("keeps both fixtures of a double gameweek in that gameweek", () => {
    renderTable();

    const item = gameweekItem(204, 11);
    expect(item).toHaveAttribute("data-double", "true");
    expect(item).toHaveTextContent(/double/i);
    expect(
      within(item)
        .getAllByTestId("fixture")
        .map((fixture) => fixture.textContent?.replace(/\s+/g, " ").trim()),
    ).toEqual(["FUL (H) Diff 2", "TOT (A) Diff 3"]);
    expect(gameweekItem(201, 11)).not.toHaveAttribute("data-double");
  });

  it("labels a blank gameweek the server reported", () => {
    renderTable();

    const item = gameweekItem(203, 10);
    expect(item).toHaveAttribute("data-kind", "blank");
    expect(item).toHaveTextContent("GW10 Blank gameweek");
    expect(within(item).queryByTestId("fixture")).toBeNull();
  });

  it("says when fixture data is missing, instead of calling it a blank", () => {
    renderTable();

    const missing = gameweekItem(205, 12);
    expect(missing).toHaveAttribute("data-kind", "missing");
    expect(missing).toHaveTextContent("GW12 No fixture data");
    expect(missing).not.toHaveTextContent(/blank/i);
    for (const gameweek of [9, 10, 11, 12, 13]) {
      expect(gameweekItem(211, gameweek)).toHaveAttribute(
        "data-kind",
        "missing",
      );
    }
  });

  it("never invents a difficulty or a venue that was not supplied", () => {
    const pool = buildRealisticCandidatePool().map((candidate) =>
      candidate.player_id === 201
        ? {
            ...candidate,
            fixtures: candidate.fixtures.map((fixture) =>
              fixture.gameweek === 9 ? { ...fixture, is_home: null } : fixture,
            ),
          }
        : candidate,
    );
    renderTable({ candidates: pool });

    expect(gameweekItem(206, 10)).toHaveTextContent("CHE (H) Diff n/a");
    expect(gameweekItem(210, 9)).toHaveTextContent("BOU (H) Diff n/a");
    expect(gameweekItem(201, 9)).toHaveTextContent("BOU (venue n/a) Diff 2");
  });

  it("marks gameweeks outside the evaluated horizon as not evaluated", () => {
    const horizons = buildExplorerHorizons({
      5: {
        evaluated_gameweeks: [9, 10, 11],
        saved_plan_gameweeks: [9, 10],
        assumed_gameweeks: [11],
        partial: true,
      },
    });
    const pool = buildRealisticCandidatePool().map((candidate) => ({
      ...candidate,
      fixtures: candidate.fixtures.filter((fixture) => fixture.gameweek <= 11),
    }));
    renderTable({ candidates: pool, horizons });

    for (const gameweek of [12, 13]) {
      const item = gameweekItem(201, gameweek);
      expect(item).toHaveAttribute("data-kind", "not_evaluated");
      expect(item).toHaveTextContent(`GW${gameweek} Not evaluated`);
    }
    expect(gameweekItem(201, 11)).toHaveTextContent("EVE (H) Diff 2");
    expect(gameweekItem(205, 11)).toHaveTextContent("LIV (H) Diff 4");
  });
});

describe("PlannerCandidateTable keeps the server's values and actions", () => {
  function deepFreeze<T>(value: T): T {
    if (value !== null && typeof value === "object") {
      Object.values(value).forEach(deepFreeze);
      Object.freeze(value);
    }
    return value;
  }

  it("never mutates the candidates or their order, whatever is filtered or sorted", () => {
    const pool = deepFreeze(buildRealisticCandidatePool());
    const snapshot = structuredClone(pool);
    renderTable({ candidates: pool });

    type(sortBy(), "price");
    type(club(), "LIV");
    fireEvent.click(availableOnly());
    type(sortBy(), "difficulty");
    fireEvent.click(direction());
    type(search(), "o");
    fireEvent.click(
      screen.getByRole("button", { name: "Reset filters and sort" }),
    );

    expect(pool).toEqual(snapshot);
    expect(pool.map((candidate) => candidate.player_id)).toEqual(SERVER_ORDER);
    expect(ids()).toEqual(SERVER_ORDER);
  });

  it("shows each candidate's own values and state unchanged after filtering and sorting", () => {
    renderTable();
    const before = new Map(
      SERVER_ORDER.map((id) => [id, rowFor(id).textContent]),
    );

    type(sortBy(), "bank");
    fireEvent.click(direction());
    type(maxPrice(), "6.2");

    for (const id of ids()) {
      expect(rowFor(id).textContent).toBe(before.get(id));
    }
    expect(within(rowFor(202)).getByText("£6.2m")).toBeInTheDocument();
    expect(within(rowFor(202)).getByText("£0.5m")).toBeInTheDocument();
    expect(within(rowFor(204)).getByText("Doubtful")).toBeInTheDocument();
    expect(rowFor(206)).toHaveAttribute(
      "data-state",
      "blocked_by_later_decision",
    );
    expect(
      within(rowFor(206)).getByText(/Blocked by GW11 planned transfer/),
    ).toBeInTheDocument();
  });

  it("previews the original player after reordering and after filtering", () => {
    const { onPreview } = renderTable();

    type(sortBy(), "price");
    expect(ids()[0]).toBe(211);
    fireEvent.click(
      within(rowFor(211)).getByRole("button", { name: "Preview Jamie Ward" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Preview Kofi Mensah" }),
    );

    type(club(), "LIV");
    fireEvent.click(
      screen.getByRole("button", { name: "Preview Alex Okonkwo" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Preview Jamie Okafor" }),
    );

    expect(onPreview.mock.calls).toEqual([[211], [209], [210], [201]]);
  });

  it("still previews a candidate the server marked unavailable or blocked", () => {
    const { onPreview } = renderTable();

    fireEvent.click(
      screen.getByRole("button", { name: "Preview Marco Vidal" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Preview Ben Ashworth" }),
    );

    expect(onPreview.mock.calls).toEqual([[207], [206]]);
  });

  it("does not call back for searching, filtering or sorting", () => {
    const { onPreview } = renderTable();

    type(search(), "a");
    type(club(), "TOT");
    type(sortBy(), "gain-3");
    fireEvent.click(direction());
    fireEvent.click(availableOnly());

    expect(onPreview).not.toHaveBeenCalled();
  });
});
