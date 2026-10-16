export type SelectionState = "idle" | "selected" | "target" | "not-target";

export type RearrangementKind = "substitution" | "bench_priority";

/** An unordered pair of players the server's rules say may exchange lineup roles. */
export type LegalRearrangement = {
  first_player_id: number;
  second_player_id: number;
  kind: RearrangementKind;
};

export type SelectionOutcome =
  | { type: "select"; playerId: number }
  | { type: "clear" }
  | {
      type: "swap";
      firstPlayerId: number;
      secondPlayerId: number;
      kind: RearrangementKind;
    };

function findRearrangement(
  legal: readonly LegalRearrangement[],
  playerId: number,
  otherId: number,
): LegalRearrangement | undefined {
  return legal.find(
    (pair) =>
      (pair.first_player_id === playerId &&
        pair.second_player_id === otherId) ||
      (pair.first_player_id === otherId && pair.second_player_id === playerId),
  );
}

export function selectionStateFor(
  legal: readonly LegalRearrangement[],
  selectedId: number | null,
  playerId: number,
): SelectionState {
  if (selectedId === null) {
    return "idle";
  }
  if (playerId === selectedId) {
    return "selected";
  }
  return findRearrangement(legal, selectedId, playerId)
    ? "target"
    : "not-target";
}

export function hasTargets(
  legal: readonly LegalRearrangement[],
  playerId: number,
): boolean {
  return legal.some(
    (pair) =>
      pair.first_player_id === playerId || pair.second_player_id === playerId,
  );
}

export function resolveSelection(
  legal: readonly LegalRearrangement[],
  selectedId: number | null,
  clickedId: number,
): SelectionOutcome {
  if (selectedId === clickedId) {
    return { type: "clear" };
  }
  if (selectedId !== null) {
    const pair = findRearrangement(legal, selectedId, clickedId);
    if (pair) {
      return {
        type: "swap",
        firstPlayerId: selectedId,
        secondPlayerId: clickedId,
        kind: pair.kind,
      };
    }
  }
  return { type: "select", playerId: clickedId };
}

export function swapAnnouncement(
  kind: RearrangementKind,
  firstName: string,
  secondName: string,
): string {
  return kind === "bench_priority"
    ? `Swapped bench order of ${firstName} and ${secondName}.`
    : `Swapped ${firstName} with ${secondName}.`;
}

export function noTargetsMessage(name: string): string {
  return `No valid swap targets for ${name}.`;
}

export function sortByBenchOrder<T extends { bench_order: number | null }>(
  items: readonly T[],
): T[] {
  return [...items].sort(
    (left, right) => (left.bench_order ?? 99) - (right.bench_order ?? 99),
  );
}
