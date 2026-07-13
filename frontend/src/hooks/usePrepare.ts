/**
 * TanStack Query wrappers over `prepareApi` (Phase 67, ADR-0085).
 * `usePreparationStatus` polls every 2s while still `PREPARING` and stops
 * on `DONE`/`FAILED` -- the same `refetchInterval` shape `useDiscover.ts`
 * uses for discovery runs.
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import { prepareApi } from "@/services/prepareApi";
import type { PendingPreparationStatus } from "@/types/api";

const POLL_INTERVAL_MS = 2_000;

function isInFlight(status: PendingPreparationStatus | undefined): boolean {
  return status?.status === "PREPARING";
}

export function useStartPreparation() {
  return useMutation({
    mutationFn: (opportunityId: string) => prepareApi.start(opportunityId),
  });
}

export function usePreparationStatus(token: string | undefined) {
  return useQuery({
    queryKey: ["prepare", token],
    queryFn: () => prepareApi.status(token as string),
    enabled: token !== undefined,
    refetchInterval: (query) =>
      isInFlight(query.state.data) ? POLL_INTERVAL_MS : false,
  });
}
