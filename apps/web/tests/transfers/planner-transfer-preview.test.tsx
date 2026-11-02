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

import { StrictMode } from "react";

import { PlannerTransferExplorer } from "@/components/transfers/planner/planner-transfer-explorer";
import type {
  PlanMutationEnvelope,
  PlanResponse,
  PlanTransferExplorerResponse,
  PlanTransferPreviewResponse,
} from "@/lib/api";
import {
  commitDescriptorToIntent,
  type PlannerCommit,
  type PlannerCommitFactory,
  type PlannerCommitView,
} from "@/lib/planner-commit";
import {
  getPlanSaveCoordinator,
  type PinnedSubmission,
} from "@/lib/plan-save-coordinator";

import {
  buildCommitDescriptor,
  buildFinancialBlockedCandidate,
  buildFinancialBlockedPreview,
  buildPlannerExplorerResponse,
  buildPlannerPlan,
  buildPlannerPreviewResponse,
  buildPreviewTotals,
  buildStructuralBlockedPreview,
  buildUnavailablePreview,
  deferred,
  EXPLORER_GAMEWEEK,
  EXPLORER_OUTGOING_ID,
  EXPLORER_RUN_ID,
  forPlan,
} from "../fixtures/planner-explorer";

const { useRouter } = vi.hoisted(() => ({ useRouter: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter }));

const routerPush = vi.fn();
const routerReplace = vi.fn();

const REVISION = 3;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function freshPlan(revision = REVISION): PlanResponse {
  return { ...buildPlannerPlan(9, 14), name: "Run-in plan", revision };
}

type PreviewSource = (
  call: number,
) => PlanTransferPreviewResponse | Response | Promise<Response>;

type Api = {
  plan: PlanResponse;
  previews: Map<number, PreviewSource>;
  previewCalls: number[];
  planReads: number;
  receipts: string[];
  mutations: {
    envelope: PlanMutationEnvelope;
    gate: ReturnType<typeof deferred<Response>>;
  }[];
  /** Replies to a mutation immediately instead of waiting for the test. */
  autoMutation: ((envelope: PlanMutationEnvelope) => Response) | null;
  receiptReply: (() => Response) | null;
  /** The run served when a request does not pin one. */
  latestRun: number;
  listCalls: URL[];
  /** Adjusts a list response in place, or replaces it, by the 1-based number of the list call. */
  listReply:
    | ((
        call: number,
        response: PlanTransferExplorerResponse,
      ) => Response | Promise<Response | void> | void)
    | null;
  spy: MockInstance<typeof fetch>;
};

function previewAt(
  base: PlanTransferPreviewResponse,
  planId: number,
  revision: number,
): PlanTransferPreviewResponse {
  const copy = structuredClone(base);
  forPlan(copy, planId);
  copy.planning_context.revision = revision;
  if (copy.commit) copy.commit.expected_revision = revision;
  return copy;
}

function installApi(plan: PlanResponse = freshPlan()): Api {
  const api: Api = {
    plan,
    previews: new Map(),
    previewCalls: [],
    planReads: 0,
    receipts: [],
    mutations: [],
    autoMutation: null,
    receiptReply: null,
    latestRun: EXPLORER_RUN_ID,
    listCalls: [],
    listReply: null,
    spy: undefined as never,
  };
  const candidates = [
    ...buildPlannerExplorerResponse().candidates,
    buildFinancialBlockedCandidate(),
  ];
  api.previews.set(101, () =>
    previewAt(buildPlannerPreviewResponse(), plan.plan_id, api.plan.revision),
  );
  api.previews.set(102, () =>
    previewAt(buildUnavailablePreview(), plan.plan_id, api.plan.revision),
  );
  api.previews.set(103, () =>
    previewAt(buildStructuralBlockedPreview(), plan.plan_id, api.plan.revision),
  );
  api.previews.set(104, () =>
    previewAt(buildFinancialBlockedPreview(), plan.plan_id, api.plan.revision),
  );
  api.spy = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = init?.method ?? "GET";
        const base = `/plans/${plan.plan_id}`;
        if (method === "POST" && url.pathname === `${base}/mutations`) {
          const envelope = JSON.parse(
            String(init?.body),
          ) as PlanMutationEnvelope;
          if (api.autoMutation) {
            api.mutations.push({ envelope, gate: deferred<Response>() });
            return api.autoMutation(envelope);
          }
          const gate = deferred<Response>();
          api.mutations.push({ envelope, gate });
          return gate.promise;
        }
        if (url.pathname.startsWith(`${base}/mutations/`)) {
          api.receipts.push(url.pathname.split("/").pop()!);
          if (api.receiptReply) return api.receiptReply();
          return json(404, {
            detail: { code: "mutation_not_found", message: "none" },
          });
        }
        if (url.pathname === base) {
          api.planReads += 1;
          return json(200, api.plan);
        }
        if (url.pathname.endsWith("/preview")) {
          const playerIn = Number(url.searchParams.get("player_in_id"));
          api.previewCalls.push(playerIn);
          const source = api.previews.get(playerIn)!;
          const result = await source(
            api.previewCalls.filter((id) => id === playerIn).length,
          );
          if (result instanceof Response) return result;
          result.projection.run_id = Number(
            url.searchParams.get("projection_run_id") ?? api.latestRun,
          );
          return json(200, result);
        }
        if (url.pathname.includes("/transfers/")) {
          const response = forPlan(
            buildPlannerExplorerResponse({ candidates }),
            plan.plan_id,
          );
          response.planning_context.revision = api.plan.revision;
          response.projection.run_id = Number(
            url.searchParams.get("projection_run_id") ?? api.latestRun,
          );
          api.listCalls.push(url);
          const custom = await api.listReply?.(api.listCalls.length, response);
          if (custom instanceof Response) return custom;
          return json(200, response);
        }
        throw new Error(`Unexpected request ${method} ${url.pathname}`);
      },
    );
  return api;
}

function committedBody(
  api: Api,
  envelope: PlanMutationEnvelope,
  revision: number,
) {
  return {
    status: "committed",
    mutation_id: envelope.mutation_id,
    committed_revision: revision,
    plan: { ...api.plan, revision },
    candidate: null,
  };
}

type ExplorerOptions = {
  commit?: PlannerCommitFactory;
  gameweek?: number;
  playerOutId?: number;
  horizon?: 1 | 3 | 5;
  runId?: number | null;
  strict?: boolean;
};

function renderExplorer(api: Api, options: ExplorerOptions = {}) {
  const element = (next: ExplorerOptions) => (
    <PlannerTransferExplorer
      planId={api.plan.plan_id}
      gameweek={next.gameweek ?? options.gameweek ?? EXPLORER_GAMEWEEK}
      playerOutId={
        next.playerOutId ?? options.playerOutId ?? EXPLORER_OUTGOING_ID
      }
      horizon={next.horizon ?? 5}
      runId={next.runId === undefined ? EXPLORER_RUN_ID : next.runId}
      commit={options.commit}
    />
  );
  const wrap = (node: JSX.Element) =>
    options.strict ? <StrictMode>{node}</StrictMode> : node;
  const view = render(wrap(element(options)));
  return {
    ...view,
    rerenderWith: (next: ExplorerOptions) => view.rerender(wrap(element(next))),
  };
}

async function openPreview(name = "Available Alex") {
  fireEvent.click(
    await screen.findByRole("button", { name: `Preview ${name}` }),
  );
  return screen.findByRole("region", { name: "Transfer preview" });
}

function pinned(overrides: Partial<PinnedSubmission> = {}): PinnedSubmission {
  return {
    submissionId: "foreign-1",
    mutationId: "00000000-0000-4000-8000-0000000000f1",
    expectedRevision: REVISION,
    status: "sending",
    committedRevision: null,
    code: null,
    diagnostics: null,
    message: null,
    ...overrides,
  };
}

