/**
 * The `/auth/*` and `/user/*` endpoints (Phase 56, ADR-0074) -- the only
 * write-capable routes this dashboard's API exposes. Login/register/
 * refresh don't go through `apiFetch`'s 401-retry (there's no token yet
 * to refresh), but they still send `credentials: "include"` so the
 * refresh cookie round-trips correctly.
 */

import { apiFetch, apiFetchJson } from "./http";
import type { JobPreferences, TokenResponse, User } from "@/types/api";

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = `${path} -> HTTP ${response.status}`;
    try {
      const parsed = await response.json();
      if (parsed?.detail) detail = String(parsed.detail);
    } catch {
      // not JSON -- keep the generic message
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const authApi = {
  register: (email: string, password: string, displayName?: string) =>
    postJson<TokenResponse>("/auth/register", {
      email,
      password,
      display_name: displayName ?? null,
    }),
  login: (email: string, password: string) =>
    postJson<TokenResponse>("/auth/login", { email, password }),
  logout: () => postJson<void>("/auth/logout", {}),
  me: () => apiFetchJson<User>("/auth/me"),
  forgotPassword: (email: string) =>
    postJson<{ detail: string }>("/auth/forgot-password", { email }),
  resetPassword: (token: string, newPassword: string) =>
    postJson<void>("/auth/reset-password", { token, new_password: newPassword }),
  updateProfile: (displayName: string | null) =>
    apiFetchJson<{ id: string; email: string; display_name: string | null }>(
      "/user/profile",
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: displayName }),
      },
    ),
  getPreferences: () => apiFetchJson<JobPreferences>("/user/preferences"),
  updatePreferences: (preferences: JobPreferences) =>
    apiFetchJson<JobPreferences>("/user/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(preferences),
    }),
};
