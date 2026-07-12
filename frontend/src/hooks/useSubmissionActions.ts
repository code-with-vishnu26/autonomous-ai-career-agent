/**
 * TanStack Query wrappers over `submissionActionsApi` (Phase 63,
 * ADR-0081). `usePendingSubmissionStatus` polls every 2s while the
 * attempt is still in flight (`PREPARING`/`AWAITING_CONFIRMATION`/
 * `SUBMITTING`) and stops once it reaches `DONE`/`FAILED` -- the same
 * shape `useDiscover.ts`'s run poll already uses.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { submissionActionsApi } from "@/services/submissionActionsApi";
import type { PendingSubmissionStatus } from "@/types/api";

const STATUS_POLL_INTERVAL_MS = 2_000;

function isInFlight(entry: PendingSubmissionStatus | undefined): boolean {
  return (
    entry?.status === "PREPARING" ||
    entry?.status === "AWAITING_CONFIRMATION" ||
    entry?.status === "SUBMITTING"
  );
}

export function usePrepareSubmission() {
  return useMutation({
    mutationFn: (applicationSessionId: string) =>
      submissionActionsApi.prepare(applicationSessionId),
  });
}

export function usePendingSubmissionStatus(token: string | undefined) {
  return useQuery({
    queryKey: ["submissions", "prepare", token],
    queryFn: () => submissionActionsApi.status(token as string),
    enabled: token !== undefined,
    refetchInterval: (query) => (isInFlight(query.state.data) ? STATUS_POLL_INTERVAL_MS : false),
  });
}

export function useConfirmSubmission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ token, approved }: { token: string; approved: boolean }) =>
      submissionActionsApi.confirm(token, approved),
    onSuccess: (updated) => {
      queryClient.setQueryData(["submissions", "prepare", updated.token], updated);
    },
  });
}
