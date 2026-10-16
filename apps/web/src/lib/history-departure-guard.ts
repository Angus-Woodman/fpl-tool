type GuardSource = {
  hasUnsavedWork(): boolean;
  subscribe(listener: () => void): () => void;
};

const MARKER = "plannerDepartureGuard";
const LEAVE_GRACE_MS = 1000;

function isGuardEntry(state: unknown): boolean {
  return (
    typeof state === "object" &&
    state !== null &&
    (state as Record<string, unknown>)[MARKER] === true
  );
}

/**
 * Back/Forward cannot be cancelled, so while work is unsaved one same-URL entry is stacked
 * above the page. Back lands on the real entry underneath; we then either restore the guard
 * entry (user stays) or continue the Back (user leaves). Arming drops any Forward entries.
 */
export function installHistoryDepartureGuard(
  source: GuardSource,
  warning: string,
): { leaving: () => boolean; dispose: () => void } {
  let armed = false;
  let leaving = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  if (isGuardEntry(window.history.state)) {
    window.history.replaceState({}, "", window.location.href);
  }

  const arm = (): void => {
    if (armed || leaving || !source.hasUnsavedWork()) return;
    window.history.pushState({ [MARKER]: true }, "", window.location.href);
    armed = true;
  };

  const onPopState = (event: PopStateEvent): void => {
    if (!armed || isGuardEntry(event.state)) return;
    if (!source.hasUnsavedWork()) {
      armed = false;
      window.history.back();
      return;
    }
    if (window.confirm(warning)) {
      armed = false;
      leaving = true;
      timer = setTimeout(() => {
        leaving = false;
        arm();
      }, LEAVE_GRACE_MS);
      window.history.back();
      return;
    }
    window.history.go(1);
  };

  window.addEventListener("popstate", onPopState);
  const unsubscribe = source.subscribe(arm);
  arm();

  return {
    leaving: () => leaving,
    dispose: () => {
      window.removeEventListener("popstate", onPopState);
      unsubscribe();
      if (timer !== undefined) clearTimeout(timer);
    },
  };
}
