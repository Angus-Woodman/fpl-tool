import { expect, test, type Page, type Route } from "@playwright/test";

const API_ORIGIN = "http://127.0.0.1:8000";
const CORS_HEADERS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "content-type",
  "access-control-allow-methods": "GET,POST,PUT,OPTIONS",
};

type StubPlayer = {
  player_id: number;
  web_name: string;
  position: "GK" | "DEF" | "MID" | "FWD";
  team_short_name: string;
  current_price: number;
  is_starting: boolean;
  bench_order: number | null;
  is_captain: boolean;
  is_vice_captain: boolean;
};

const SQUAD: StubPlayer[] = [
  {
    player_id: 1,
    web_name: "GK One",
    position: "GK",
    team_short_name: "ARS",
    current_price: 4.0,
    is_starting: true,
    bench_order: null,
    is_captain: false,
    is_vice_captain: false,
  },
  {
    player_id: 2,
    web_name: "GK Two",
    position: "GK",
    team_short_name: "AVL",
    current_price: 4.1,
    is_starting: false,
    bench_order: 1,
    is_captain: false,
    is_vice_captain: false,
  },
  {
    player_id: 3,
    web_name: "DEF One",
    position: "DEF",
    team_short_name: "BOU",
    current_price: 4.2,
    is_starting: true,
    bench_order: null,
    is_captain: false,
    is_vice_captain: false,
  },
  {
    player_id: 4,
    web_name: "DEF Two",
    position: "DEF",
    team_short_name: "CHE",
    current_price: 4.3,
    is_starting: true,
    bench_order: null,
    is_captain: false,
    is_vice_captain: false,
  },
  {
    player_id: 5,
    web_name: "DEF Three",
    position: "DEF",
    team_short_name: "EVE",
    current_price: 4.4,
    is_starting: true,
    bench_order: null,
    is_captain: false,
    is_vice_captain: false,
  },
  {
    player_id: 6,
    web_name: "DEF Four",
    position: "DEF",
    team_short_name: "FUL",
    current_price: 4.5,
    is_starting: true,
    bench_order: null,
    is_captain: false,
    is_vice_captain: false,
  },
  {
    player_id: 7,
    web_name: "DEF Five",
    position: "DEF",
    team_short_name: "LEI",
    current_price: 4.6,
    is_starting: false,
    bench_order: 2,
    is_captain: false,
    is_vice_captain: false,
  },
  {
    player_id: 8,
    web_name: "MID One",
    position: "MID",
    team_short_name: "LIV",
    current_price: 5.0,
    is_starting: true,
    bench_order: null,
    is_captain: true,
    is_vice_captain: false,
  },
  {
    player_id: 9,
    web_name: "MID Nine",
    position: "MID",
    team_short_name: "MCI",
    current_price: 5.1,
    is_starting: true,
    bench_order: null,
    is_captain: false,
    is_vice_captain: true,
  },
  {
    player_id: 10,
    web_name: "MID Three",
    position: "MID",
    team_short_name: "NEW",
    current_price: 5.2,
    is_starting: true,
    bench_order: null,
    is_captain: false,
    is_vice_captain: false,
  },
  {
    player_id: 11,
    web_name: "MID Four",
    position: "MID",
    team_short_name: "NFO",
    current_price: 5.3,
    is_starting: true,
    bench_order: null,
    is_captain: false,
    is_vice_captain: false,
  },
  {
    player_id: 12,
    web_name: "MID Five",
    position: "MID",
    team_short_name: "SOU",
    current_price: 5.4,
    is_starting: false,
    bench_order: 3,
    is_captain: false,
    is_vice_captain: false,
  },
  {
    player_id: 13,
    web_name: "FWD One",
    position: "FWD",
    team_short_name: "TOT",
    current_price: 6.0,
    is_starting: true,
    bench_order: null,
    is_captain: false,
    is_vice_captain: false,
  },
  {
    player_id: 14,
    web_name: "FWD Two",
    position: "FWD",
    team_short_name: "WHU",
    current_price: 6.1,
    is_starting: true,
    bench_order: null,
    is_captain: false,
    is_vice_captain: false,
  },
  {
    player_id: 15,
    web_name: "FWD Three",
    position: "FWD",
    team_short_name: "WOL",
    current_price: 6.2,
    is_starting: false,
    bench_order: 4,
    is_captain: false,
    is_vice_captain: false,
  },
];

