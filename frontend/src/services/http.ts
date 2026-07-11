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
 */

import { getToken, setToken } from "./tokenStore";
import type { TokenResponse } from "@/types/api";

export const SESSION_EXPIRED_EVENT = "career-agent:session-expired";

let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const response = await fetch("/auth/refresh", {
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
  let response = await fetch(path, withAuthHeaders(init));
  if (response.status === 401 && path !== "/auth/refresh" && path !== "/auth/login") {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await fetch(path, withAuthHeaders(init));
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