/** A scripted stand-in for the default adapter, driven one state at a time. */
function createFakeCommit(api: Api, initial: Partial<PlannerCommitView> = {}) {
  let view: PlannerCommitView = {
    plan: api.plan,
    acknowledgedRevision: api.plan.revision,
    idle: true,
    pinned: null,
    label: null,
    details: null,
    ...initial,
  };
  const listeners = new Set<() => void>();
  let counter = 0;
  const set = (next: Partial<PlannerCommitView>) => {
    view = { ...view, ...next };
    listeners.forEach((listener) => listener());
  };
  const fake: PlannerCommit = {
    getView: () => view,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    submit: vi.fn(() => {
      counter += 1;
      return { type: "started" as const, submissionId: `own-${counter}` };
    }),
    retry: vi.fn(),
    reconcile: vi.fn(async () => {}),
    abandon: vi.fn(async () => {
      const previous = view.pinned;
      if (!previous) return { type: "nothing_to_abandon" as const };
      set({ pinned: null });
      return {
        type: "abandoned" as const,
        previous,
        serverReceiptRetained: previous.status === "pending_unsaved",
      };
    }),
    synchronize: vi.fn(),
    hasUnsavedWork: () =>
      view.pinned !== null &&
      ["sending", "unknown", "pending_unsaved", "conflict"].includes(
        view.pinned.status,
      ),
  };
  const factory: PlannerCommitFactory = () => fake;
  return { fake, factory, set };
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

describe("Planner transfer preview", () => {
  it("opens above the candidate table with wording distinct from the confirmation", async () => {
    const api = installApi();
    renderExplorer(api);

    const panel = await openPreview();

    const table = screen.getByRole("table", { name: "Replacement candidates" });
    expect(
      panel.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: /Preview: P6 for Available Alex/ }),
    ).toBeInTheDocument();
    const region = within(panel).getByRole("region", {
      name: "Add to plan GW9",
    });
    expect(
      within(region).getByRole("button", { name: "Confirm transfer" }),
    ).toBeEnabled();
    expect(api.previewCalls).toEqual([101]);
  });

  it("asks the server for the preview on the pinned run and never fetches mutations", async () => {
    const api = installApi();
    renderExplorer(api);
    await openPreview();

    const call = api.spy.mock.calls
      .map(([input]) => new URL(String(input)))
      .find((url) => url.pathname.endsWith("/preview"));
    expect(call?.searchParams.get("projection_run_id")).toBe("42");
    expect(api.mutations).toHaveLength(0);
  });

  it("keeps saved-plan and assumed-continuation gameweeks in separate labelled blocks", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview();

    const saved = within(panel).getByRole("region", {
      name: "Saved plan gameweeks",
    });
    const assumed = within(panel).getByRole("region", {
      name: "Assumed continuation (no plan decisions)",
    });
    expect(
      within(saved)
        .getAllByRole("row")
        .slice(1)
        .map((row) => row.getAttribute("data-gameweek")),
    ).toEqual(["9", "10"]);
    expect(
      within(assumed)
        .getAllByRole("row")
        .slice(1)
        .map((row) => row.getAttribute("data-gameweek")),
    ).toEqual(["11", "12"]);
    expect(
      within(assumed).getByText(/no further decisions/i),
    ).toBeInTheDocument();
  });

  it("shows consequences in later gameweeks: roles, bank, free transfers, hits and points", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview();

    const gw9 = within(panel).getByTestId("preview-gw-9");
    expect(gw9).toHaveTextContent("£1.5m");
    expect(gw9).toHaveTextContent("£0.8m");
    expect(gw9).toHaveTextContent(/starting/i);
    expect(gw9).toHaveTextContent("60.0");
    expect(gw9).toHaveTextContent("62.5");
    expect(gw9).toHaveTextContent("+2.5");
    expect(within(panel).getByTestId("preview-gw-10")).toHaveTextContent(
      /bench/i,
    );
    expect(within(panel).getByTestId("preview-gw-11")).toHaveTextContent(
      /captain/i,
    );
  });

  it("shows totals by horizon with saved plan and assumed continuation never summed", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview();

    const totals = within(panel).getByRole("region", {
      name: "Totals by horizon",
    });
    const row = within(totals).getByTestId("totals-5");
    expect(row).toHaveTextContent("+5.0");
    expect(row).toHaveTextContent("+7.5");
    expect(row).toHaveTextContent("-4");
    expect(row).toHaveTextContent("+1.0");
    expect(totals.textContent).not.toContain("12.5");
    expect(
      within(totals).getByText(/Assumed continuation \(no plan decisions\)/),
    ).toBeInTheDocument();
    expect(within(totals).getByTestId("totals-1")).toHaveTextContent("-");
  });

  it("shows the hit change as its effect on points: extra hits negative, a removed hit positive", async () => {
    const api = installApi();
    const reduced = buildPlannerPreviewResponse();
    reduced.totals["3"] = buildPreviewTotals({
      hit_change: -4,
      net_saved_plan: 9,
      saved_plan: 5,
    });
    reduced.totals["1"] = buildPreviewTotals({
      hit_change: 0,
      net_saved_plan: 5,
      saved_plan: 5,
    });
    api.previews.set(101, () =>
      previewAt(reduced, api.plan.plan_id, api.plan.revision),
    );
    renderExplorer(api);
    const panel = await openPreview();

    const totals = within(panel).getByRole("region", {
      name: "Totals by horizon",
    });
    const hitOf = (key: string) =>
      within(within(totals).getByTestId(`totals-${key}`)).getAllByRole(
        "cell",
      )[2].textContent;
    expect(hitOf("1")).toContain("0");
    expect(hitOf("3")).toContain("+4");
    expect(hitOf("5")).toContain("-4");
  });

  it("tells the manager when a transfer changes the captain", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview();

    expect(within(panel).getByTestId("lineup-effect")).toHaveTextContent(
      /captain/i,
    );
  });

  it("marks partial horizon coverage in the totals", async () => {
    const api = installApi();
    api.previews.set(101, () => {
      const preview = previewAt(
        buildPlannerPreviewResponse(),
        api.plan.plan_id,
        REVISION,
      );
      preview.projection.horizons[2] = {
        ...preview.projection.horizons[2],
        evaluated_gameweeks: [9, 10, 11],
        partial: true,
      };
      return preview;
    });
    renderExplorer(api);
    const panel = await openPreview();

    expect(within(panel).getByTestId("totals-5")).toHaveTextContent(/partial/i);
  });

  it("shows a blocked candidate's valid values and names the clashing gameweek, with no repair", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview("Blocked Ben");

    const conflict = within(panel).getByTestId("preview-conflict");
    expect(conflict).toHaveTextContent("GW11");
    expect(conflict).toHaveTextContent(
      "Ben is sold by a planned transfer in GW11.",
    );
    expect(conflict).toHaveTextContent(/through GW10/i);
    expect(within(panel).getByTestId("preview-gw-9")).toHaveTextContent("+2.5");
    const withheldRow = within(panel).getByTestId("preview-gw-11");
    expect(withheldRow).toHaveTextContent(/not valid/i);
    expect(withheldRow).not.toHaveTextContent("+");
    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeDisabled();
    expect(
      within(panel).queryByRole("button", {
        name: /repair|fix|remove|resolve|replace/i,
      }),
    ).not.toBeInTheDocument();
    expect(api.mutations).toHaveLength(0);
  });

  it("explains a financial shortfall as an overdrawn bank rather than a clashing transfer", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview("Costly Cal");

    const conflict = within(panel).getByTestId("preview-conflict");
    expect(conflict).toHaveTextContent(/overdraw/i);
    expect(conflict).toHaveTextContent("£2.5m");
    expect(conflict).toHaveTextContent(/not a valid gameweek/i);
    expect(conflict).not.toHaveTextContent(/planned transfer/i);
    const shortfall = within(panel).getByTestId("preview-gw-10");
    expect(shortfall).toHaveAttribute("data-valid", "false");
    expect(shortfall).toHaveTextContent("-£2.5m");
    expect(shortfall).toHaveTextContent(/short by £2\.5m/i);
    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeDisabled();
  });

  it("keeps the figures the server retained for a financially invalid gameweek, labelled as an invalid scenario", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview("Costly Cal");

    const shortfall = within(panel).getByTestId("preview-gw-10");
    expect(shortfall).toHaveAttribute("data-valid", "false");
    expect(shortfall).toHaveTextContent("Starting");
    expect(shortfall).toHaveTextContent("61.0");
    expect(shortfall).toHaveTextContent("62.0");
    expect(shortfall).toHaveTextContent("+1.0");
    expect(shortfall).toHaveTextContent(/invalid scenario/i);
    expect(within(panel).getByTestId("preview-gw-9")).not.toHaveTextContent(
      /invalid scenario/i,
    );
  });

  it("labels the totals of a financially blocked candidate as including the unaffordable gameweek", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview("Costly Cal");

    const note = within(panel).getByTestId("totals-invalid-note");
    expect(note).toHaveTextContent(/include GW10, which cannot be afforded/i);
    expect(note).toHaveTextContent(/no later gameweek/i);
    expect(note).toHaveTextContent(/cannot execute/i);
  });

  it("adds no such note to the totals of an available or structurally blocked candidate", async () => {
    const api = installApi();
    renderExplorer(api);
    const available = await openPreview();
    expect(within(available).queryByTestId("totals-invalid-note")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Close preview" }));
    const blocked = await openPreview("Blocked Ben");
    expect(within(blocked).queryByTestId("totals-invalid-note")).toBeNull();
  });

  it("withholds everything the server withheld for dependent later gameweeks of a financial conflict", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview("Costly Cal");

    for (const gameweek of [11, 12]) {
      const row = within(panel).getByTestId(`preview-gw-${gameweek}`);
      expect(row).toHaveAttribute("data-valid", "false");
      expect(row).toHaveTextContent(/not valid/i);
      expect(row.textContent).not.toMatch(/\d+\.\d/);
      expect(row).not.toHaveTextContent(/starting|bench|captain/i);
    }
  });

  it("still withholds the clashing gameweek and later ones of a structural conflict, and labels any figure it is given", async () => {
    const api = installApi();
    api.previews.set(103, () => {
      const preview = previewAt(
        buildStructuralBlockedPreview(),
        api.plan.plan_id,
        REVISION,
      );
      preview.gameweeks[2] = {
        ...preview.gameweeks[2],
        incoming_role: "bench",
        points: { before: 50, after: 51, delta: 1 },
      };
      return preview;
    });
    renderExplorer(api);
    const panel = await openPreview("Blocked Ben");

    const clash = within(panel).getByTestId("preview-gw-11");
    expect(clash).toHaveTextContent("Bench");
    expect(clash).toHaveTextContent("+1.0");
    expect(clash).toHaveTextContent(/invalid scenario/i);
    const later = within(panel).getByTestId("preview-gw-12");
    expect(later.textContent).not.toMatch(/\d+\.\d/);
  });

  it("shows no figures for a structural conflict's gameweeks when the server provides none", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview("Blocked Ben");

    for (const gameweek of [11, 12]) {
      const row = within(panel).getByTestId(`preview-gw-${gameweek}`);
      expect(row).toHaveTextContent(/not valid/i);
      expect(row.textContent).not.toMatch(/\d+\.\d/);
    }
  });

  it("explains an unavailable candidate and keeps Confirm disabled", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview("Unavailable Uri");

    expect(within(panel).getByTestId("preview-state")).toHaveTextContent(
      /3 players from one club/i,
    );
    expect(
      within(panel).getByTestId("confirm-disabled-reason"),
    ).toBeInTheDocument();
    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeDisabled();
  });

  it("explains a preview the server could not produce", async () => {
    const api = installApi();
    api.previews.set(101, () =>
      json(422, {
        detail: {
          code: "missing_projections",
          message: "GW10: fixture not projected",
          missing_player_ids: [101],
        },
      }),
    );
    renderExplorer(api);
    fireEvent.click(
      await screen.findByRole("button", { name: "Preview Available Alex" }),
    );

    const alert = await screen.findByTestId("preview-error");
    expect(alert).toHaveTextContent("GW10: fixture not projected");
    expect(alert).toHaveTextContent("#101");
    expect(
      screen.queryByRole("button", { name: "Confirm transfer" }),
    ).not.toBeInTheDocument();
  });

  it("ignores a stale preview that arrives after a newer one was requested", async () => {
    const api = installApi();
    const first = deferred<Response>();
    api.previews.set(101, () => first.promise);
    const view = renderExplorer(api);
    // First preview is left pending; asking for another replaces it.
    fireEvent.click(
      await screen.findByRole("button", { name: "Preview Available Alex" }),
    );
    await waitFor(() => expect(api.previewCalls).toEqual([101]));
    fireEvent.click(
      screen.getByRole("button", { name: "Preview Blocked Ben" }),
    );
    await screen.findByTestId("preview-conflict");

    await act(async () => {
      first.resolve(
        json(
          200,
          previewAt(buildPlannerPreviewResponse(), api.plan.plan_id, REVISION),
        ),
      );
    });

    expect(
      screen.getByRole("heading", { name: /Preview: P6 for Blocked Ben/ }),
    ).toBeInTheDocument();
    view.unmount();
  });

  it("closes the preview without touching the plan", async () => {
    const api = installApi();
    renderExplorer(api);
    await openPreview();

    fireEvent.click(screen.getByRole("button", { name: "Close preview" }));

    expect(
      screen.queryByRole("region", { name: "Transfer preview" }),
    ).not.toBeInTheDocument();
    expect(api.mutations).toHaveLength(0);
  });
});

