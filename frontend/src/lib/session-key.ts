/**
 * The operator's admin key, held in sessionStorage.
 *
 * WHY THIS IS NOT JUST useState + useEffect
 *
 * The obvious version reads sessionStorage in an effect and calls setState.
 * That works and React now flags it, for a good reason: the page renders
 * once with the wrong answer (no key, so the password box) and then again
 * with the right one, so an operator with a valid key sees the login form
 * flash on every navigation.
 *
 * It also cannot be read during render. This page is prerendered as a static
 * file, so the HTML says "no key"; a render that read storage directly would
 * disagree with that HTML and break hydration.
 *
 * `useSyncExternalStore` is the primitive built for exactly this -- a value
 * that lives outside React, differs between server and client, and can
 * change. `getServerSnapshot` returns null, which is what the static HTML
 * contains, and the client resolves it during the first render rather than
 * after it.
 *
 * WHY sessionStorage AND NOT localStorage
 *
 * The key unlocks every customer's name, phone number and passport scan.
 * sessionStorage dies with the tab, so a shared or forgotten machine does
 * not keep it. localStorage would survive reboots, which is convenient for
 * the operator and wrong for everybody in the table.
 */

import { useSyncExternalStore } from "react";

const STORAGE_KEY = "skyclaim.admin.key";

const listeners = new Set<() => void>();

/**
 * The last value read, returned by reference until something changes it.
 *
 * `useSyncExternalStore` calls `getSnapshot` on every render and loops
 * forever if the result is not stable. Reading sessionStorage each time
 * would return an equal string, which is fine for a primitive -- but the
 * cache also means a blocked-storage exception is paid once rather than on
 * every render.
 */
let cached: string | null = null;
let loaded = false;

function read(): string | null {
  if (loaded) return cached;
  try {
    cached = sessionStorage.getItem(STORAGE_KEY);
  } catch {
    // Private browsing, or storage disabled by policy. The operator types
    // the key each time: inconvenient, not broken.
    cached = null;
  }
  loaded = true;
  return cached;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function write(value: string | null): void {
  cached = value;
  loaded = true;
  try {
    if (value === null) sessionStorage.removeItem(STORAGE_KEY);
    else sessionStorage.setItem(STORAGE_KEY, value);
  } catch {
    // Keep it in memory for this tab regardless -- a key that works until
    // the page reloads is better than one that does not work at all.
  }
  for (const listener of listeners) listener();
}

export function useAdminKey(): [string | null, (value: string | null) => void] {
  const key = useSyncExternalStore(subscribe, read, () => null);
  // `write` is a module-level function, so it is already stable across
  // renders -- wrapping it in useCallback would add a hook to memoise
  // something that never changes.
  return [key, write];
}

/** Exported for tests, which need to start from a known state. */
export const __testing = { write, reset: () => {
  cached = null;
  loaded = false;
} };
