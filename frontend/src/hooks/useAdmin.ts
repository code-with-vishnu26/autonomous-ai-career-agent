/** TanStack Query wrappers over `adminApi` (Phase 60, ADR-0078). */

import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/services/adminApi";

export function useAdminOrganizations() {
  return useQuery({
    queryKey: ["admin", "organizations"],
    queryFn: adminApi.listOrganizations,
  });
}

export function useAdminOrganizationMembers(organizationId: string | undefined) {
  return useQuery({
    queryKey: ["admin", "organizations", organizationId, "members"],
    queryFn: () => adminApi.listOrganizationMembers(organizationId as string),
    enabled: Boolean(organizationId),
  });
}