describe("Planner transfer confirmation through the commit adapter", () => {
  it("submits the exact server-issued descriptor once and reports sending", async () => {
    const api = installApi();
    const { fake, factory, set } = createFakeCommit(api);
    renderExplorer(api, { commit: factory });
    const panel = await openPreview();

    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    act(() =>
      set({
        pinned: pinned({ submissionId: "own-1", status: "sending" }),
        idle: false,
      }),
    );

    expect(fake.submit).toHaveBeenCalledTimes(1);
    const [descriptor, label] = vi.mocked(fake.submit).mock.calls[0];
    expect(descriptor).toEqual(
      buildCommitDescriptor(101, { expected_revision: REVISION }),
    );
    expect(commitDescriptorToIntent(descriptor)).toMatchObject({
      expected_outgoing_market_tenths: 54,
      expected_incoming_price_tenths: 62,
    });
    expect(label).toMatch(/P6.*Available Alex.*GW9/);
    expect(screen.getByRole("status", { name: /saving/i })).toBeInTheDocument();
    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeDisabled();
  });

  it("disables Confirm when a foreign submission is pinned and says why", async () => {
    const api = installApi();
    const { factory } = createFakeCommit(api, {
      pinned: pinned({ status: "sending" }),
      idle: false,
    });
    renderExplorer(api, { commit: factory });
    const panel = await openPreview();

    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeDisabled();
    expect(
      within(panel).getByTestId("confirm-disabled-reason"),
    ).toHaveTextContent(/still unresolved|already being saved/i);
  });

  it("disables Confirm while the Planner is busy with other edits", async () => {
    const api = installApi();
    const { factory } = createFakeCommit(api, { idle: false });
    renderExplorer(api, { commit: factory });
    const panel = await openPreview();

    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeDisabled();
    expect(
      within(panel).getByTestId("confirm-disabled-reason"),
    ).toHaveTextContent(/saving other changes/i);
  });

  it("marks the preview stale as soon as the acknowledged revision changes", async () => {
    const api = installApi();
    const { fake, factory, set } = createFakeCommit(api);
    renderExplorer(api, { commit: factory });
    const panel = await openPreview();
    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeEnabled();

    act(() => set({ acknowledgedRevision: REVISION + 1 }));

    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeDisabled();
    expect(
      within(panel).getByText("Plan changed, preview again"),
    ).toBeInTheDocument();
    expect(fake.submit).not.toHaveBeenCalled();
  });

  it("previews again after a plan change and enables Confirm only for the fresh revision", async () => {
    const api = installApi();
    const { fake, factory, set } = createFakeCommit(api);
    renderExplorer(api, { commit: factory });
    const panel = await openPreview();
    api.plan = { ...api.plan, revision: REVISION + 1 };
    act(() => set({ acknowledgedRevision: REVISION + 1, plan: api.plan }));

    fireEvent.click(
      within(panel).getByRole("button", { name: "Preview again" }),
    );

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Confirm transfer" }),
      ).toBeEnabled(),
    );
    expect(api.previewCalls).toEqual([101, 101]);
    expect(fake.synchronize).toHaveBeenCalledWith(
      expect.objectContaining({ revision: REVISION + 1 }),
    );
    expect(fake.submit).not.toHaveBeenCalled();
  });

  it("reports success only for its own submission", async () => {
    const api = installApi();
    const { factory, set } = createFakeCommit(api);
    renderExplorer(api, { commit: factory });
    const panel = await openPreview();
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    act(() =>
      set({
        pinned: pinned({ submissionId: "own-1", status: "sending" }),
        idle: false,
      }),
    );
    expect(screen.queryByTestId("commit-success")).not.toBeInTheDocument();

    act(() =>
      set({
        pinned: pinned({
          submissionId: "own-1",
          status: "committed",
          committedRevision: 4,
        }),
        acknowledgedRevision: 4,
        idle: true,
      }),
    );

    const success = await screen.findByTestId("commit-success");
    expect(success).toHaveTextContent(/Transfer added to your plan/);
    expect(success).toHaveTextContent("Available Alex");
    expect(
      within(success).getByRole("link", { name: /back to plan/i }),
    ).toHaveAttribute("href", `/plans/${api.plan.plan_id}?gw=9`);
    expect(routerPush).toHaveBeenCalledTimes(1);
    expect(routerPush).toHaveBeenCalledWith(
      `/plans/${api.plan.plan_id}?gw=9&highlight=101`,
    );
  });

  it("does not report success for a committed submission it did not start", async () => {
    const api = installApi();
    const { fake, factory } = createFakeCommit(api, {
      pinned: pinned({
        submissionId: "someone-else",
        status: "committed",
        committedRevision: 4,
      }),
    });
    renderExplorer(api, { commit: factory });

    await waitFor(() => expect(fake.abandon).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("commit-success")).not.toBeInTheDocument();
    expect(await screen.findByTestId("commit-earlier")).toHaveTextContent(
      /earlier/i,
    );
    expect(routerPush).not.toHaveBeenCalled();
    expect(fake.submit).not.toHaveBeenCalled();
  });

  it("shows a rejection found on mount once, clears it and never submits", async () => {
    const api = installApi();
    const { fake, factory } = createFakeCommit(api, {
      pinned: pinned({
        submissionId: "old",
        status: "rejected",
        code: "prices_changed",
        message: "Prices changed since the preview",
      }),
    });
    renderExplorer(api, { commit: factory });

    const notice = await screen.findByTestId("commit-earlier");
    expect(notice).toHaveTextContent("Prices changed since the preview");
    await waitFor(() => expect(fake.abandon).toHaveBeenCalledTimes(1));
    expect(fake.submit).not.toHaveBeenCalled();
    expect(routerPush).not.toHaveBeenCalled();
  });

  it("keeps a rejection's message above a fresh preview and needs a new explicit confirmation", async () => {
    const api = installApi();
    const { fake, factory, set } = createFakeCommit(api);
    renderExplorer(api, { commit: factory });
    const panel = await openPreview();
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    api.previews.set(101, () => {
      const preview = previewAt(
        buildPlannerPreviewResponse(),
        api.plan.plan_id,
        REVISION,
      );
      preview.candidate.price_tenths = 64;
      return preview;
    });

    act(() =>
      set({
        pinned: pinned({
          submissionId: "own-1",
          status: "rejected",
          code: "prices_changed",
          message: "Prices changed since you previewed this transfer",
        }),
      }),
    );

    const rejection = await screen.findByTestId("commit-rejection");
    expect(rejection).toHaveTextContent(
      "Prices changed since you previewed this transfer",
    );
    await waitFor(() => expect(fake.abandon).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.previewCalls).toEqual([101, 101]));
    const fresh = await screen.findByRole("region", {
      name: "Transfer preview",
    });
    expect(
      rejection.compareDocumentPosition(fresh) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(fake.submit).toHaveBeenCalledTimes(1);

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Confirm transfer" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm transfer" }));
    expect(fake.submit).toHaveBeenCalledTimes(2);
  });

  it("clears the rejection message when the manager picks another candidate", async () => {
    const api = installApi();
    const { factory, set } = createFakeCommit(api);
    renderExplorer(api, { commit: factory });
    const panel = await openPreview();
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    act(() =>
      set({
        pinned: pinned({
          submissionId: "own-1",
          status: "rejected",
          message: "Not added",
        }),
      }),
    );
    await screen.findByTestId("commit-rejection");

    fireEvent.click(
      await screen.findByRole("button", { name: "Preview Blocked Ben" }),
    );

    await waitFor(() =>
      expect(screen.queryByTestId("commit-rejection")).not.toBeInTheDocument(),
    );
  });

  it("offers check and retry for an unknown outcome and never offers to stop tracking it", async () => {
    const api = installApi();
    const { fake, factory, set } = createFakeCommit(api);
    renderExplorer(api, { commit: factory });
    const panel = await openPreview();
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    act(() =>
      set({
        pinned: pinned({
          submissionId: "own-1",
          status: "unknown",
          message: "Network failure",
        }),
        idle: false,
      }),
    );

    const status = await screen.findByTestId("commit-unknown");
    fireEvent.click(
      within(status).getByRole("button", { name: "Check save status" }),
    );
    fireEvent.click(
      within(status).getByRole("button", { name: "Retry same transfer" }),
    );

    expect(fake.reconcile).toHaveBeenCalledTimes(1);
    expect(fake.retry).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByRole("button", {
        name: /stop tracking|refresh and preview/i,
      }),
    ).not.toBeInTheDocument();
    expect(fake.abandon).not.toHaveBeenCalled();
    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeDisabled();
  });

  it("offers a refresh after a conflict, abandoning and previewing again from fresh data", async () => {
    const api = installApi();
    const { fake, factory, set } = createFakeCommit(api);
    renderExplorer(api, { commit: factory });
    const panel = await openPreview();
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    act(() =>
      set({
        pinned: pinned({
          submissionId: "own-1",
          status: "conflict",
          message: "Plan revision has advanced",
        }),
        idle: false,
      }),
    );
    api.plan = { ...api.plan, revision: REVISION + 1 };

    const region = await screen.findByTestId("commit-conflict");
    expect(region).toHaveTextContent("Plan revision has advanced");
    fireEvent.click(
      within(region).getByRole("button", { name: "Refresh and preview again" }),
    );

    await waitFor(() => expect(fake.abandon).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.previewCalls).toEqual([101, 101]));
    expect(fake.synchronize).toHaveBeenCalled();
    expect(fake.submit).toHaveBeenCalledTimes(1);
  });

  it("warns before stopping tracking an accepted-but-not-saved transfer, then shows the not-added notice", async () => {
    const api = installApi();
    const { fake, factory, set } = createFakeCommit(api);
    renderExplorer(api, { commit: factory });
    const panel = await openPreview();
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    act(() =>
      set({
        pinned: pinned({
          submissionId: "own-1",
          status: "pending_unsaved",
          message: "Accepted edit is not saved; retry the same edit",
        }),
        idle: false,
      }),
    );

    const region = await screen.findByTestId("commit-pending");
    expect(
      within(region).getByRole("button", { name: "Retry same transfer" }),
    ).toBeInTheDocument();
    expect(
      within(region).getByRole("button", { name: "Check save status" }),
    ).toBeInTheDocument();
    expect(region).toHaveTextContent(
      "The server accepted this transfer but could not save it. If you stop tracking it, it will not be added to your plan and this app will not retry it. The server may keep a pending record of it, which is not a saved transfer.",
    );
    expect(fake.abandon).not.toHaveBeenCalled();

    fireEvent.click(
      within(region).getByRole("button", {
        name: "Stop tracking this transfer",
      }),
    );

    const notice = await screen.findByTestId("not-added-notice");
    expect(notice).toHaveTextContent(
      "Transfer not added to your plan. The server may still hold a pending record of it; that record is not a saved transfer and this app will not retry it.",
    );
    expect(fake.abandon).toHaveBeenCalledTimes(1);
    expect(fake.submit).toHaveBeenCalledTimes(1);
    expect(routerPush).not.toHaveBeenCalled();
    expect(screen.queryByTestId("commit-success")).not.toBeInTheDocument();
    // Only the contract's negated wording may mention saving, cancelling, deleting or removing.
    const withoutPermitted = (notice.textContent ?? "")
      .replace("not a saved transfer", "")
      .replace("not added", "");
    expect(withoutPermitted).not.toMatch(/saved|cancel|delet|remov|discard/i);
    expect(
      screen.queryByRole("region", { name: "Transfer preview" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Confirm transfer" }),
    ).not.toBeInTheDocument();
  });
});

