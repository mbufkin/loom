import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { RunPreflight } from "../types";

/**
 * One shared answer to "can this computer run an audit?".
 *
 * Every screen used to ask independently and keep the reply in its own
 * component state, which let them contradict each other: Settings could say
 * "finish setup" while Setup said "you are ready", because they had asked at
 * different moments. Two screens disagreeing about the same fact is worse
 * than either answer being wrong, because now neither can be trusted.
 *
 * A tiny module-level store fixes that. Screens read one cached value, and
 * anything that changes the machine's state -- connecting a model, installing
 * dependencies -- calls refresh() once, which updates every mounted screen.
 *
 * Deliberately not React Context: this needs to be readable and refreshable
 * from anywhere without wrapping the tree in another provider, and the state
 * is a single value with no per-subtree variation.
 */

let cache: RunPreflight | null = null;
let cachedError: unknown = null;
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();

function emit(): void {
  for (const l of listeners) l();
}

/**
 * Re-ask the server and notify every screen.
 *
 * Concurrent callers share one request: mounting two screens at once, or
 * clicking refresh while a check is already running, should not produce two
 * scans whose replies race to land last.
 */
export function refreshPreflight(): Promise<void> {
  if (inflight) return inflight;
  inflight = api
    .canRun()
    .then((pf) => {
      cache = pf;
      cachedError = null;
    })
    .catch((e: unknown) => {
      cachedError = e;
    })
    .finally(() => {
      inflight = null;
      emit();
    });
  return inflight;
}

export function usePreflight(): {
  preflight: RunPreflight | null;
  error: unknown;
  /** False only until the first reply lands, so screens can show a spinner. */
  loaded: boolean;
  refresh: () => Promise<void>;
} {
  const [, bump] = useState(0);

  useEffect(() => {
    const listener = () => bump((n) => n + 1);
    listeners.add(listener);
    // Fetch once on first mount. Later mounts reuse the cache and get a fresh
    // value from whatever action last called refresh(), so navigating between
    // screens does not re-probe the model endpoint every time.
    if (cache === null && cachedError === null) void refreshPreflight();
    return () => {
      listeners.delete(listener);
    };
  }, []);

  const refresh = useCallback(() => refreshPreflight(), []);
  return {
    preflight: cache,
    error: cachedError,
    loaded: cache !== null || cachedError !== null,
    refresh,
  };
}

/**
 * The single place that turns a preflight into a verdict.
 *
 * Both screens now call this rather than each deriving its own. The previous
 * bug was precisely a derivation difference: Setup computed "ready" by
 * filtering the `checks` array, so when `checks` was absent -- an older
 * server, or any response that omits it -- it filtered an empty list, found
 * nothing wrong, and reported success while `can_run` was false.
 *
 * `can_run` is the server's own verdict and is therefore authoritative here.
 * The checks are detail for display, never the basis of the summary.
 */
export function readiness(pf: RunPreflight | null): {
  ready: boolean;
  pdfOnly: boolean;
  blocked: boolean;
} {
  if (!pf) return { ready: false, pdfOnly: false, blocked: false };
  const canRun = pf.can_run;
  const canPdf = pf.can_read_pdf !== false;
  return {
    ready: canRun && canPdf,
    pdfOnly: canRun && !canPdf,
    blocked: !canRun,
  };
}