function squadResponse(bank = 2.3) {
  return {
    squad_id: 1,
    name: "My Team",
    bank,
    free_transfers: 1,
    projection_totals: null,
    bench_projection_totals: null,
    captain_adjusted_projection_totals: null,
    gameweek_numbers: [],
    legal_rearrangements: [
      { first_player_id: 1, second_player_id: 2, kind: "substitution" },
    ],
    players: SQUAD.map((player) => ({
      ...player,
      first_name: player.web_name,
      second_name: player.web_name,
      team_name: player.team_short_name,
      status: "a",
      projection_totals: null,
      fixture_projections: [],
    })),
  };
}

type StubCandidate = {
  player_id: number;
  web_name: string;
  team_short_name: string;
  price: number;
  resulting_bank: number;
  team_gain_by_horizon: Record<string, number>;
  direct_xpts_difference: number | null;
  gameweeks_evaluated: number;
  is_legal: boolean;
  unavailable_reasons: string[];
  status: string;
};

function candidate(
  index: number,
  overrides: Partial<StubCandidate> = {},
): StubCandidate {
  return {
    player_id: 1000 + index,
    web_name: `Candidate ${String(index).padStart(2, "0")}`,
    team_short_name: "CHE",
    price: 5.0,
    resulting_bank: 2.4,
    team_gain_by_horizon: { "1": 1.0, "3": 3.0, "5": 5.0 - index * 0.01 },
    direct_xpts_difference: 0.5,
    gameweeks_evaluated: 5,
    is_legal: true,
    unavailable_reasons: [],
    status: "a",
    ...overrides,
  };
}

function explorerResponse(candidates: StubCandidate[]) {
  return {
    model_version: "component_v3",
    projection_run_id: 42,
    generated_at: "2026-08-16T08:10:00+00:00",
    primary_horizon: 5,
    bank: 2.3,
    selling_price_is_approximate: true,
    outgoing: {
      player_id: 9,
      web_name: "MID Nine",
      position: "MID",
      team_short_name: "MCI",
      current_price: 5.1,
      selling_price: 5.1,
      projected_points_by_horizon: { "1": 3.3, "3": 9.0, "5": 15.0 },
    },
    candidates,
    evaluated_gameweek_numbers: [5, 6, 7, 8, 9],
  };
}

function lineup(captain: number) {
  return {
    starting_xi: [1, 3, 4, 5, 6, 8, 9, 10, 11, 13, 14],
    bench_goalkeeper: 2,
    bench_outfield: [7, 12, 15],
    captain,
    vice_captain: 13,
    starting_xi_points: 40.0,
    captain_adjusted_points: 44.5,
  };
}

function previewResponse(
  playerInId: number,
  overrides: Record<string, unknown> = {},
) {
  return {
    model_version: "component_v3",
    projection_run_id: 42,
    generated_at: "2026-08-16T08:10:00+00:00",
    target_gameweek_number: 5,
    bank: 2.3,
    resulting_bank: 2.4,
    selling_price_is_approximate: true,
    player_out_id: 9,
    player_in_id: playerInId,
    is_legal: true,
    errors: [],
    projected_team_gain: 1.2,
    direct_player_xpts_difference: 0.5,
    lineup_before: lineup(8),
    lineup_after: lineup(playerInId),
    captain_changed: false,
    vice_captain_changed: false,
    player_in_status: "a",
    ...overrides,
  };
}

