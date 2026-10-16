import { describe, expect, it } from "vitest";

import {
  hasTargets,
  resolveSelection,
  selectionStateFor,
  sortByBenchOrder,
  swapAnnouncement,
  type LegalRearrangement,
} from "@/lib/squad-rearrangement";

const legal: LegalRearrangement[] = [
  { first_player_id: 1, second_player_id: 2, kind: "substitution" },
  { first_player_id: 7, second_player_id: 3, kind: "substitution" },
  { first_player_id: 7, second_player_id: 12, kind: "bench_priority" },
];

describe("squad rearrangement selection", () => {
  it("has no selection states until something is selected", () => {
    expect(selectionStateFor(legal, null, 1)).toBe("idle");
  });

  it("marks the selection and only the pairs the server listed, in either order", () => {
    expect(selectionStateFor(legal, 1, 1)).toBe("selected");
    expect(selectionStateFor(legal, 1, 2)).toBe("target");
    expect(selectionStateFor(legal, 2, 1)).toBe("target");
    expect(selectionStateFor(legal, 7, 3)).toBe("target");
    expect(selectionStateFor(legal, 3, 7)).toBe("target");
    expect(selectionStateFor(legal, 7, 12)).toBe("target");
    expect(selectionStateFor(legal, 1, 3)).toBe("not-target");
    expect(selectionStateFor(legal, 3, 12)).toBe("not-target");
  });

  it("derives targets only from the supplied list, never from positions or formations", () => {
    expect(selectionStateFor([], 1, 2)).toBe("not-target");
    expect(
      selectionStateFor(
        [{ first_player_id: 40, second_player_id: 41, kind: "substitution" }],
        40,
        41,
      ),
    ).toBe("target");
  });

  it("reports whether a selected player has any target", () => {
    expect(hasTargets(legal, 12)).toBe(true);
    expect(hasTargets(legal, 2)).toBe(true);
    expect(hasTargets(legal, 99)).toBe(false);
  });

  it("selects, cancels, swaps or replaces on each choice", () => {
    expect(resolveSelection(legal, null, 1)).toEqual({
      type: "select",
      playerId: 1,
    });
    expect(resolveSelection(legal, 1, 1)).toEqual({ type: "clear" });
    expect(resolveSelection(legal, 1, 2)).toEqual({
      type: "swap",
      firstPlayerId: 1,
      secondPlayerId: 2,
      kind: "substitution",
    });
    expect(resolveSelection(legal, 12, 7)).toEqual({
      type: "swap",
      firstPlayerId: 12,
      secondPlayerId: 7,
      kind: "bench_priority",
    });
    expect(resolveSelection(legal, 1, 3)).toEqual({
      type: "select",
      playerId: 3,
    });
  });

  it("words the announcement by kind and names both players", () => {
    expect(swapAnnouncement("substitution", "GK One", "GK Two")).toBe(
      "Swapped GK One with GK Two.",
    );
    expect(swapAnnouncement("bench_priority", "DEF Five", "MID Five")).toBe(
      "Swapped bench order of DEF Five and MID Five.",
    );
  });

  it("orders substitutes by priority without mutating the input", () => {
    const bench = [
      { id: "d", bench_order: 3 },
      { id: "g", bench_order: 1 },
      { id: "f", bench_order: 4 },
      { id: "m", bench_order: 2 },
    ];
    expect(sortByBenchOrder(bench).map((item) => item.id)).toEqual([
      "g",
      "m",
      "d",
      "f",
    ]);
    expect(bench.map((item) => item.id)).toEqual(["d", "g", "f", "m"]);
  });
});
