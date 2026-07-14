/**
 * TanStack Query wrappers over `cvImportApi` (Phase 71, ADR-0089).
 * `useConfirmResumeImport` writes a returned (non-null) `profile` straight
 * into the `["master-profile"]` query cache -- the same cache key
 * `useMasterProfile`/`useUpdateMasterProfile` use -- so the rest of the
 * onboarding wizard's `useEffect` (which resets the form whenever
 * `profile.data` changes) picks up newly-confirmed facts with no extra
 * wiring, exactly as it already does after a manual save.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cvImportApi } from "@/services/cvImportApi";
import type { CvImportProposalDecision } from "@/types/api";

export function useUploadResume() {
  return useMutation({
    mutationFn: (file: File) => cvImportApi.upload(file),
  });
}

export function useConfirmResumeImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      token,
      decisions,
    }: {
      token: string;
      decisions: CvImportProposalDecision[];
    }) => cvImportApi.confirm(token, decisions),
    onSuccess: (result) => {
      if (result.profile) {
        queryClient.setQueryData(["master-profile"], result.profile);
      }
    },
  });
}