type Recorded = { method: string; path: string; body: string | null };

type ApiStub = {
  candidates: StubCandidate[];
  previews?: Record<number, ReturnType<typeof previewResponse>>;
  bank?: number;
};

/** Stubs every backend call so the spec never depends on database state. */
async function stubApi(page: Page, stub: ApiStub): Promise<Recorded[]> {
  const recorded: Recorded[] = [];

  await page.route(`${API_ORIGIN}/**`, async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        headers: { ...CORS_HEADERS, "content-type": "application/json" },
        body: JSON.stringify(body),
      });

    if (request.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: CORS_HEADERS });
    }

    recorded.push({
      method: request.method(),
      path: `${path}${url.search}`,
      body: request.postData(),
    });

    if (path === "/teams") {
      return json({ items: [], total: 0 });
    }
    if (path === "/my-team/recommendation") {
      return json({ detail: "No squad saved yet" }, 404);
    }
    if (
      path === "/my-team" &&
      (request.method() === "GET" || request.method() === "PUT")
    ) {
      return json(squadResponse(stub.bank));
    }
    if (
      /^\/my-team\/transfers\/\d+\/apply$/.test(path) &&
      request.method() === "POST"
    ) {
      return json(squadResponse(stub.bank));
    }
    const previewMatch = path.match(/^\/my-team\/transfers\/\d+\/preview$/);
    if (previewMatch) {
      const playerInId = Number(url.searchParams.get("player_in_id"));
      return json(stub.previews?.[playerInId] ?? previewResponse(playerInId));
    }
    if (/^\/my-team\/transfers\/\d+$/.test(path)) {
      return json(explorerResponse(stub.candidates));
    }
    return json({ detail: `Unstubbed ${request.method()} ${path}` }, 404);
  });

  return recorded;
}

