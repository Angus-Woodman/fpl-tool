export type TransferNotice = {
  message: string;
  gameweek: number;
  incomingPlayerId: number;
};

const noticeKey = (planId: number): string => `plannerTransferNotice:${planId}`;

/** One-shot hand-off from the Explorer to the Planner after a saved transfer. */
export function writeTransferNotice(
  planId: number,
  notice: TransferNotice,
): void {
  try {
    window.sessionStorage.setItem(noticeKey(planId), JSON.stringify(notice));
  } catch {
    // Storage can be blocked; the transfer is already saved and the highlighted card still shows it.
  }
}

/** Reads the notice without consuming it, so a repeated effect run cannot lose it; unreadable values are dropped. */
export function peekTransferNotice(planId: number): TransferNotice | null {
  let raw: string | null;
  try {
    raw = window.sessionStorage.getItem(noticeKey(planId));
  } catch {
    // Storage can be blocked; no notice then.
    return null;
  }
  if (raw === null) return null;
  try {
    const value = JSON.parse(raw) as Partial<TransferNotice>;
    if (
      typeof value.message === "string" &&
      Number.isInteger(value.gameweek) &&
      Number.isInteger(value.incomingPlayerId)
    ) {
      return value as TransferNotice;
    }
  } catch {
    // Not JSON: treated like any other unreadable value below.
  }
  clearTransferNotice(planId);
  return null;
}

export function clearTransferNotice(planId: number): void {
  try {
    window.sessionStorage.removeItem(noticeKey(planId));
  } catch {
    // Storage can be blocked; nothing to clear.
  }
}
