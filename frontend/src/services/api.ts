/**
 * Thin fetch wrapper over the FastAPI dashboard API (Phase 54, ADR-0072).
 * One function per route, no client-side business logic beyond parsing
 * JSON -- any derived view (e.g. "applications ready to submit") is
 * computed in a hook from these raw responses, mirroring how
 * `analytics.py`'s own aggregation is presentation logic over the same
 * stores, not a new source of truth.
 *
 * Every route here is a GET, and every one requires authentication
 * (Phase 56, ADR-0074) -- `apiFetchJson` attaches the access token and
 * transparently refreshes it once on a 401. There is no `postX`/`patchX`
 * in this file because the dashboard-data backend exposes none (Phase 54
 * is deliberately read-only) -- see `src/components/CliOnlyAction.tsx`
 * for how write actions are surfaced honestly instead.
 */

import { apiFetchJson } from "./http";
import type {
  AnalyticsSummary,
  ApplicationSession,
  HealthStatus,
  RedactedSettings,
  ResumeVariant,
  ReviewSession,
  SubmissionResult,
} from "@/types/api";

export const api = {
  health: () => apiFetchJson<HealthStatus>("/api/health"),
  applications: () => apiFetchJson<ApplicationSession[]>("/api/applications"),
  reviews: () => apiFetchJson<ReviewSession[]>("/api/reviews"),
  pendingReviews: () => apiFetchJson<ReviewSession[]>("/api/reviews/pending"),
  submissions: () => apiFetchJson<SubmissionResult[]>("/api/submissions"),
  resumeVariants: () => apiFetchJson<ResumeVariant[]>("/api/resume-variants"),
  analyticsSummary: () => apiFetchJson<AnalyticsSummary>("/api/analytics/summary"),
  settings: () => apiFetchJson<RedactedSettings>("/api/settings"),
};
