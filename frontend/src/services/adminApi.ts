/**
 * Thin fetch wrapper over `/api/admin/*` (Phase 60, ADR-0078) --
 * platform-superadmin only (`User.role === "admin"`), a separate concept
 * from an organization's own `owner`/`admin` role.
 */

import { apiFetchJson } from "./http";
import type { AdminOrganization, Member } from "@/types/api";

export const adminApi = {
  listOrganizations: () => apiFetchJson<AdminOrganization[]>("/api/admin/organizations"),
  listOrganizationMembers: (organizationId: string) =>
    apiFetchJson<Member[]>(`/api/admin/organizations/${organizationId}/members`),
};
