import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "../../src");

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory()
      ? sources(path)
      : /\.(ts|tsx)$/.test(name)
        ? [path]
        : [];
  });
}

const files = sources(SRC).map((path) => ({
  path: path.slice(SRC.length + 1),
  text: readFileSync(path, "utf8"),
}));

describe("Planner single guarded writer path", () => {
  it("has no Planner-scoped PATCH or PUT anywhere in the web source", () => {
    const offenders = files.flatMap(({ path, text }) =>
      [...text.matchAll(/method:\s*"(PATCH|PUT)"/g)]
        .filter((match) =>
          text
            .slice(Math.max(0, match.index! - 160), match.index!)
            .includes("/plans"),
        )
        .map(() => path),
    );
    expect(offenders).toEqual([]);
  });

  it("sends plan edits only through the mutation endpoint, from the coordinator alone", () => {
    const mutators = files
      .filter(({ text }) => /\bmutatePlan\b/.test(text))
      .map(({ path }) => path)
      .sort();
    expect(mutators).toEqual(["lib/api.ts", "lib/plan-save-coordinator.ts"]);
    const writes = files.flatMap(({ path, text }) =>
      [
        ...text.matchAll(
          /fetch\(\s*`[^`]*\/plans[^`]*`\s*,\s*\{[^}]*?method:\s*"(\w+)"/gs,
        ),
      ].map(
        (match) => `${path}:${match[0].match(/`([^`]*)`/)![1]}:${match[1]}`,
      ),
    );
    expect(writes.sort()).toEqual(
      [
        "lib/api.ts:${API_BASE_URL}/plans/${planId}/mutations:POST",
        "lib/api.ts:${API_BASE_URL}/plans/${planId}:DELETE",
        "lib/api.ts:${API_BASE_URL}/plans:POST",
      ].sort(),
    );
  });

  it("offers no Save Gameweek control or copy", () => {
    const offenders = files
      .filter(({ text }) => /save\s*gameweek/i.test(text))
      .map(({ path }) => path);
    expect(offenders).toEqual([]);
  });
});
