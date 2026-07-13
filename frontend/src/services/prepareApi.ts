/**
 * Web-triggered Prepare (Phase 67, ADR-0085). Tailors a résumé + cover
 * letter for one opportunity from the caller's stored Master Profile, then
 * hands the result to the Review Queue. `start` triggers; `status` polls.
 */

import { apiFetchJson } from "./http";
import type { PastedJobRequest, PendingPreparationStatus } from "@/types/api";

export const prepareApi = {
  start: (opportunityId: string) =>
    apiFetchJson<PendingPreparationStatus>("/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ opportunity_id: opportunityId }),
    }),
  startPasted: (job: PastedJobRequest) =>
    apiFetchJson<PendingPreparationStatus>("/prepare/pasted", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(job),
    }),
  status: (token: string) =>
    apiFetchJson<PendingPreparationStatus>(`/prepare/${token}`),
};
