/**
 * Thin fetch wrapper over `/organizations/*` (Phase 60, ADR-0078).
 */

import { apiFetch, apiFetchJson } from "./http";
import type { Organization } from "@/types/api";

export const organizationsApi = {
  list: () => apiFetchJson<Organization[]>("/organizations"),
  create: (name: string) =>
    apiFetchJson<Organization>("/organizations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  get: (organizationId: string) =>
    apiFetchJson<Organization>(`/organizations/${organizationId}`),
  rename: (organizationId: string, name: string) =>
    apiFetchJson<Organization>(`/organizations/${organizationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  remove: async (organizationId: string) => {
    const response = await apiFetch(`/organizations/${organizationId}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error(`Failed to delete organization (${response.status})`);
  },
};
