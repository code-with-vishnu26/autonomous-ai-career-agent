/**
 * `/discover/*` (Phase 63, ADR-0081) -- calls the exact same discovery
 * pipeline `career-agent discover` runs, over HTTP. `trigger` returns a
 * `PENDING` run immediately; the caller polls `run` until it reaches
 * `COMPLETED`/`FAILED` (see `useDiscover.ts`'s `refetchInterval`).
 */

import { apiFetchJson } from "./http";
import type { DiscoveryRun, Opportunity } from "@/types/api";

export const discoverApi = {
  trigger: (sinceDays = 7) =>
    apiFetchJson<DiscoveryRun>("/discover", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ since_days: sinceDays }),
    }),
  run: (runId: string) => apiFetchJson<DiscoveryRun>(`/discover/${runId}`),
  runs: () => apiFetchJson<DiscoveryRun[]>("/discover/runs"),
  opportunities: (limit = 50) =>
    apiFetchJson<Opportunity[]>(`/discover/opportunities?limit=${limit}`),
};
