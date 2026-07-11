/**
 * Thin fetch wrapper over the FastAPI dashboard API (Phase 54, ADR-0072).
 * One function per route, no client-side business logic beyond parsing
 * JSON -- any derived view (e.g. "applications ready to submit") is
 * computed in a hook from these raw responses, mirroring how
 * `analytics.py`'s own aggregation is presentation logic over the same
 * stores, not a new source of truth.
 *
 * Every route here is a GET. There is no `postX`/`patchX` in this file
 * because the backend exposes none (Phase 54 is deliberately read-only) --
 * see `src/components/CliOnlyAction.tsx` for how write actions are
 * surfaced honestly instead.
 */

import type {
  AnalyticsSummary,
  ApplicationSession,
  HealthStatus,
  RedactedSettings,
  ResumeVariant,
  ReviewSession,
  SubmissionResult,
} from "@/types/api";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path} -> HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => getJson<HealthStatus>("/api/health"),
  applications: () => getJson<ApplicationSession[]>("/api/applications"),
  reviews: () => getJson<ReviewSession[]>("/api/reviews"),
  pendingReviews: () => getJson<ReviewSession[]>("/api/reviews/pending"),
  submissions: () => getJson<SubmissionResult[]>("/api/submissions"),
  resumeVariants: () => getJson<ResumeVariant[]>("/api/resume-variants"),
  analyticsSummary: () => getJson<AnalyticsSummary>("/api/analytics/summary"),
  settings: () => getJson<RedactedSettings>("/api/settings"),
};