describe("Planner transfer confirmation through the real coordinator", () => {
  async function confirm(panel: HTMLElement) {
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
  }

  it("sends one request pinned to the previewed revision and reports success only after its acknowledgement", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview();

    await confirm(panel);
    await waitFor(() => expect(api.mutations).toHaveLength(1));
    const { envelope, gate } = api.mutations[0];
    expect(envelope.expected_revision).toBe(REVISION);
    expect(envelope.intents).toEqual([
      commitDescriptorToIntent(
        buildCommitDescriptor(101, { expected_revision: REVISION }),
      ),
    ]);
    expect(screen.getByRole("status", { name: /saving/i })).toBeInTheDocument();
    expect(screen.queryByTestId("commit-success")).not.toBeInTheDocument();
    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeDisabled();

    await act(async () => {
      gate.resolve(json(200, committedBody(api, envelope, REVISION + 1)));
    });

    expect(await screen.findByTestId("commit-success")).toBeInTheDocument();
    const snapshot = getPlanSaveCoordinator(api.plan).getSnapshot();
    expect(snapshot.pinned).toBeNull();
    expect(snapshot.acknowledged.revision).toBe(REVISION + 1);
    expect(routerPush).toHaveBeenCalledTimes(1);
    expect(routerPush).toHaveBeenCalledWith(
      `/plans/${api.plan.plan_id}?gw=9&highlight=101`,
    );
  });

  it("sends once when Confirm is clicked twice", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview();
    const button = within(panel).getByRole("button", {
      name: "Confirm transfer",
    });

    fireEvent.click(button);
    fireEvent.click(button);

    await waitFor(() => expect(api.mutations).toHaveLength(1));
    expect(api.mutations).toHaveLength(1);
  });

  it("does not submit against a newer revision after a competing Planner edit commits", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview();
    api.autoMutation = (envelope) =>
      json(200, committedBody(api, envelope, REVISION + 1));

    act(() => {
      getPlanSaveCoordinator(api.plan).enqueue([
        { kind: "set_starting_transfers", value: 2 },
      ]);
    });
    await waitFor(() => expect(api.mutations).toHaveLength(1));
    await waitFor(() =>
      expect(
        getPlanSaveCoordinator(api.plan).getSnapshot().acknowledged.revision,
      ).toBe(REVISION + 1),
    );

    expect(
      await within(panel).findByText("Plan changed, preview again"),
    ).toBeInTheDocument();
    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeDisabled();
    expect(api.mutations).toHaveLength(1);
    expect(api.mutations[0].envelope.intents[0].kind).toBe(
      "set_starting_transfers",
    );
  });

  it("recovers from prices_changed: message kept, record cleared, fresh preview, explicit second confirm with a new identity", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview();
    api.previews.set(101, () => {
      const preview = previewAt(
        buildPlannerPreviewResponse(),
        api.plan.plan_id,
        REVISION,
      );
      preview.candidate.price_tenths = 64;
      if (preview.commit)
        preview.commit.guard.expected_incoming_price_tenths = 64;
      return preview;
    });
    await confirm(panel);
    await waitFor(() => expect(api.mutations).toHaveLength(1));
    const first = api.mutations[0];

    await act(async () => {
      first.gate.resolve(
        json(422, {
          detail: {
            code: "prices_changed",
            message: "Prices changed since you previewed this transfer",
            diagnostics: [],
          },
        }),
      );
    });

    const rejection = await screen.findByTestId("commit-rejection");
    expect(rejection).toHaveTextContent(
      "Prices changed since you previewed this transfer",
    );
    await waitFor(() => expect(api.previewCalls).toEqual([101, 101]));
    expect(getPlanSaveCoordinator(api.plan).getSnapshot().pinned).toBeNull();
    expect(api.mutations).toHaveLength(1);
    expect(await screen.findByText("£6.4m")).toBeInTheDocument();

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Confirm transfer" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm transfer" }));
    await waitFor(() => expect(api.mutations).toHaveLength(2));
    expect(api.mutations[1].envelope.mutation_id).not.toBe(
      first.envelope.mutation_id,
    );
    expect(api.mutations[1].envelope.intents[0]).toMatchObject({
      expected_incoming_price_tenths: 64,
    });
  });

  it("treats a network failure as unknown, checks by identity and retries the same identity", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview();
    await confirm(panel);
    await waitFor(() => expect(api.mutations).toHaveLength(1));
    const first = api.mutations[0];

    await act(async () => {
      first.gate.reject(new TypeError("Failed to fetch"));
    });
    const unknown = await screen.findByTestId("commit-unknown");
    expect(screen.queryByTestId("commit-success")).not.toBeInTheDocument();

    fireEvent.click(
      within(unknown).getByRole("button", { name: "Check save status" }),
    );
    await waitFor(() =>
      expect(api.receipts).toEqual([first.envelope.mutation_id]),
    );
    expect(await screen.findByTestId("commit-unknown")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry same transfer" }),
    );
    await waitFor(() => expect(api.mutations).toHaveLength(2));
    expect(api.mutations[1].envelope.mutation_id).toBe(
      first.envelope.mutation_id,
    );
    expect(api.mutations[1].envelope.expected_revision).toBe(REVISION);
  });

  it("requires a fresh preview after a conflict and never replays the transfer", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview();
    await confirm(panel);
    await waitFor(() => expect(api.mutations).toHaveLength(1));
    api.plan = { ...api.plan, revision: REVISION + 1 };

    await act(async () => {
      api.mutations[0].gate.resolve(
        json(409, {
          detail: {
            code: "revision_conflict",
            message: "Plan revision has advanced",
            plan: api.plan,
          },
        }),
      );
    });
    const conflict = await screen.findByTestId("commit-conflict");
    fireEvent.click(
      within(conflict).getByRole("button", {
        name: "Refresh and preview again",
      }),
    );

    await waitFor(() => expect(api.previewCalls).toEqual([101, 101]));
    expect(getPlanSaveCoordinator(api.plan).getSnapshot().pinned).toBeNull();
    const fresh = await screen.findByRole("region", {
      name: "Transfer preview",
    });
    expect(
      within(fresh).getByRole("button", { name: "Confirm transfer" }),
    ).toBeEnabled();
    expect(api.mutations).toHaveLength(1);
  });

  it("stops tracking an accepted-but-not-saved transfer client-side only", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview();
    await confirm(panel);
    await waitFor(() => expect(api.mutations).toHaveLength(1));
    await act(async () => {
      api.mutations[0].gate.resolve(
        json(503, {
          detail: {
            code: "accepted_not_saved",
            message: "The edit was accepted but not saved",
            plan: api.plan,
            candidate: null,
          },
        }),
      );
    });
    const pending = await screen.findByTestId("commit-pending");
    const readsBefore = api.planReads;

    fireEvent.click(
      within(pending).getByRole("button", {
        name: "Stop tracking this transfer",
      }),
    );

    expect(await screen.findByTestId("not-added-notice")).toBeInTheDocument();
    expect(api.mutations).toHaveLength(1);
    expect(api.receipts).toEqual([]);
    expect(api.planReads).toBeGreaterThan(readsBefore);
    const snapshot = getPlanSaveCoordinator(api.plan).getSnapshot();
    expect(snapshot.pinned).toBeNull();
    expect(snapshot.acknowledged.revision).toBe(REVISION);
    expect(screen.queryByTestId("commit-success")).not.toBeInTheDocument();
  });

  it("is refused while another Planner edit is in flight and sends nothing", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview();

    act(() => {
      getPlanSaveCoordinator(api.plan).enqueue([
        { kind: "set_starting_transfers", value: 2 },
      ]);
    });

    await waitFor(() =>
      expect(
        within(panel).getByRole("button", { name: "Confirm transfer" }),
      ).toBeDisabled(),
    );
    expect(
      within(panel).getByTestId("confirm-disabled-reason"),
    ).toHaveTextContent(/saving other changes/i);
    expect(api.mutations).toHaveLength(1);
  });
});

describe("Planner transfer confirmation after navigating away", () => {
  it("shows an unresolved submission again, with its actions, when the Explorer is reopened", async () => {
    const api = installApi();
    const first = renderExplorer(api);
    const panel = await openPreview();
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    await waitFor(() => expect(api.mutations).toHaveLength(1));
    await act(async () => {
      api.mutations[0].gate.resolve(
        json(503, {
          detail: {
            code: "accepted_not_saved",
            message: "The edit was accepted but not saved",
            plan: api.plan,
            candidate: null,
          },
        }),
      );
    });
    await screen.findByTestId("commit-pending");
    first.unmount();

    renderExplorer(api);

    const region = await screen.findByRole("region", {
      name: "Unresolved transfer confirmation",
    });
    expect(region).toHaveTextContent("P6 to Available Alex in GW9");
    expect(
      within(region).getByRole("button", {
        name: "Stop tracking this transfer",
      }),
    ).toBeInTheDocument();
    expect(
      within(region).getByRole("button", { name: "Retry same transfer" }),
    ).toBeInTheDocument();
    expect(api.mutations).toHaveLength(1);
    expect(screen.queryByTestId("commit-success")).not.toBeInTheDocument();
  });
});

