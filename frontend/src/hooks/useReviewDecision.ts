/**
 * TanStack Query wrapper over `reviewsApi.decide` (Phase 63, ADR-0081) --
 * the sole web-reachable READY_FOR_REVIEW -> APPROVED/REJECTED transition.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { reviewsApi } from "@/services/reviewsApi";

export function useDecideReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      applicationSessionId,
      approved,
      notes,
    }: {
      applicationSessionId: string;
      approved: boolean;
      notes?: string;
    }) => reviewsApi.decide(applicationSessionId, approved, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reviews"] });
    },
  });
}
