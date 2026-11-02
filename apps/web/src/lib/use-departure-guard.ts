import { useEffect } from "react";

import { installHistoryDepartureGuard } from "@/lib/history-departure-guard";

export const DEPARTURE_WARNING =
  "Your latest Planner edit is not saved yet. Leave this page anyway?";

/** The plan-scoped save coordinator (or an adapter over it); the Planner and the Explorer share it. */
export type DepartureGuardSource = {
  hasUnsavedWork(): boolean;
  subscribe(listener: () => void): () => void;
};

/**
 * Warns before leaving a page while the shared coordinator holds unsaved work:
 * link clicks, `beforeunload`, and Back/Forward through the history guard.
 */
export function useDepartureGuard(source: DepartureGuardSource | null): void {
  useEffect(() => {
    if (!source) return;
    const historyGuard = installHistoryDepartureGuard(
      source,
      DEPARTURE_WARNING,
    );
    const onUnload = (event: BeforeUnloadEvent): void => {
      if (historyGuard.leaving() || !source.hasUnsavedWork()) return;
      event.preventDefault();
      event.returnValue = DEPARTURE_WARNING;
    };
    const onClick = (event: MouseEvent): void => {
      if (!source.hasUnsavedWork() || event.defaultPrevented) return;
      if (
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey
      )
        return;
      const link = (event.target as Element | null)?.closest?.("a[href]");
      if (!(link instanceof HTMLAnchorElement)) return;
      if (link.target === "_blank" || link.hasAttribute("download")) return;
      const destination = new URL(link.href, window.location.href);
      if (!/^https?:$/.test(destination.protocol)) return;
      const here = new URL(window.location.href);
      if (
        destination.origin === here.origin &&
        destination.pathname === here.pathname &&
        destination.search === here.search
      )
        return;
      if (!window.confirm(DEPARTURE_WARNING)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", onUnload);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      document.removeEventListener("click", onClick, true);
      historyGuard.dispose();
    };
  }, [source]);
}
