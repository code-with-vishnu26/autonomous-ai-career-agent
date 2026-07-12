/** TanStack Query wrapper over `auditApi` (Phase 60, ADR-0078). */

import { useQuery } from "@tanstack/react-query";
import { auditApi } from "@/services/auditApi";

export function useAuditLog(organizationId: string) {
  return useQuery({
    queryKey: ["audit", organizationId],
    queryFn: () => auditApi.list(organizationId),
  });
}
