/**
 * Thin fetch wrapper over the FastAPI dashboard API's read-only `/api/*`
 * routes (Phase 54, ADR-0072). One function per route, no client-side
 * business logic beyond parsing JSON -- any derived view (e.g.
 * "applications ready to submit") is computed in a hook from these raw
 * responses, mirroring how `analytics.py`'s own aggregation is
 * presentation logic over the same stores, not a new source of truth.
 *
 * Every route here is a GET, and every one requires authentication
 * (Phase 56, ADR-0074) -- `apiFetchJson` attaches the access token and
 * transparently refreshes it once on a 401. Reviews (Phase 63, ADR-0081)
 * moved to `reviewsApi.ts` once they gained a real write action --
 * `discoverApi.ts`/`submissionActionsApi.ts` are the same phase's other
 * two new write-capable service files.
 */

import { apiFetchJson } from "./http";
import type {
  AnalyticsSummary,
  ApplicationSession,
  HealthStatus,
  RedactedSettings,
  ResumeVariant,
  SubmissionResult,
} from "@/types/api";

export const api = {
  health: () => apiFetchJson<HealthStatus>("/api/health"),
  applications: () => apiFetchJson<ApplicationSession[]>("/api/applications"),
  submissions: () => apiFetchJson<SubmissionResult[]>("/api/submissions"),
  resumeVariants: () => apiFetchJson<ResumeVariant[]>("/api/resume-variants"),
  analyticsSummary: () => apiFetchJson<AnalyticsSummary>("/api/analytics/summary"),
  settings: () => apiFetchJson<RedactedSettings>("/api/settings"),
};
