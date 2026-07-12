/**
 * `/submissions/prepare` + `/submissions/{token}/confirm` (Phase 63,
 * ADR-0081) -- the two-step web analogue of `career-agent submit`'s
 * countdown-then-ENTER gate. `prepare` starts the background attempt and
 * returns a token immediately; the caller polls `status` until it reaches
 * `AWAITING_CONFIRMATION` (then calls `confirm`) or `DONE`/`FAILED`.
 */

import { apiFetchJson } from "./http";
import type { PendingSubmissionStatus } from "@/types/api";

export const submissionActionsApi = {
  prepare: (applicationSessionId: string) =>
    apiFetchJson<PendingSubmissionStatus>("/submissions/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ application_session_id: applicationSessionId }),
    }),
  status: (token: string) =>
    apiFetchJson<PendingSubmissionStatus>(`/submissions/prepare/${token}`),
  confirm: (token: string, approved: boolean) =>
    apiFetchJson<PendingSubmissionStatus>(`/submissions/${token}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved }),
    }),
};
