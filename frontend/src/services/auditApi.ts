/** Thin fetch wrapper over `/api/audit/*` (Phase 60, ADR-0078). */

import { apiFetchJson } from "./http";
import type { AuditLogEntry } from "@/types/api";

export const auditApi = {
  list: (organizationId: string) =>
    apiFetchJson<AuditLogEntry[]>(`/api/audit/${organizationId}`),
};
