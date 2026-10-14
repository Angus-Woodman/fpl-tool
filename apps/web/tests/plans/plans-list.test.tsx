import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PlansList } from "@/components/plans/plans-list";
import { PlanIntent, PlanMutationEnvelope } from "@/lib/api";
import { buildPlannerPlan, createPlannerFixture } from "../fixtures/planner";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function scenario(outcome: "success" | "technical" | "stale") {
  const initial = buildPlannerPlan();
  const server = createPlannerFixture(
    initial,
    (plan, intents: PlanIntent[]) => ({
      ...plan,
      name: intents[0].kind === "rename_plan" ? intents[0].name : plan.name,
    }),
  );
  const requests: {
    url: string;
    method: string;
    body?: PlanMutationEnvelope;
  }[] = [];
  let posts = 0;
  vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    requests.push({ url, method, body });
    if (method === "PATCH" || method === "PUT")
      return new Response("retired", { status: 410 });
    if (method === "POST" && url.endsWith("/mutations")) {
      posts += 1;
      if (outcome === "stale")
        return Response.json(
          {
            detail: {
              code: "revision_conflict",
              message: "Plan revision has advanced",
              plan: { ...initial, revision: 1 },
            },
          },
          { status: 409 },
        );
      if (outcome === "technical" && posts === 1)
        return Response.json(
          {
            detail: {
              code: "outcome_unknown",
              message: "Save outcome is unknown",
            },
          },
          { status: 503 },
        );
      return Response.json({
        ...server.mutate(body),
        mutation_id: body.mutation_id,
        candidate: null,
      });
    }
    if (url.endsWith("/plans"))
      return Response.json({ plans: [server.read()] });
    return Response.json(server.read());
  });
  return { requests, initial, server };
}

async function rename(): Promise<void> {
  fireEvent.click(await screen.findByLabelText("Rename Starting state"));
  fireEvent.change(
    screen.getByRole("textbox", { name: "Rename Starting state" }),
    {
      target: { value: "Renamed plan" },
    },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
}

describe("guarded list rename", () => {
  it("loads the current revision, posts a rename intent and refreshes after acknowledgement", async () => {
    const { requests, initial } = scenario("success");
    render(<PlansList />);
    await rename();
    expect(
      await screen.findByRole("link", { name: "Renamed plan" }),
    ).toBeInTheDocument();
    const post = requests.find((request) => request.method === "POST")!;
    expect(post.url).toContain(`/plans/${initial.plan_id}/mutations`);
    expect(post.body).toMatchObject({
      expected_revision: 0,
      intents: [{ kind: "rename_plan", name: "Renamed plan" }],
    });
    expect(
      requests
        .slice(0, requests.indexOf(post))
        .some((request) => request.url.endsWith(`/plans/${initial.plan_id}`)),
    ).toBe(true);
    expect(requests.some((request) => request.method === "PATCH")).toBe(false);
  });

  it("shows technical failure and retries the exact same immutable envelope", async () => {
    const { requests } = scenario("technical");
    render(<PlansList />);
    await rename();
    expect(
      await screen.findByText("Save outcome is unknown"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Renamed plan" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry Rename" }));
    expect(
      await screen.findByRole("link", { name: "Renamed plan" }),
    ).toBeInTheDocument();
    const posts = requests.filter((request) => request.method === "POST");
    expect(posts).toHaveLength(2);
    expect(posts[1].body).toEqual(posts[0].body);
    expect(requests.some((request) => request.method === "PATCH")).toBe(false);
  });

  it("keeps stale rename context visible without claiming success or overwriting", async () => {
    const { requests } = scenario("stale");
    render(<PlansList />);
    await rename();
    expect(
      await screen.findByText("Plan revision has advanced"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "Rename Starting state" }),
    ).toHaveValue("Renamed plan");
    await waitFor(() =>
      expect(
        requests.filter((request) => request.method === "POST"),
      ).toHaveLength(1),
    );
    expect(requests.some((request) => request.method === "PATCH")).toBe(false);
  });
});
