import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type MockInstance,
} from "vitest";

import { PlannerTransferExplorer } from "@/components/transfers/planner/planner-transfer-explorer";
import type {
  PlanResponse,
  PlanTransferExplorerResponse,
  TransferHorizon,
} from "@/lib/api";

import {
  buildAvailableCandidate,
  buildBlockedCandidate,
  buildExplorerCandidate,
  buildExplorerHorizons,
  buildPlannerExplorerResponse,
  buildUnavailableCandidate,
  deferred,
  EXPLORER_GAMEWEEK,
  EXPLORER_OUTGOING_ID,
  EXPLORER_PLAN_ID,
  EXPLORER_RUN_ID,
} from "../fixtures/planner-explorer";
import { buildPlannerPlan } from "../fixtures/planner";

const { useRouter } = vi.hoisted(() => ({ useRouter: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter }));

const routerPush = vi.fn();
const routerReplace = vi.fn();

type ExplorerHandler = (url: URL) => Response | Promise<Response>;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function plannerPlan(overrides: Partial<PlanResponse> = {}): PlanResponse {
  return {
    ...buildPlannerPlan(9, 14),
    plan_id: EXPLORER_PLAN_ID,
    name: "Run-in plan",
    ...overrides,
  };
}

function installApi(options: {
  plan?: PlanResponse | null | "error";
  explorer?: PlanTransferExplorerResponse | ExplorerHandler;
}): MockInstance<typeof fetch> {
  const plan = options.plan === undefined ? plannerPlan() : options.plan;
  const explorer = options.explorer ?? buildPlannerExplorerResponse();
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      if (url.pathname === `/plans/${EXPLORER_PLAN_ID}`) {
        if (plan === "error") {
          return json(500, {});
        }
        if (plan === null) {
          return json(404, {
            detail: { code: "plan_not_found", message: "Plan not found" },
          });
        }
        return json(200, plan);
      }
      if (url.pathname.includes("/transfers/")) {
        return typeof explorer === "function"
          ? explorer(url)
          : json(200, explorer);
      }
      throw new Error(`Unexpected request ${url.pathname}`);
    });
}

function renderExplorer(
  props: {
    playerOutId?: number | null;
    horizon?: TransferHorizon;
    runId?: number | null;
  } = {},
) {
  const view = (next: typeof props) => (
    <PlannerTransferExplorer
      planId={EXPLORER_PLAN_ID}
      gameweek={EXPLORER_GAMEWEEK}
      playerOutId={
        next.playerOutId === undefined ? EXPLORER_OUTGOING_ID : next.playerOutId
      }
      horizon={next.horizon ?? 5}
      runId={next.runId ?? null}
    />
  );
  const result = render(view(props));
  return {
    ...result,
    rerenderWith: (next: typeof props) => result.rerender(view(next)),
  };
}

beforeEach(() => {
  useRouter.mockReturnValue({ push: routerPush, replace: routerReplace });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  routerPush.mockClear();
  routerReplace.mockClear();
});

describe("PlannerTransferExplorer: context and loading", () => {
  it("shows loading, then Planner mode context with a link back to the plan", async () => {
    installApi({});
    renderExplorer();

    expect(screen.getByRole("status")).toHaveTextContent(/loading/i);

    const banner = await screen.findByRole("region", {
      name: "Planner context",
    });
    expect(banner).toHaveTextContent("Planner mode");
    expect(banner).toHaveTextContent("Run-in plan");
    expect(banner).toHaveTextContent("Gameweek 9");
    expect(
      within(banner).getByRole("link", { name: /back to plan/i }),
    ).toHaveAttribute("href", "/plans/7?gw=9");
  });

  it("asks for an outgoing player when none is in the address and does not list candidates", async () => {
    const fetchSpy = installApi({});
    renderExplorer({ playerOutId: null });

    const select = await screen.findByRole("combobox", {
      name: "Outgoing player",
    });
    expect(within(select).getAllByRole("option")).toHaveLength(16);
    expect(
      fetchSpy.mock.calls.some(([input]) =>
        String(input).includes("/transfers/"),
      ),
    ).toBe(false);

    fireEvent.change(select, { target: { value: "8" } });
    expect(routerPush).toHaveBeenCalledWith("/transfers?plan=7&gw=9&out=8&h=5");
  });
});

