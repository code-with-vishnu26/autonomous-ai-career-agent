/**
 * `/reviews/*` (Phase 63, ADR-0081). Moved off `/api/reviews` (Phase 54,
 * ADR-0072) onto its own write-capable prefix now that `decide` is real --
 * the same "one feature, one prefix, mixed methods" shape
 * `notificationsApi.ts`/`teamApi.ts` already use. `pending` returns
 * `ApplicationSession[]`, not `ReviewSession[]` -- a session with no
 * decision yet has no `ReviewSession` to return (see the backend's own
 * `list_pending_reviews` docstring for why).
 */

import { apiFetchJson } from "./http";
import type { ApplicationSession, ReviewSession } from "@/types/api";

export const reviewsApi = {
  list: () => apiFetchJson<ReviewSession[]>("/reviews"),
  pending: () => apiFetchJson<ApplicationSession[]>("/reviews/pending"),
  decide: (applicationSessionId: string, approved: boolean, notes?: string) =>
    apiFetchJson<ReviewSession>("/reviews/decide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        application_session_id: applicationSessionId,
        approved,
        notes: notes ?? null,
      }),
    }),
};