describe("Planner transfer preview and the selected projection run", () => {
  const regionName = { name: "Transfer preview" };

  it("invalidates the open preview when the run changes and submits nothing", async () => {
    const api = installApi();
    const view = renderExplorer(api);
    await openPreview();

    view.rerenderWith({ runId: 43 });

    await waitFor(() =>
      expect(screen.queryByRole("region", regionName)).not.toBeInTheDocument(),
    );
    await screen.findByRole("table");
    expect(api.listCalls.at(-1)?.searchParams.get("projection_run_id")).toBe(
      "43",
    );
    expect(screen.queryByRole("region", regionName)).not.toBeInTheDocument();
    expect(api.previewCalls).toEqual([101]);
    expect(api.mutations).toHaveLength(0);
  });

  it("ignores a late preview response from the previous run", async () => {
    const api = installApi();
    const late = deferred<Response>();
    api.previews.set(101, () => late.promise);
    const view = renderExplorer(api);
    fireEvent.click(
      await screen.findByRole("button", { name: "Preview Available Alex" }),
    );
    await waitFor(() => expect(api.previewCalls).toEqual([101]));

    view.rerenderWith({ runId: 43 });
    await screen.findByRole("table");
    await act(async () => {
      late.resolve(
        json(
          200,
          previewAt(buildPlannerPreviewResponse(), api.plan.plan_id, REVISION),
        ),
      );
    });

    expect(screen.queryByRole("region", regionName)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Confirm transfer" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Loading preview...")).not.toBeInTheDocument();
    expect(api.mutations).toHaveLength(0);
  });

  it("previews again on the new run, and only that preview can be confirmed", async () => {
    const api = installApi();
    const view = renderExplorer(api);
    await openPreview();
    view.rerenderWith({ runId: 43 });
    await screen.findByRole("table");

    fireEvent.click(
      screen.getByRole("button", { name: "Preview Available Alex" }),
    );

    const panel = await screen.findByRole("region", regionName);
    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeEnabled();
    const last = api.spy.mock.calls
      .map(([input]) => new URL(String(input)))
      .filter((url) => url.pathname.endsWith("/preview"))
      .at(-1);
    expect(last?.searchParams.get("projection_run_id")).toBe("43");
  });

  it("invalidates the preview when the latest run replaces the pinned one", async () => {
    const api = installApi();
    const view = renderExplorer(api);
    await openPreview();
    api.latestRun = 99;

    view.rerenderWith({ runId: null });

    await screen.findByRole("table");
    await waitFor(() =>
      expect(screen.queryByRole("region", regionName)).not.toBeInTheDocument(),
    );
    expect(screen.getByText(/component_v3/)).toBeInTheDocument();
    expect(api.mutations).toHaveLength(0);
  });

  it("disables Confirm unless the preview was made on the selected run", async () => {
    const api = installApi();
    api.previews.set(101, () => {
      const preview = previewAt(
        buildPlannerPreviewResponse(),
        api.plan.plan_id,
        REVISION,
      );
      preview.projection.run_id = 41;
      return json(200, preview);
    });
    renderExplorer(api);

    const panel = await openPreview();

    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeDisabled();
    expect(
      within(panel).getByTestId("confirm-disabled-reason"),
    ).toHaveTextContent(/projection run/i);
    expect(
      within(panel).getByRole("button", { name: "Preview again" }),
    ).toBeInTheDocument();
    expect(api.mutations).toHaveLength(0);
  });

  it("keeps the preview, its run and Confirm when only the horizon changes", async () => {
    const api = installApi();
    const view = renderExplorer(api);
    await openPreview();

    view.rerenderWith({ horizon: 3, runId: EXPLORER_RUN_ID });

    await screen.findByRole("table", { name: "Replacement candidates" });
    const panel = screen.getByRole("region", regionName);
    expect(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    ).toBeEnabled();
    expect(api.previewCalls).toEqual([101]);
    expect(api.listCalls.at(-1)?.searchParams.get("projection_run_id")).toBe(
      "42",
    );
    expect(api.listCalls.at(-1)?.searchParams.get("primary_horizon")).toBe("3");
  });
});