describe("PlannerTransferExplorer: plan states", () => {
  it("reports a missing plan", async () => {
    installApi({ plan: null });
    renderExplorer();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /plan.*(no longer exists|not found)/i,
    );
    expect(screen.queryByText("Planner mode")).not.toBeInTheDocument();
  });

  it("reports a plan that is not ready", async () => {
    installApi({ plan: plannerPlan({ foundation_state: "legacy_pending" }) });
    renderExplorer();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /not ready for transfers/i,
    );
  });

  it("reports a plan_not_ready response from the list endpoint", async () => {
    installApi({
      explorer: () =>
        json(409, {
          detail: { code: "plan_not_ready", message: "Still initialising" },
        }),
    });
    renderExplorer();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /not ready for transfers/i,
    );
  });

  it("reports a gameweek that is not in the plan", async () => {
    installApi({ plan: plannerPlan({ gameweeks: [] }) });
    renderExplorer();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /GW9 is not part of this plan/i,
    );
  });

  it("surfaces a plan load failure instead of hiding it", async () => {
    installApi({ plan: "error" });
    renderExplorer();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /could not load/i,
    );
  });
});

describe("PlannerTransferExplorer: unavailable states", () => {
  const cases: [string, RegExp][] = [
    ["gameweek_not_in_plan", /GW9 is not part of this plan/i],
    ["evaluation_blocked", /cannot be evaluated/i],
    ["player_not_in_squad", /not in your squad/i],
    ["no_projection_run", /no projections are available yet/i],
    ["run_not_found", /projection run .*no longer exists/i],
    ["run_model_mismatch", /different (projection )?model/i],
    ["gameweek_not_projected", /no projections .*this gameweek/i],
    ["selectability_unknown", /could not be confirmed.*refresh/i],
    ["invalid_money", /money/i],
    ["invalid_horizon", /horizon/i],
  ];

  it.each(cases)("explains %s specifically", async (code, expected) => {
    installApi({
      explorer: () =>
        json(422, { detail: { code, message: `Server detail for ${code}` } }),
    });
    renderExplorer();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(expected);
    expect(alert).toHaveTextContent(`Server detail for ${code}`);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("names the players and gameweeks behind missing_projections", async () => {
    installApi({
      explorer: () =>
        json(422, {
          detail: {
            code: "missing_projections",
            message: "GW10: fixture not projected",
            missing_player_ids: [3, 8],
          },
        }),
    });
    renderExplorer();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/projections are missing/i);
    expect(alert).toHaveTextContent("GW10: fixture not projected");
    expect(alert).toHaveTextContent("#3");
    expect(alert).toHaveTextContent("#8");
  });

  it("keeps the planner context visible for unavailable states", async () => {
    installApi({
      explorer: () =>
        json(422, { detail: { code: "no_projection_run", message: "none" } }),
    });
    renderExplorer();

    await screen.findByRole("alert");
    expect(screen.getByText("Planner mode")).toBeInTheDocument();
  });
});

describe("PlannerTransferExplorer: candidates", () => {
  it("renders available, unavailable and blocked candidates with distinct states", async () => {
    installApi({});
    renderExplorer();

    const table = await screen.findByRole("table", {
      name: /replacement candidates/i,
    });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);

    const available = rows[0];
    expect(available).toHaveAttribute("data-state", "available");
    expect(available).toHaveTextContent("Available Alex");
    expect(available).toHaveTextContent("£6.2m");
    expect(available).toHaveTextContent("£0.8m");
    expect(within(available).getByText("Available")).toBeInTheDocument();

    const unavailable = rows[1];
    expect(unavailable).toHaveAttribute("data-state", "unavailable");
    expect(unavailable).toHaveTextContent(/Unavailable: .*money/i);

    const blocked = rows[2];
    expect(blocked).toHaveAttribute("data-state", "blocked_by_later_decision");
    expect(blocked).toHaveTextContent("Blocked by GW11 planned transfer");
  });

  it("describes each unavailable reason code", async () => {
    installApi({
      explorer: buildPlannerExplorerResponse({
        candidates: [
          buildUnavailableCandidate(["club_limit"]),
          buildExplorerCandidate({
            player_id: 104,
            web_name: "Sold Sam",
            state: "unavailable",
            reasons: ["sold_this_gameweek"],
          }),
          buildExplorerCandidate({
            player_id: 105,
            web_name: "Odd Olly",
            state: "unavailable",
            reasons: ["some_new_rule"],
          }),
        ],
      }),
    });
    renderExplorer();

    const table = await screen.findByRole("table");
    expect(table).toHaveTextContent(/Unavailable: .*(three|3) players/i);
    expect(table).toHaveTextContent(/Unavailable: .*sold/i);
    expect(table).toHaveTextContent(/Unavailable: .*some_new_rule/);
  });

  it("shows plan impact with saved plan and assumed continuation labelled and never summed", async () => {
    installApi({});
    renderExplorer();

    const table = await screen.findByRole("table");
    const row = within(table).getAllByRole("row")[1];
    const impact = within(row).getByTestId("plan-impact");

    expect(impact).toHaveTextContent(/saved plan/i);
    expect(impact).toHaveTextContent("+3.5");
    expect(impact).toHaveTextContent(
      "Assumed continuation (no plan decisions)",
    );
    expect(impact).toHaveTextContent("+2.5");
    expect(impact).toHaveTextContent("-0.5");
    expect(impact.textContent).not.toContain("6.0");
    expect(within(impact).getByTestId("impact-saved-plan")).not.toBe(
      within(impact).getByTestId("impact-assumed-continuation"),
    );
  });

  it("does not invent plan impact when the server returned none", async () => {
    installApi({
      explorer: buildPlannerExplorerResponse({
        candidates: [buildUnavailableCandidate()],
      }),
    });
    renderExplorer();

    const row = within(await screen.findByRole("table")).getAllByRole("row")[1];
    expect(within(row).getByTestId("impact-saved-plan")).toHaveTextContent("-");
    expect(within(row).getByTestId("impact-saved-plan")).not.toHaveTextContent(
      "0.0",
    );
  });

  it("shows best-XI gains under horizon labels built from the evaluated gameweeks", async () => {
    installApi({});
    renderExplorer();

    await screen.findByRole("table");
    expect(
      screen.getByRole("columnheader", { name: /Best-XI gain GW9$/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: /Best-XI gain GW9-11/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: /Best-XI gain GW9-13/ }),
    ).toBeInTheDocument();
    const row = screen.getAllByRole("row")[1];
    expect(row).toHaveTextContent("+1.5");
    expect(row).toHaveTextContent("+3.2");
    expect(row).toHaveTextContent("+5.5");
  });

  it("shows advisory playing status without changing the state", async () => {
    installApi({
      explorer: buildPlannerExplorerResponse({
        candidates: [
          buildExplorerCandidate({
            player_id: 110,
            web_name: "Doubtful Dan",
            status: "d",
          }),
        ],
      }),
    });
    renderExplorer();

    const row = within(await screen.findByRole("table")).getAllByRole("row")[1];
    expect(row).toHaveTextContent("Doubtful");
    expect(row).toHaveAttribute("data-state", "available");
  });

  it("explains an empty candidate pool", async () => {
    installApi({
      explorer: buildPlannerExplorerResponse({ candidates: [] }),
    });
    renderExplorer();

    expect(await screen.findByText(/no replacement candidates/i)).toBeVisible();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("surfaces withheld candidates instead of showing them with zero gains", async () => {
    const response = buildPlannerExplorerResponse();
    response.projection.unprojected_candidate_ids = [201, 202];
    installApi({ explorer: response });
    renderExplorer();

    const notice = await screen.findByTestId("withheld-candidates");
    expect(notice).toHaveTextContent(/2 players/i);
    expect(notice).toHaveTextContent(/no complete projection/i);
    expect(notice).toHaveTextContent("#201");
    expect(notice).toHaveTextContent("#202");
    expect(screen.getAllByRole("row")).toHaveLength(4);
  });

  it("offers only a disabled, clearly unavailable Preview in this read-only phase", async () => {
    const fetchSpy = installApi({});
    renderExplorer();

    await screen.findByRole("table");
    const buttons = screen.getAllByRole("button", { name: /preview/i });
    expect(buttons).toHaveLength(3);
    for (const button of buttons) {
      expect(button).toBeDisabled();
      fireEvent.click(button);
    }
    expect(
      fetchSpy.mock.calls.every(
        ([, init]) => (init?.method ?? "GET") === "GET",
      ),
    ).toBe(true);
    expect(routerPush).not.toHaveBeenCalled();
  });
});

describe("PlannerTransferExplorer: outgoing summary", () => {
  it("shows purchase basis, prices, bank and free transfers with estimates flagged", async () => {
    installApi({});
    renderExplorer();

    const summary = await screen.findByRole("region", {
      name: /outgoing player/i,
    });
    expect(summary).toHaveTextContent("P6");
    expect(summary).toHaveTextContent(/Purchase price.*£5\.0m.*Estimated/);
    expect(summary).toHaveTextContent(/Market price.*£5\.4m/);
    expect(summary).toHaveTextContent(/Selling price.*£5\.2m.*Estimated/);
    expect(summary).toHaveTextContent(/Bank before.*£1\.5m/);
    expect(summary).toHaveTextContent(/Free transfers.*2/);
    expect(summary).toHaveTextContent(/Points hit.*0/);
  });

  it("does not flag confirmed purchase prices as estimated", async () => {
    const response = buildPlannerExplorerResponse();
    response.outgoing.purchase_basis = {
      basis_kind: "starting",
      confirmation: "user_confirmed",
    };
    response.outgoing.selling_provisional = false;
    installApi({ explorer: response });
    renderExplorer();

    const summary = await screen.findByRole("region", {
      name: /outgoing player/i,
    });
    expect(summary).not.toHaveTextContent("Estimated");
  });

  it("explains that an edited transfer has no separate selling price", async () => {
    const response = buildPlannerExplorerResponse();
    response.outgoing.operation = "edit_transfer";
    response.outgoing.selling_price_tenths = null;
    installApi({ explorer: response });
    renderExplorer();

    const summary = await screen.findByRole("region", {
      name: /outgoing player/i,
    });
    expect(summary).toHaveTextContent(/replaces a transfer already planned/i);
    expect(within(summary).getByTestId("selling-price")).not.toHaveTextContent(
      "£",
    );
  });

  it("offers a way to choose a different outgoing player", async () => {
    installApi({});
    renderExplorer();

    expect(
      await screen.findByRole("link", { name: /choose a different player/i }),
    ).toHaveAttribute("href", "/transfers?plan=7&gw=9");
  });
});

describe("PlannerTransferExplorer: projection run and coverage", () => {
  it("shows the run badge and pins the run in the address after the first load", async () => {
    installApi({});
    renderExplorer();

    expect(await screen.findByText(/component_v3/)).toBeInTheDocument();
    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith(
        `/transfers?plan=7&gw=9&out=6&h=5&run=${EXPLORER_RUN_ID}`,
      ),
    );
  });

  it("does not rewrite an address that already pins the run", async () => {
    installApi({});
    renderExplorer({ runId: EXPLORER_RUN_ID });

    await screen.findByRole("table");
    expect(routerReplace).not.toHaveBeenCalled();
  });

  it("sends the pinned run with every request", async () => {
    const fetchSpy = installApi({});
    renderExplorer({ runId: 41 });

    await screen.findByRole("table");
    const listCall = fetchSpy.mock.calls
      .map(([input]) => new URL(String(input)))
      .find((url) => url.pathname.includes("/transfers/"));
    expect(listCall?.searchParams.get("projection_run_id")).toBe("41");
  });

  it("announces a newer run without switching to it", async () => {
    const response = buildPlannerExplorerResponse();
    response.projection.newer_run_available = true;
    installApi({ explorer: response });
    renderExplorer({ runId: EXPLORER_RUN_ID });

    const notice = await screen.findByTestId("newer-run-notice");
    expect(notice).toHaveTextContent(/newer projection run is available/i);

    fireEvent.click(
      within(notice).getByRole("button", { name: /use the latest run/i }),
    );
    expect(routerReplace).toHaveBeenCalledWith(
      "/transfers?plan=7&gw=9&out=6&h=5",
    );
  });

  it("always shows evaluated gameweeks for every horizon, split into saved plan and assumed continuation", async () => {
    installApi({});
    renderExplorer();

    const coverage = await screen.findByRole("region", {
      name: /projection coverage/i,
    });
    expect(coverage).toHaveTextContent(/GW9-13 evaluated/);
    expect(coverage).toHaveTextContent(/saved plan GW9-10/i);
    expect(coverage).toHaveTextContent(/assumed continuation GW11-13/i);
    expect(coverage).not.toHaveTextContent(/partial/i);
  });

  it("flags partial coverage and names the gameweeks that could not be projected", async () => {
    const response = buildPlannerExplorerResponse();
    response.projection.horizons = buildExplorerHorizons({
      5: {
        evaluated_gameweeks: [9, 10, 11],
        saved_plan_gameweeks: [9, 10],
        assumed_gameweeks: [11],
        partial: true,
      },
    });
    installApi({ explorer: response });
    renderExplorer();

    const coverage = await screen.findByRole("region", {
      name: /projection coverage/i,
    });
    expect(coverage).toHaveTextContent(/partial coverage/i);
    expect(coverage).toHaveTextContent(/GW12-13 not projected/i);
    expect(
      screen.getByRole("columnheader", {
        name: /Best-XI gain GW9-11 \(partial\)/,
      }),
    ).toBeInTheDocument();
  });

  it("explains that a Free Hit gameweek limits every horizon to the selected gameweek", async () => {
    const response = buildPlannerExplorerResponse();
    response.projection.limited_to_selected_gameweek = true;
    response.projection.limited_reason = "free_hit_gameweek";
    response.projection.horizons = buildExplorerHorizons({
      3: {
        evaluated_gameweeks: [9],
        saved_plan_gameweeks: [9],
        assumed_gameweeks: [],
      },
      5: {
        evaluated_gameweeks: [9],
        saved_plan_gameweeks: [9],
        assumed_gameweeks: [],
      },
    });
    installApi({ explorer: response });
    renderExplorer();

    expect(await screen.findByTestId("free-hit-limit")).toHaveTextContent(
      /Free Hit.*only GW9/i,
    );
  });
});

describe("PlannerTransferExplorer: horizon changes and stale responses", () => {
  it("moves the horizon into the address, keeping the pinned run", async () => {
    installApi({});
    renderExplorer({ runId: EXPLORER_RUN_ID });

    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "3 GWs" }));

    expect(routerReplace).toHaveBeenCalledWith(
      `/transfers?plan=7&gw=9&out=6&h=3&run=${EXPLORER_RUN_ID}`,
    );
  });

  it("requests the chosen horizon so ordering comes from the server", async () => {
    const fetchSpy = installApi({});
    const view = renderExplorer({ runId: EXPLORER_RUN_ID });
    await screen.findByRole("table");

    view.rerenderWith({ horizon: 1, runId: EXPLORER_RUN_ID });

    await waitFor(() => {
      const horizons = fetchSpy.mock.calls
        .map(([input]) => new URL(String(input)))
        .filter((url) => url.pathname.includes("/transfers/"))
        .map((url) => url.searchParams.get("primary_horizon"));
      expect(horizons).toEqual(["5", "1"]);
    });
  });

  it("ignores a stale response that resolves after a newer request", async () => {
    const first = deferred<Response>();
    const second = deferred<Response>();
    const pending = [first, second];
    installApi({
      explorer: () => pending.shift()!.promise,
    });
    const view = renderExplorer({ runId: EXPLORER_RUN_ID });
    await screen.findByRole("status");
    await waitFor(() => expect(pending).toHaveLength(1));

    view.rerenderWith({ horizon: 1, runId: EXPLORER_RUN_ID });
    await waitFor(() => expect(pending).toHaveLength(0));

    const fresh = buildPlannerExplorerResponse({
      candidates: [
        buildExplorerCandidate({ player_id: 301, web_name: "Fresh Fran" }),
      ],
    });
    const stale = buildPlannerExplorerResponse({
      candidates: [
        buildExplorerCandidate({ player_id: 302, web_name: "Stale Stu" }),
      ],
    });
    await act(async () => {
      second.resolve(json(200, fresh));
    });
    await screen.findByText("Fresh Fran");
    await act(async () => {
      first.resolve(json(200, stale));
    });

    expect(screen.getByText("Fresh Fran")).toBeInTheDocument();
    expect(screen.queryByText("Stale Stu")).not.toBeInTheDocument();
  });
});

describe("candidate fixtures used by the explorer tests", () => {
  it("cover each contract state", () => {
    expect(buildAvailableCandidate().state).toBe("available");
    expect(buildUnavailableCandidate().state).toBe("unavailable");
    expect(buildBlockedCandidate().state).toBe("blocked_by_later_decision");
  });
});
