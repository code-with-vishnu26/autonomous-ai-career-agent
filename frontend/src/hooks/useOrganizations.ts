/** TanStack Query wrappers over `organizationsApi` (Phase 60, ADR-0078). */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { organizationsApi } from "@/services/organizationsApi";

export function useOrganizations() {
  return useQuery({ queryKey: ["organizations"], queryFn: organizationsApi.list });
}

export function useOrganization(organizationId: string | undefined) {
  return useQuery({
    queryKey: ["organizations", organizationId],
    queryFn: () => organizationsApi.get(organizationId as string),
    enabled: Boolean(organizationId),
  });
}

export function useCreateOrganization() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => organizationsApi.create(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
    },
  });
}

export function useRenameOrganization(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => organizationsApi.rename(organizationId, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
    },
  });
}

export function useDeleteOrganization() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (organizationId: string) => organizationsApi.remove(organizationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
    },
  });
}