describe("Planner unresolved submissions stay with their own transfer", () => {
  const LABEL = "P6 to Available Alex in GW9";
  const unresolved = { name: "Unresolved transfer confirmation" };

  async function submitThenSwitch(
    status: "sending" | "unknown" | "pending_unsaved" | "conflict",
  ) {
    const api = installApi();
    const harness = createFakeCommit(api);
    renderExplorer(api, { commit: harness.factory });
    const panel = await openPreview();
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    act(() =>
      harness.set({
        pinned: pinned({
          submissionId: "own-1",
          status,
          message: "Server said so",
        }),
        idle: false,
        label: LABEL,
      }),
    );
    const region = await screen.findByRole("region", unresolved);
    fireEvent.click(
      screen.getByRole("button", { name: "Preview Blocked Ben" }),
    );
    const other = await screen.findByRole("region", {
      name: "Transfer preview",
    });
    await screen.findByRole("heading", { name: /for Blocked Ben/ });
    return { api, ...harness, region, other };
  }

  it.each(["sending", "unknown", "pending_unsaved", "conflict"] as const)(
    "names the transfer in its own region while %s and keeps its controls out of another candidate's preview",
    async (status) => {
      const { other, region } = await submitThenSwitch(status);

      expect(region).toHaveTextContent(LABEL);
      expect(screen.getByRole("region", unresolved)).toHaveTextContent(LABEL);
      for (const id of [
        "commit-unknown",
        "commit-pending",
        "commit-conflict",
      ]) {
        expect(within(other).queryByTestId(id)).not.toBeInTheDocument();
      }
      expect(
        within(other).queryByRole("button", {
          name: /retry same|check save|stop tracking|refresh and preview/i,
        }),
      ).not.toBeInTheDocument();
      expect(
        within(other).getByRole("button", { name: "Confirm transfer" }),
      ).toBeDisabled();
      expect(
        within(other).getByTestId("confirm-disabled-reason"),
      ).toHaveTextContent(LABEL);
    },
  );

  it("reports a transfer that is still sending as a status of that transfer", async () => {
    await submitThenSwitch("sending");

    expect(
      within(screen.getByRole("region", unresolved)).getByRole("status", {
        name: /saving/i,
      }),
    ).toBeInTheDocument();
  });

  it("retries and checks the same submission from its own region", async () => {
    const { fake, region } = await submitThenSwitch("unknown");

    fireEvent.click(
      within(region).getByRole("button", { name: "Check save status" }),
    );
    fireEvent.click(
      within(region).getByRole("button", { name: "Retry same transfer" }),
    );

    expect(fake.reconcile).toHaveBeenCalledTimes(1);
    expect(fake.retry).toHaveBeenCalledTimes(1);
    expect(fake.submit).toHaveBeenCalledTimes(1);
    expect(
      within(region).queryByRole("button", { name: /stop tracking/i }),
    ).not.toBeInTheDocument();
    expect(fake.abandon).not.toHaveBeenCalled();
  });

  it("stops tracking only the unresolved transfer and leaves the open preview alone", async () => {
    const { fake, region } = await submitThenSwitch("pending_unsaved");
    expect(region).toHaveTextContent(/stop tracking it, it will not be added/i);

    fireEvent.click(
      within(region).getByRole("button", {
        name: "Stop tracking this transfer",
      }),
    );

    const notice = await screen.findByTestId("not-added-notice");
    expect(notice).toHaveTextContent(LABEL);
    expect(notice).toHaveTextContent(
      "Transfer not added to your plan. The server may still hold a pending record of it; that record is not a saved transfer and this app will not retry it.",
    );
    expect(fake.abandon).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("heading", { name: /for Blocked Ben/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("region", unresolved)).not.toBeInTheDocument();
  });

  it("refreshes after a conflict by previewing the transfer that conflicted", async () => {
    const { api, fake, region } = await submitThenSwitch("conflict");

    fireEvent.click(
      within(region).getByRole("button", { name: "Refresh and preview again" }),
    );

    await waitFor(() => expect(fake.abandon).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.previewCalls.at(-1)).toBe(101));
    await screen.findByRole("heading", { name: /for Available Alex/ });
  });

  it("keeps same-identity retry working after switching candidates with the real coordinator", async () => {
    const api = installApi();
    renderExplorer(api);
    const panel = await openPreview();
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    await waitFor(() => expect(api.mutations).toHaveLength(1));
    await act(async () => {
      api.mutations[0].gate.reject(new TypeError("Failed to fetch"));
    });
    const region = await screen.findByRole("region", unresolved);
    expect(region).toHaveTextContent(LABEL);

    fireEvent.click(
      screen.getByRole("button", { name: "Preview Blocked Ben" }),
    );
    await screen.findByRole("heading", { name: /for Blocked Ben/ });
    fireEvent.click(
      within(screen.getByRole("region", unresolved)).getByRole("button", {
        name: "Retry same transfer",
      }),
    );

    await waitFor(() => expect(api.mutations).toHaveLength(2));
    expect(api.mutations[1].envelope.mutation_id).toBe(
      api.mutations[0].envelope.mutation_id,
    );
    expect(api.mutations[1].envelope.intents).toEqual(
      api.mutations[0].envelope.intents,
    );
  });

  it("does not replace another candidate's preview when a rejection arrives for the earlier transfer", async () => {
    const api = installApi();
    const harness = createFakeCommit(api);
    renderExplorer(api, { commit: harness.factory });
    const panel = await openPreview();
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    act(() =>
      harness.set({
        pinned: pinned({ submissionId: "own-1", status: "sending" }),
        idle: false,
        label: LABEL,
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Preview Blocked Ben" }),
    );
    await screen.findByRole("heading", { name: /for Blocked Ben/ });

    act(() =>
      harness.set({
        pinned: pinned({
          submissionId: "own-1",
          status: "rejected",
          message: "Prices changed",
          code: "prices_changed",
        }),
        idle: true,
      }),
    );

    const rejection = await screen.findByTestId("commit-rejection");
    expect(rejection).toHaveTextContent(LABEL);
    expect(rejection).toHaveTextContent("Prices changed");
    expect(
      screen.getByRole("heading", { name: /for Blocked Ben/ }),
    ).toBeInTheDocument();
    expect(api.previewCalls).toEqual([101, 103]);
  });
});

describe("Planner Explorer navigation and departure protection", () => {
  const WARNING =
    "Your latest Planner edit is not saved yet. Leave this page anyway?";
  const noticeKey = (api: Api) => `plannerTransferNotice:${api.plan.plan_id}`;
  const documentListeners: [string, EventListener][] = [];
  const onDocument = (type: string, listener: EventListener) => {
    document.addEventListener(type, listener);
    documentListeners.push([type, listener]);
  };

  beforeEach(() => {
    window.sessionStorage.clear();
    window.history.replaceState({}, "", "/transfers");
  });

  afterEach(() => {
    window.sessionStorage.clear();
    for (const [type, listener] of documentListeners.splice(0)) {
      document.removeEventListener(type, listener);
    }
  });

  async function confirmOwn(api: Api, options: ExplorerOptions = {}) {
    const view = renderExplorer(api, options);
    const panel = await openPreview();
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    await waitFor(() => expect(api.mutations).toHaveLength(1));
    return view;
  }

  it("navigates to the plan with the incoming player only after its own commit is acknowledged", async () => {
    const api = installApi();
    await confirmOwn(api);
    expect(routerPush).not.toHaveBeenCalled();
    const { envelope, gate } = api.mutations[0];

    await act(async () => {
      gate.resolve(json(200, committedBody(api, envelope, REVISION + 1)));
    });

    await waitFor(() => expect(routerPush).toHaveBeenCalledTimes(1));
    expect(routerPush).toHaveBeenCalledWith(
      `/plans/${api.plan.plan_id}?gw=9&highlight=101`,
    );
    expect(getPlanSaveCoordinator(api.plan).getSnapshot().pinned).toBeNull();
    expect(
      JSON.parse(window.sessionStorage.getItem(noticeKey(api)) ?? "null"),
    ).toEqual({
      message: "Transferred P6 for Available Alex in GW9",
      gameweek: 9,
      incomingPlayerId: 101,
    });
    expect(screen.getByTestId("commit-success")).toHaveTextContent(
      /P6.*Available Alex.*GW9/,
    );
  });

  it("navigates exactly once under React Strict Mode and across rerenders", async () => {
    const api = installApi();
    const view = await confirmOwn(api, { strict: true });
    const { envelope, gate } = api.mutations[0];

    await act(async () => {
      gate.resolve(json(200, committedBody(api, envelope, REVISION + 1)));
    });
    await waitFor(() => expect(routerPush).toHaveBeenCalledTimes(1));
    view.rerenderWith({ horizon: 3, runId: EXPLORER_RUN_ID, strict: true });
    view.rerenderWith({ horizon: 1, runId: EXPLORER_RUN_ID, strict: true });
    await act(async () => {
      await Promise.resolve();
    });

    expect(routerPush).toHaveBeenCalledTimes(1);
  });

  it("does not navigate because an unrelated revision arrived while sending", async () => {
    const api = installApi();
    await confirmOwn(api);

    act(() => {
      getPlanSaveCoordinator(api.plan).synchronize({
        ...api.plan,
        revision: REVISION + 1,
      });
    });

    expect(routerPush).not.toHaveBeenCalled();
    expect(getPlanSaveCoordinator(api.plan).getSnapshot().pinned?.status).toBe(
      "sending",
    );
    expect(window.sessionStorage.getItem(noticeKey(api))).toBeNull();
  });

  it("does not navigate when another submission's record is acknowledged as committed", async () => {
    const api = installApi();
    const { factory, set } = createFakeCommit(api);
    renderExplorer(api, { commit: factory });
    const panel = await openPreview();
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    act(() =>
      set({
        pinned: pinned({ submissionId: "someone-else", status: "committed" }),
      }),
    );

    await screen.findByTestId("commit-earlier");
    expect(routerPush).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem(noticeKey(api))).toBeNull();
  });

  it.each([
    "unknown",
    "pending_unsaved",
    "conflict",
    "rejected",
    "plan_missing",
  ] as const)(
    "never navigates automatically for an own submission that is %s",
    async (status) => {
      const api = installApi();
      const { factory, set } = createFakeCommit(api);
      renderExplorer(api, { commit: factory });
      const panel = await openPreview();
      fireEvent.click(
        within(panel).getByRole("button", { name: "Confirm transfer" }),
      );

      act(() =>
        set({
          pinned: pinned({ submissionId: "own-1", status, message: "no" }),
          idle: status === "rejected" || status === "plan_missing",
        }),
      );
      await act(async () => {
        await Promise.resolve();
      });

      expect(routerPush).not.toHaveBeenCalled();
      expect(routerReplace).not.toHaveBeenCalledWith(
        expect.stringContaining("/plans/"),
      );
      expect(window.sessionStorage.getItem(noticeKey(api))).toBeNull();
    },
  );

  it.each(["committed", "rejected", "plan_missing"] as const)(
    "shows a %s record found on mount once, clears it and neither navigates nor submits",
    async (status) => {
      const api = installApi();
      const { fake, factory } = createFakeCommit(api, {
        pinned: pinned({ submissionId: "old", status, message: "Earlier" }),
      });
      renderExplorer(api, { commit: factory });

      await screen.findByTestId("commit-earlier");
      await waitFor(() => expect(fake.abandon).toHaveBeenCalledTimes(1));

      expect(routerPush).not.toHaveBeenCalled();
      expect(fake.submit).not.toHaveBeenCalled();
      expect(window.sessionStorage.getItem(noticeKey(api))).toBeNull();
    },
  );

  it("keeps an unresolved submission, with its identity, when the Explorer unmounts and returns", async () => {
    const api = installApi();
    const first = await confirmOwn(api);
    const original = api.mutations[0].envelope.mutation_id;
    await act(async () => {
      api.mutations[0].gate.reject(new TypeError("Failed to fetch"));
    });
    await screen.findByTestId("commit-unknown");

    first.unmount();

    const coordinator = getPlanSaveCoordinator(api.plan);
    expect(coordinator.getSnapshot().pinned?.status).toBe("unknown");
    expect(coordinator.hasUnsavedWork()).toBe(true);
    renderExplorer(api);
    const region = await screen.findByRole("region", {
      name: "Unresolved transfer confirmation",
    });
    fireEvent.click(
      within(region).getByRole("button", { name: "Check save status" }),
    );
    await waitFor(() => expect(api.receipts).toEqual([original]));
    fireEvent.click(
      within(
        screen.getByRole("region", {
          name: "Unresolved transfer confirmation",
        }),
      ).getByRole("button", { name: "Retry same transfer" }),
    );
    await waitFor(() => expect(api.mutations).toHaveLength(2));
    expect(api.mutations[1].envelope.mutation_id).toBe(original);
  });

  it("navigates when a returned Explorer's retry of its own earlier submission commits", async () => {
    const api = installApi();
    const first = await confirmOwn(api);
    const original = api.mutations[0].envelope.mutation_id;
    await act(async () => {
      api.mutations[0].gate.reject(new TypeError("Failed to fetch"));
    });
    await screen.findByTestId("commit-unknown");
    first.unmount();

    renderExplorer(api);
    const region = await screen.findByRole("region", {
      name: "Unresolved transfer confirmation",
    });
    fireEvent.click(
      within(region).getByRole("button", { name: "Retry same transfer" }),
    );
    await waitFor(() => expect(api.mutations).toHaveLength(2));
    expect(api.mutations[1].envelope.mutation_id).toBe(original);
    await act(async () => {
      api.mutations[1].gate.resolve(
        json(200, committedBody(api, api.mutations[1].envelope, REVISION + 1)),
      );
    });

    await waitFor(() => expect(routerPush).toHaveBeenCalledTimes(1));
    expect(routerPush).toHaveBeenCalledWith(
      `/plans/${api.plan.plan_id}?gw=9&highlight=101`,
    );
    expect(
      JSON.parse(window.sessionStorage.getItem(noticeKey(api)) ?? "null"),
    ).toMatchObject({ message: "Transferred P6 for Available Alex in GW9" });
  });

  describe("a submission resumed in a different gameweek keeps its own gameweek", () => {
    const earlier = {
      gameweek: 9,
      outgoingPlayerId: EXPLORER_OUTGOING_ID,
      projectionRunId: EXPLORER_RUN_ID,
      playerInId: 101,
      outgoingName: "P6",
      incomingName: "Available Alex",
    };

    it("reports GW9 for the notice, return URL and highlight when the real coordinator commits it while GW10 is shown", async () => {
      const api = installApi();
      const first = await confirmOwn(api);
      const original = api.mutations[0].envelope;
      await act(async () => {
        api.mutations[0].gate.reject(new TypeError("Failed to fetch"));
      });
      await screen.findByTestId("commit-unknown");
      first.unmount();

      renderExplorer(api, { gameweek: 10 });
      const region = await screen.findByRole("region", {
        name: "Unresolved transfer confirmation",
      });
      expect(region).toHaveTextContent("P6 to Available Alex in GW9");
      fireEvent.click(
        within(region).getByRole("button", { name: "Retry same transfer" }),
      );
      await waitFor(() => expect(api.mutations).toHaveLength(2));
      expect(api.mutations[1].envelope).toEqual(original);
      await act(async () => {
        api.mutations[1].gate.resolve(
          json(200, committedBody(api, original, REVISION + 1)),
        );
      });

      await waitFor(() => expect(routerPush).toHaveBeenCalledTimes(1));
      expect(routerPush).toHaveBeenCalledWith(
        `/plans/${api.plan.plan_id}?gw=9&highlight=101`,
      );
      expect(
        JSON.parse(window.sessionStorage.getItem(noticeKey(api)) ?? "null"),
      ).toEqual({
        message: "Transferred P6 for Available Alex in GW9",
        gameweek: 9,
        incomingPlayerId: 101,
      });
      expect(screen.getByTestId("commit-success")).toHaveTextContent("GW9");
      expect(screen.getByTestId("commit-success")).not.toHaveTextContent(
        "GW10",
      );
    });

    it("uses the original gameweek for an unresolved record observed while mounted", async () => {
      const api = installApi();
      const { factory, set } = createFakeCommit(api, {
        pinned: pinned({ submissionId: "earlier-1", status: "unknown" }),
        label: "P6 to Available Alex in GW9",
        details: earlier,
      });
      renderExplorer(api, { commit: factory, gameweek: 10 });
      await screen.findByRole("region", {
        name: "Unresolved transfer confirmation",
      });

      act(() =>
        set({
          pinned: pinned({ submissionId: "earlier-1", status: "committed" }),
          idle: true,
        }),
      );

      await waitFor(() => expect(routerPush).toHaveBeenCalledTimes(1));
      expect(routerPush).toHaveBeenCalledWith(
        `/plans/${api.plan.plan_id}?gw=9&highlight=101`,
      );
      expect(
        JSON.parse(window.sessionStorage.getItem(noticeKey(api)) ?? "null"),
      ).toMatchObject({
        message: "Transferred P6 for Available Alex in GW9",
        gameweek: 9,
      });
    });

    it("does not navigate for a terminal record already present on mount, even with remembered details", async () => {
      const api = installApi();
      const { fake, factory } = createFakeCommit(api, {
        pinned: pinned({ submissionId: "earlier-1", status: "committed" }),
        label: "P6 to Available Alex in GW9",
        details: earlier,
      });
      renderExplorer(api, { commit: factory, gameweek: 10 });

      await screen.findByTestId("commit-earlier");
      await waitFor(() => expect(fake.abandon).toHaveBeenCalledTimes(1));

      expect(routerPush).not.toHaveBeenCalled();
      expect(window.sessionStorage.getItem(noticeKey(api))).toBeNull();
    });

    it("does not navigate for another submission's acknowledgement while GW10 is shown", async () => {
      const api = installApi();
      const { factory, set } = createFakeCommit(api);
      renderExplorer(api, { commit: factory, gameweek: 10 });
      await screen.findByRole("button", { name: "Preview Available Alex" });

      act(() =>
        set({
          pinned: pinned({ submissionId: "someone-else", status: "committed" }),
          label: "P6 to Available Alex in GW9",
          details: earlier,
        }),
      );

      await screen.findByTestId("commit-earlier");
      expect(routerPush).not.toHaveBeenCalled();
      expect(window.sessionStorage.getItem(noticeKey(api))).toBeNull();
    });
  });

  it("shows a commit that finished while the Explorer was away once, without navigating", async () => {
    const api = installApi();
    const first = await confirmOwn(api);
    first.unmount();
    await act(async () => {
      api.mutations[0].gate.resolve(
        json(200, committedBody(api, api.mutations[0].envelope, REVISION + 1)),
      );
    });
    expect(getPlanSaveCoordinator(api.plan).getSnapshot().pinned?.status).toBe(
      "committed",
    );

    renderExplorer(api);

    expect(await screen.findByTestId("commit-earlier")).toHaveTextContent(
      /earlier.*added to your plan/i,
    );
    await waitFor(() =>
      expect(getPlanSaveCoordinator(api.plan).getSnapshot().pinned).toBeNull(),
    );
    expect(routerPush).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem(noticeKey(api))).toBeNull();
  });

  describe("departure while a submission is unresolved", () => {
    function backToPlan() {
      return within(
        screen.getByRole("region", { name: "Planner context" }),
      ).getByRole("link", { name: "Back to plan" });
    }

    async function unresolved(status: "sending" | "unknown") {
      const api = installApi();
      await confirmOwn(api);
      if (status === "unknown") {
        await act(async () => {
          api.mutations[0].gate.reject(new TypeError("Failed to fetch"));
        });
        await screen.findByTestId("commit-unknown");
      }
      return api;
    }

    it.each(["sending", "unknown"] as const)(
      "offers the same warning as the Planner while %s and keeps the submission when declined",
      async (status) => {
        const api = await unresolved(status);
        const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
        const stop = vi.fn();
        onDocument("click", (event) => {
          stop(event.defaultPrevented);
          event.preventDefault();
        });

        fireEvent.click(backToPlan());

        expect(confirm).toHaveBeenCalledWith(WARNING);
        expect(stop).not.toHaveBeenCalled();
        const unload = new Event("beforeunload", { cancelable: true });
        window.dispatchEvent(unload);
        expect(unload.defaultPrevented).toBe(true);
        expect(
          getPlanSaveCoordinator(api.plan).getSnapshot().pinned?.status,
        ).toBe(status);
      },
    );

    it("lets an accepted departure through and leaves the submission in the shared coordinator", async () => {
      const api = await unresolved("unknown");
      vi.spyOn(window, "confirm").mockReturnValue(true);
      const reached: boolean[] = [];
      onDocument("click", (event) => {
        reached.push(event.defaultPrevented);
        event.preventDefault();
      });

      fireEvent.click(backToPlan());

      expect(reached).toEqual([false]);
      expect(
        getPlanSaveCoordinator(api.plan).getSnapshot().pinned?.status,
      ).toBe("unknown");
    });

    it("prompts on browser Back and stays on the Explorer when declined", async () => {
      const api = await unresolved("unknown");
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      const go = vi.spyOn(window.history, "go").mockImplementation(() => {});
      const back = vi
        .spyOn(window.history, "back")
        .mockImplementation(() => {});

      act(() => {
        window.dispatchEvent(new PopStateEvent("popstate", { state: {} }));
      });

      expect(confirm).toHaveBeenCalledWith(WARNING);
      expect(go).toHaveBeenCalledWith(1);
      expect(back).not.toHaveBeenCalled();
      expect(screen.getByTestId("commit-unknown")).toBeInTheDocument();
      expect(
        getPlanSaveCoordinator(api.plan).getSnapshot().pinned?.status,
      ).toBe("unknown");
    });

    it("does not warn once the submission is committed or rejected", async () => {
      const api = installApi();
      await confirmOwn(api);
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      await act(async () => {
        api.mutations[0].gate.resolve(
          json(422, {
            detail: {
              code: "prices_changed",
              message: "Prices",
              diagnostics: [],
            },
          }),
        );
      });
      await screen.findByTestId("commit-rejection");
      onDocument("click", (event) => event.preventDefault());

      fireEvent.click(backToPlan());
      const unload = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(unload);

      expect(confirm).not.toHaveBeenCalled();
      expect(unload.defaultPrevented).toBe(false);
    });

    it("stops guarding after the Explorer unmounts but the coordinator still reports the work", async () => {
      const api = await unresolved("unknown");
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      cleanup();

      const unload = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(unload);

      expect(unload.defaultPrevented).toBe(false);
      expect(confirm).not.toHaveBeenCalled();
      expect(getPlanSaveCoordinator(api.plan).hasUnsavedWork()).toBe(true);
    });
  });
});

