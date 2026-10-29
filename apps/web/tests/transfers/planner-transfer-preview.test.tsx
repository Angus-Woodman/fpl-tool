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
  PlanMutationEnvelope,
  PlanResponse,
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
          return result instanceof Response ? result : json(200, result);
        }
        if (url.pathname.includes("/transfers/")) {
          const response = forPlan(
            buildPlannerExplorerResponse({ candidates }),
            plan.plan_id,
          );
          response.planning_context.revision = api.plan.revision;
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

function renderExplorer(
  api: Api,
  options: { commit?: PlannerCommitFactory; horizon?: 1 | 3 | 5 } = {},
) {
  return render(
    <PlannerTransferExplorer
      planId={api.plan.plan_id}
      gameweek={EXPLORER_GAMEWEEK}
      playerOutId={EXPLORER_OUTGOING_ID}
      horizon={options.horizon ?? 5}
      runId={EXPLORER_RUN_ID}
      commit={options.commit}
    />,
  );
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
    expect(routerPush).not.toHaveBeenCalled();
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
      within(panel).queryByRole("button", { name: "Confirm transfer" }),
    ).not.toBeInTheDocument();
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
    expect(routerPush).not.toHaveBeenCalled();
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
