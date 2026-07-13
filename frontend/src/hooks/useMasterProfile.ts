/**
 * TanStack Query wrappers over `masterProfileApi` (Phase 64, ADR-0082).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { masterProfileApi } from "@/services/masterProfileApi";
import type { MasterProfileUpdate } from "@/types/api";

export function useMasterProfile() {
  return useQuery({ queryKey: ["master-profile"], queryFn: masterProfileApi.get });
}

export function useUpdateMasterProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (profile: MasterProfileUpdate) => masterProfileApi.update(profile),
    onSuccess: (updated) => {
      queryClient.setQueryData(["master-profile"], updated);
    },
  });
}
