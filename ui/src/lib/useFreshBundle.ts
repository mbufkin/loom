import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/**
 * Has the app on disk moved on since this window loaded it?
 *
 * A desktop window is not a browser tab. It can stay open for days, and the
 * JavaScript it fetched at startup keeps running regardless of what is
 * rebuilt underneath it. That is not hypothetical: a window left open for
 * four days went on showing the old read-only setup checklist after the
 * document-upload flow shipped, with nothing on screen to suggest the app had
 * changed. The only way out was knowing that View → Reload exists.
 *
 * The check is deliberately dumb. On mount it asks the server which build it
 * is serving and keeps that as the baseline — whatever the answer is at load
 * time *is* this window's version, so nothing has to be injected at build
 * time or threaded through the bundle. Afterwards it re-asks, and any change
 * means the files behind this page were replaced.
 *
 * Why this cannot cry wolf:
 *   * The id is a hash of the built index.html, so a rebuild that changes
 *     nothing produces the same id.
 *   * Restarting the API server does not change it either.
 *   * A failed request leaves the baseline alone. Losing contact with the
 *     service is already reported elsewhere and is not an upgrade.
 *
 * Skipped entirely in development, where Vite serves the app with hot reload
 * and `bundle` is null because ui/dist is not what you are looking at.
 */

/** How often to re-ask while the window sits there. */
const POLL_MS = 60_000;

export function useFreshBundle(): { stale: boolean; reload: () => void } {
  const [stale, setStale] = useState(false);
  // The build this window is running. Held in a ref rather than state because
  // changing it must never re-render: it is the fixed point everything else is
  // compared against.
  const baseline = useRef<string | null>(null);

  const check = useCallback(async () => {
    try {
      const { bundle } = await api.version();
      // No bundle means no dist — development, served by Vite. Nothing to
      // compare, and hot reload makes the question moot.
      if (!bundle) return;
      if (baseline.current === null) {
        baseline.current = bundle;
        return;
      }
      if (bundle !== baseline.current) setStale(true);
    } catch {
      // Server down or restarting. Not an upgrade; say nothing.
    }
  }, []);

  useEffect(() => {
    if (import.meta.env.DEV) return;
    void check();
    const timer = window.setInterval(() => void check(), POLL_MS);
    // Also on return to the window. Someone who upgrades Loom and comes back
    // should not wait out the rest of a poll interval to be told, and this is
    // the moment they are most likely to be about to use it.
    const onVisible = () => {
      if (document.visibilityState === "visible") void check();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [check]);

  // location.reload() re-requests index.html, which names the new bundles.
  const reload = useCallback(() => window.location.reload(), []);
  return { stale, reload };
}
