/**
 * A `fetch` wrapper that attaches the access token, always sends the
 * refresh cookie (`credentials: "include"`), and transparently retries
 * once via `/auth/refresh` on a 401 (Phase 56, ADR-0074) -- so a page
 * mid-session doesn't see a spurious failure just because the 15-minute
 * access token expired since the last request.
 *
 * If the refresh itself fails (expired/revoked/missing refresh cookie),
 * this dispatches a `career-agent:session-expired` window event and
 * throws -- `AuthContext` listens for that event to show the session
 * timeout screen, rather than every call site handling it individually.
 *
 * `VITE_API_BASE_URL` (Phase 59, ADR-0076) is a build-time env var,
 * empty by default -- every path this module fetches is a *relative*
 * path (`/auth/...`, `/api/...`), so leaving it unset (the deployment
 * this project actually ships: nginx reverse-proxies the API same-
 * origin, ADR-0076) needs no prefix at all. Setting it points every
 * request at a different origin instead, for the one real case that
 * needs it -- backend and frontend served from genuinely different
 * hosts.
 */

import { getToken, setToken } from "./tokenStore";
import type { TokenResponse } from "@/types/api";

export const SESSION_EXPIRED_EVENT = "career-agent:session-expired";

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "";

function resolve(path: string): string {
  return `${API_BASE_URL}${path}`;
}

let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const response = await fetch(resolve("/auth/refresh"), {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) return false;
      const body = (await response.json()) as TokenResponse;
      setToken(body.access_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

function withAuthHeaders(init: RequestInit = {}): RequestInit {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return { ...init, headers, credentials: "include" };
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  let response = await fetch(resolve(path), withAuthHeaders(init));
  if (response.status === 401 && path !== "/auth/refresh" && path !== "/auth/login") {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await fetch(resolve(path), withAuthHeaders(init));
    } else {
      setToken(null);
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
  }
  return response;
}

export async function apiFetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    let detail = `${path} -> HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // response body wasn't JSON -- keep the generic message
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