describe("Planner Explorer list refresh and submission-scoped recovery", () => {
  const PRICES_CHANGED = {
    detail: {
      code: "prices_changed",
      message: "Prices changed since you previewed this transfer",
      diagnostics: [],
    },
  };
  const NOT_SAVED = {
    detail: {
      code: "accepted_not_saved",
      message: "The edit was accepted but not saved",
      candidate: null,
    },
  };

  const previewRequests = (api: Api): URL[] =>
    api.spy.mock.calls
      .map(([input]) => new URL(String(input)))
      .filter((url) => url.pathname.endsWith("/preview"));

  const priceOf = (name: string): HTMLElement =>
    within(screen.getByRole("row", { name: new RegExp(name) })).getByText(
      /^£\d+\.\dm$/,
      { selector: "td" },
    );

  /** The server raises Available Alex's price from the second list call on. */
  function repriceFromSecondList(api: Api, tenths = 64) {
    api.listReply = (call, response) => {
      if (call >= 2) {
        response.candidates.find(
          (item) => item.player_id === 101,
        )!.price_tenths = tenths;
      }
    };
  }

  async function submitAndHold(
    api: Api,
    options: ExplorerOptions = {},
    candidate = "Available Alex",
  ) {
    const view = renderExplorer(api, options);
    const panel = await openPreview(candidate);
    fireEvent.click(
      within(panel).getByRole("button", { name: "Confirm transfer" }),
    );
    await waitFor(() => expect(api.mutations).toHaveLength(1));
    return view;
  }

  const rejectWith = (api: Api, body: unknown, status = 422) =>
    act(async () => {
      api.mutations[0].gate.resolve(json(status, body));
    });

  describe("refreshing the candidate list after a rejection or conflict", () => {
    it("replaces stale prices in place without unmounting the table, its controls or the pinned run", async () => {
      const api = installApi();
      repriceFromSecondList(api);
      await submitAndHold(api);
      const table = screen.getByRole("table", {
        name: "Replacement candidates",
      });
      fireEvent.change(
        screen.getByRole("searchbox", { name: "Search players" }),
        { target: { value: "alex" } },
      );
      expect(priceOf("Available Alex")).toHaveTextContent("£6.2m");

      await rejectWith(api, PRICES_CHANGED);

      await waitFor(() =>
        expect(priceOf("Available Alex")).toHaveTextContent("£6.4m"),
      );
      expect(
        screen.getByRole("table", { name: "Replacement candidates" }),
      ).toBe(table);
      expect(
        screen.getByRole("searchbox", { name: "Search players" }),
      ).toHaveValue("alex");
      expect(screen.queryByText(/Loading replacements/)).toBeNull();
      expect(api.listCalls).toHaveLength(2);
      expect(api.listCalls[1].searchParams.get("projection_run_id")).toBe(
        String(EXPLORER_RUN_ID),
      );
      expect(api.listCalls[1].searchParams.get("primary_horizon")).toBe("5");
      // The preview is reloaded too, and nothing was resubmitted.
      await waitFor(() => expect(api.previewCalls).toEqual([101, 101]));
      expect(api.mutations).toHaveLength(1);
    });

    it("refreshes the list for an in-scope rejection while another candidate's preview is open, leaving that preview alone", async () => {
      const api = installApi();
      repriceFromSecondList(api);
      await submitAndHold(api);
      fireEvent.click(
        screen.getByRole("button", { name: "Preview Blocked Ben" }),
      );
      await screen.findByRole("heading", { name: /for Blocked Ben/ });
      const open = screen.getByRole("region", { name: "Transfer preview" });
      const before = open.textContent;
      expect(priceOf("Available Alex")).toHaveTextContent("£6.2m");

      await rejectWith(api, PRICES_CHANGED);

      await waitFor(() =>
        expect(priceOf("Available Alex")).toHaveTextContent("£6.4m"),
      );
      expect(api.listCalls).toHaveLength(2);
      expect(await screen.findByTestId("commit-rejection")).toHaveTextContent(
        /prices changed/i,
      );
      expect(
        screen.getByRole("heading", { name: /for Blocked Ben/ }),
      ).toBeInTheDocument();
      expect(screen.getByRole("region", { name: "Transfer preview" })).toBe(
        open,
      );
      // Only the confirmation line may change: the saving notice goes once the submission ends.
      expect(open.textContent?.split("Add to plan GW9")[0]).toBe(
        before?.split("Add to plan GW9")[0],
      );
      expect(api.previewCalls).toEqual([101, 103]);
      expect(api.mutations).toHaveLength(1);
    });

    it("refreshes after a conflict, on the pinned run, and shows the refreshed state", async () => {
      const api = installApi();
      repriceFromSecondList(api, 66);
      await submitAndHold(api);
      api.plan = { ...api.plan, revision: REVISION + 1 };
      await rejectWith(
        api,
        {
          detail: {
            code: "revision_conflict",
            message: "Plan revision has advanced",
            plan: api.plan,
          },
        },
        409,
      );
      const conflict = await screen.findByTestId("commit-conflict");

      fireEvent.click(
        within(conflict).getByRole("button", {
          name: "Refresh and preview again",
        }),
      );

      await waitFor(() =>
        expect(priceOf("Available Alex")).toHaveTextContent("£6.6m"),
      );
      expect(api.listCalls[1].searchParams.get("projection_run_id")).toBe(
        String(EXPLORER_RUN_ID),
      );
      expect(api.listCalls[1].searchParams.get("primary_horizon")).toBe("5");
      await waitFor(() => expect(api.previewCalls).toEqual([101, 101]));
    });

    it("keeps the current list visible and says it is refreshing while the refresh is pending", async () => {
      const api = installApi();
      const gate = deferred<void>();
      api.listReply = async (call, response) => {
        if (call === 2) {
          await gate.promise;
          response.candidates.find(
            (item) => item.player_id === 101,
          )!.price_tenths = 64;
        }
      };
      await submitAndHold(api);

      await rejectWith(api, PRICES_CHANGED);

      expect(await screen.findByTestId("list-refreshing")).toHaveTextContent(
        /refreshing/i,
      );
      expect(priceOf("Available Alex")).toHaveTextContent("£6.2m");
      expect(screen.getByTestId("commit-rejection")).toBeInTheDocument();
      await act(async () => gate.resolve());
      await waitFor(() =>
        expect(priceOf("Available Alex")).toHaveTextContent("£6.4m"),
      );
      expect(screen.queryByTestId("list-refreshing")).toBeNull();
    });

    it("keeps the stale list with a warning when the refresh fails, and recovers on retry", async () => {
      const api = installApi();
      api.listReply = (call, response) => {
        if (call === 2) return json(500, { detail: "boom" });
        if (call >= 3) {
          response.candidates.find(
            (item) => item.player_id === 101,
          )!.price_tenths = 64;
        }
      };
      await submitAndHold(api);

      await rejectWith(api, PRICES_CHANGED);

      const warning = await screen.findByTestId("list-refresh-failed");
      expect(warning).toHaveTextContent(/may be out of date/i);
      expect(priceOf("Available Alex")).toHaveTextContent("£6.2m");
      // The rejection and its recovery are unaffected by the failed refresh.
      expect(screen.getByTestId("commit-rejection")).toBeInTheDocument();
      await waitFor(() => expect(api.previewCalls).toEqual([101, 101]));

      fireEvent.click(
        within(warning).getByRole("button", { name: "Retry refresh" }),
      );

      await waitFor(() =>
        expect(priceOf("Available Alex")).toHaveTextContent("£6.4m"),
      );
      expect(screen.queryByTestId("list-refresh-failed")).toBeNull();
      expect(api.listCalls).toHaveLength(3);
    });

    it("discards a refresh that finishes after the list was reloaded for another horizon", async () => {
      const api = installApi();
      const gate = deferred<void>();
      api.listReply = async (call, response) => {
        const alex = response.candidates.find(
          (item) => item.player_id === 101,
        )!;
        if (call === 2) {
          await gate.promise;
          alex.price_tenths = 64; // the stale refresh
        }
        if (call === 3) alex.price_tenths = 61; // the horizon change's own load
      };
      const view = await submitAndHold(api);
      await rejectWith(api, PRICES_CHANGED);
      await screen.findByTestId("list-refreshing");

      view.rerenderWith({ horizon: 3 });
      await waitFor(() =>
        expect(priceOf("Available Alex")).toHaveTextContent("£6.1m"),
      );
      await act(async () => gate.resolve());

      await act(async () => {
        await Promise.resolve();
      });
      expect(priceOf("Available Alex")).toHaveTextContent("£6.1m");
      expect(screen.queryByTestId("list-refreshing")).toBeNull();
      expect(screen.queryByTestId("list-refresh-failed")).toBeNull();
    });

    it("does not refresh the list for a rejection that belongs to another scope", async () => {
      const api = installApi();
      const view = await submitAndHold(api);
      view.rerenderWith({ gameweek: 10 });
      await waitFor(() => expect(api.listCalls).toHaveLength(2));

      await rejectWith(api, PRICES_CHANGED);

      await screen.findByTestId("commit-rejection");
      await act(async () => {
        await Promise.resolve();
      });
      expect(api.listCalls).toHaveLength(2);
    });
  });

  describe("recovery is bound to the submission's own scope", () => {
    const recoverHref = () =>
      screen.getByTestId("recover-link").getAttribute("href");

    it("reloads the preview in place when only the horizon changed", async () => {
      const api = installApi();
      const view = await submitAndHold(api);
      view.rerenderWith({ horizon: 3 });
      await waitFor(() => expect(api.listCalls).toHaveLength(2));

      await rejectWith(api, PRICES_CHANGED);

      await waitFor(() => expect(api.previewCalls).toEqual([101, 101]));
      expect(screen.queryByTestId("recover-link")).toBeNull();
      await waitFor(() => expect(api.listCalls).toHaveLength(3));
      expect(api.listCalls[2].searchParams.get("primary_horizon")).toBe("3");
    });

    it("leaves a different gameweek alone and points back to the rejected transfer", async () => {
      const api = installApi();
      const view = await submitAndHold(api);
      view.rerenderWith({ gameweek: 10 });
      await waitFor(() => expect(api.listCalls).toHaveLength(2));

      await rejectWith(api, PRICES_CHANGED);

      const rejection = await screen.findByTestId("commit-rejection");
      expect(rejection).toHaveTextContent(/P6 to Available Alex in GW9/);
      expect(recoverHref()).toBe(
        `/transfers?plan=${api.plan.plan_id}&gw=9&out=6&h=5&run=${EXPLORER_RUN_ID}`,
      );
      await act(async () => {
        await Promise.resolve();
      });
      expect(previewRequests(api)).toHaveLength(1);
      expect(api.previewCalls).toEqual([101]);
      expect(screen.queryByText(/Loading preview/)).toBeNull();
    });

    it("leaves a different outgoing player alone and points back to the rejected transfer", async () => {
      const api = installApi();
      const view = await submitAndHold(api);
      view.rerenderWith({ playerOutId: 7 });
      await waitFor(() => expect(api.listCalls).toHaveLength(2));

      await rejectWith(api, PRICES_CHANGED);

      await screen.findByTestId("commit-rejection");
      expect(recoverHref()).toContain("gw=9&out=6&");
      await act(async () => {
        await Promise.resolve();
      });
      expect(api.previewCalls).toEqual([101]);
    });

    it("never switches to another projection run to recover", async () => {
      const api = installApi();
      const view = await submitAndHold(api);
      view.rerenderWith({ runId: EXPLORER_RUN_ID + 1 });
      await waitFor(() => expect(api.listCalls).toHaveLength(2));

      await rejectWith(api, PRICES_CHANGED);

      await screen.findByTestId("commit-rejection");
      expect(recoverHref()).toContain(`run=${EXPLORER_RUN_ID}`);
      expect(recoverHref()).not.toContain(`run=${EXPLORER_RUN_ID + 1}`);
      await act(async () => {
        await Promise.resolve();
      });
      expect(api.previewCalls).toEqual([101]);
    });

    it("refreshes a conflicting submission from another scope without previewing it here", async () => {
      const api = installApi();
      const view = await submitAndHold(api);
      view.rerenderWith({ gameweek: 10 });
      await waitFor(() => expect(api.listCalls).toHaveLength(2));
      api.plan = { ...api.plan, revision: REVISION + 1 };
      await rejectWith(
        api,
        {
          detail: {
            code: "revision_conflict",
            message: "Plan revision has advanced",
            plan: api.plan,
          },
        },
        409,
      );
      const conflict = await screen.findByTestId("commit-conflict");
      const refresh = within(conflict).getByRole("button", {
        name: "Refresh the plan",
      });

      fireEvent.click(refresh);

      const notice = await screen.findByTestId("commit-earlier");
      expect(notice).toHaveTextContent(/was not submitted/i);
      expect(recoverHref()).toContain("gw=9&out=6&");
      expect(getPlanSaveCoordinator(api.plan).getSnapshot().pinned).toBeNull();
      // The page's own list is refreshed for the new revision; no preview is loaded for GW9.
      await waitFor(() => expect(api.listCalls).toHaveLength(3));
      expect(api.listCalls[2].pathname).toContain("/gameweeks/10/");
      expect(api.previewCalls).toEqual([101]);
      expect(api.mutations).toHaveLength(1);
    });

    it("keeps another scope's open preview when an unresolved transfer is stopped", async () => {
      const api = installApi();
      const view = await submitAndHold(api);
      await rejectWith(api, NOT_SAVED, 503);
      await screen.findByTestId("commit-pending");
      view.rerenderWith({ playerOutId: 7 });
      await waitFor(() => expect(api.listCalls).toHaveLength(2));
      // The same candidate id, previewed for a different outgoing player.
      fireEvent.click(
        await screen.findByRole("button", { name: "Preview Available Alex" }),
      );
      await screen.findByRole("region", { name: "Transfer preview" });
      expect(api.previewCalls).toEqual([101, 101]);

      fireEvent.click(
        within(screen.getByTestId("commit-pending")).getByRole("button", {
          name: "Stop tracking this transfer",
        }),
      );

      await screen.findByTestId("not-added-notice");
      expect(
        screen.getByRole("region", { name: "Transfer preview" }),
      ).toBeInTheDocument();
    });

    it("still closes the stopped transfer's own preview in its own scope", async () => {
      const api = installApi();
      await submitAndHold(api);
      await rejectWith(api, NOT_SAVED, 503);
      await screen.findByTestId("commit-pending");

      fireEvent.click(
        within(screen.getByTestId("commit-pending")).getByRole("button", {
          name: "Stop tracking this transfer",
        }),
      );

      await screen.findByTestId("not-added-notice");
      expect(
        screen.queryByRole("region", { name: "Transfer preview" }),
      ).toBeNull();
    });
  });
});
