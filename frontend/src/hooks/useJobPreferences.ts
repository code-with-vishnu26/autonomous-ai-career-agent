/**
 * TanStack Query wrappers over `authApi.getPreferences`/`updatePreferences`
 * (`/user/preferences`, Phase 56, ADR-0074) -- the Search Jobs page's real
 * configuration surface (Phase 63, ADR-0081): `POST /discover` reads
 * whatever is saved here, the same way `career-agent discover` reads
 * `job_preferences.json`.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { authApi } from "@/services/authApi";
import type { JobPreferences } from "@/types/api";

export function useJobPreferences() {
  return useQuery({ queryKey: ["job-preferences"], queryFn: authApi.getPreferences });
}

export function useUpdateJobPreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (preferences: JobPreferences) => authApi.updatePreferences(preferences),
    onSuccess: (updated) => {
      queryClient.setQueryData(["job-preferences"], updated);
    },
  });
}
