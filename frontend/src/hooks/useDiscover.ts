/**
 * TanStack Query wrappers over `discoverApi` (Phase 63, ADR-0081).
 * `useDiscoveryRun` polls every 2s while the run is still
 * `PENDING`/`RUNNING` -- the same "no websockets, just `refetchInterval`"
 * shape `useNotifications.ts`'s unread poll already commits to -- and
 * stops once it reaches `COMPLETED`/`FAILED`.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { discoverApi } from "@/services/discoverApi";
import type { DiscoveryRun } from "@/types/api";

const RUN_POLL_INTERVAL_MS = 2_000;

function isInFlight(run: DiscoveryRun | undefined): boolean {
  return run?.status === "PENDING" || run?.status === "RUNNING";
}

export function useTriggerDiscovery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sinceDays?: number) => discoverApi.trigger(sinceDays),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["discover", "runs"] });
    },
  });
}

export function useDiscoveryRun(runId: string | undefined) {
  return useQuery({
    queryKey: ["discover", "run", runId],
    queryFn: () => discoverApi.run(runId as string),
    enabled: runId !== undefined,
    refetchInterval: (query) => (isInFlight(query.state.data) ? RUN_POLL_INTERVAL_MS : false),
  });
}

export function useDiscoveryOpportunities() {
  return useQuery({
    queryKey: ["discover", "opportunities"],
    queryFn: () => discoverApi.opportunities(),
  });
}
