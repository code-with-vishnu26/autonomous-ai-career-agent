/**
 * The access token lives here, in memory only -- never `localStorage`
 * (Phase 56, ADR-0074: an XSS payload that can read `localStorage` can
 * read anything a script can, but keeping the token out of persistent
 * storage means it doesn't survive a page reload or get written to disk).
 * The refresh token never reaches JavaScript at all -- it's an httpOnly
 * cookie the browser attaches automatically.
 *
 * A plain module-level singleton, not React state: `services/http.ts`
 * needs to read/write the current token from plain `fetch` calls outside
 * any component, and `AuthContext` subscribes to be notified when it
 * changes so the UI re-renders in sync.
 */

let currentToken: string | null = null;
type Listener = (token: string | null) => void;
const listeners = new Set<Listener>();

export function getToken(): string | null {
  return currentToken;
}

export function setToken(token: string | null): void {
  currentToken = token;
  for (const listener of listeners) listener(token);
}

export function subscribeToken(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