test.describe("My Team UX", () => {
  test("a Preview opened from near the top of a long candidate list is in the viewport without scrolling", async ({
    page,
  }) => {
    const candidates = Array.from({ length: 80 }, (_, index) =>
      candidate(index + 1),
    );
    await stubApi(page, { candidates });

    await page.goto("/transfers?out=9");
    await expect(page.getByText("Replacing MID Nine")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Preview transfer" }),
    ).toHaveCount(80);

    const firstPreviewButton = page
      .getByRole("button", { name: "Preview transfer" })
      .first();
    await expect(firstPreviewButton).toBeInViewport();

    await firstPreviewButton.click();

    const heading = page.getByRole("heading", {
      name: "Preview: MID Nine → Candidate 01",
    });
    await expect(heading).toBeVisible();
    // The result of the click must be visible to the user without any scrolling.
    await expect(heading).toBeInViewport({ ratio: 1 });
    await expect(
      page.getByRole("button", { name: "Apply transfer" }),
    ).toBeInViewport();
  });

  test("a swap saves immediately and its PUT /my-team body carries the stubbed saved bank exactly", async ({
    page,
  }) => {
    const recorded = await stubApi(page, { candidates: [], bank: 2.3 });

    await page.goto("/my-team");
    await expect(page.getByText("Bank: 2.3")).toBeVisible();
    await expect(page.getByRole("button", { name: "Edit Team" })).toHaveCount(
      0,
    );

    await page.getByRole("button", { name: "Select GK One" }).click();
    await page.getByRole("button", { name: "Select GK Two" }).click();

    await expect(page.getByTestId("swap-confirmation")).toContainText("GK One");
    const put = recorded.find(
      (entry) => entry.method === "PUT" && entry.path === "/my-team",
    );
    expect(put).toBeDefined();
    const body = JSON.parse(put?.body ?? "{}") as {
      bank: number;
      free_transfers: number;
    };
    expect(body.bank).toBe(2.3);
    expect(body.free_transfers).toBe(1);
  });

  test("Explore transfers from a squad card opens the Explorer already showing that player", async ({
    page,
  }) => {
    await stubApi(page, { candidates: [candidate(1)] });

    await page.goto("/my-team");
    const card = page.locator("article", {
      has: page.getByRole("button", { name: "Select MID Nine" }),
    });
    await card.getByRole("link", { name: /Explore transfers/ }).click();

    await expect(page).toHaveURL(/\/transfers\?out=9$/);
    await expect(page.getByText("Replacing MID Nine")).toBeVisible();
    await expect(page.getByLabel("Outgoing player")).toHaveCount(0);
  });

  test("an unavailable candidate is listed with its reason and its Preview keeps Apply disabled", async ({
    page,
  }) => {
    const unavailable = candidate(1, {
      web_name: "Premium Pick",
      price: 12.5,
      resulting_bank: -5.1,
      is_legal: false,
      unavailable_reasons: ["insufficient_bank"],
    });
    await stubApi(page, {
      candidates: [unavailable, candidate(2)],
      previews: {
        [unavailable.player_id]: previewResponse(unavailable.player_id, {
          is_legal: false,
          errors: ["insufficient_bank"],
          resulting_bank: -5.1,
          lineup_after: null,
        }),
      },
    });

    await page.goto("/transfers?out=9");
    const row = page.getByRole("row", { name: /Premium Pick/ });
    await expect(row).toContainText("Unavailable: Insufficient budget");
    await expect(row).not.toContainText("insufficient_bank");
    await expect(
      row.getByRole("button", { name: "Preview transfer" }),
    ).toBeEnabled();

    await row.getByRole("button", { name: "Preview transfer" }).click();

    await expect(
      page.getByText(
        /This transfer is not currently legal: Insufficient budget/,
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Apply transfer" }),
    ).toBeDisabled();
  });

  test("a legal candidate is previewed and then applied only on the explicit Apply click", async ({
    page,
  }) => {
    const recorded = await stubApi(page, {
      candidates: [candidate(1), candidate(2)],
    });

    await page.goto("/transfers?out=9");
    await page
      .getByRole("button", { name: "Preview transfer" })
      .first()
      .click();
    await expect(
      page.getByRole("heading", { name: "Preview: MID Nine → Candidate 01" }),
    ).toBeVisible();

    expect(recorded.filter((entry) => entry.method !== "GET")).toHaveLength(0);

    await page.getByRole("button", { name: "Apply transfer" }).click();

    await expect(
      page.getByRole("heading", { name: "Transfer applied" }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "View My Team" }),
    ).toHaveAttribute("href", "/my-team");
    const apply = recorded.find((entry) => entry.method === "POST");
    expect(apply?.path).toBe("/my-team/transfers/9/apply");
    expect(JSON.parse(apply?.body ?? "{}")).toEqual({ player_in_id: 1001 });
  });

  test("an injured but selectable (non-'a') player remains explorable, previewable and applicable", async ({
    page,
  }) => {
    const injured = candidate(1, { web_name: "Knocked Winger", status: "i" });
    const recorded = await stubApi(page, {
      candidates: [injured],
      previews: {
        [injured.player_id]: previewResponse(injured.player_id, {
          player_in_status: "i",
        }),
      },
    });

    await page.goto("/transfers?out=9");
    const row = page.getByRole("row", { name: /Knocked Winger/ });
    await expect(row).toContainText("Injured");
    await row.getByRole("button", { name: "Preview transfer" }).click();

    await expect(page.getByText(/Playing status: Injured/)).toBeVisible();
    await expect(
      page.getByText(/This transfer is not currently legal/),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Apply transfer" }),
    ).toBeEnabled();

    await page.getByRole("button", { name: "Apply transfer" }).click();

    await expect(
      page.getByRole("heading", { name: "Transfer applied" }),
    ).toBeVisible();
    expect(
      recorded.some(
        (entry) => entry.method === "POST" && entry.path.endsWith("/apply"),
      ),
    ).toBe(true);
  });
});
