/**
 * Thin fetch wrapper over `/team/*` and `/api/roles*` (Phase 60, ADR-0078).
 */

import { apiFetch, apiFetchJson } from "./http";
import type { Invitation, Member, Role, RolePermissions } from "@/types/api";

export const teamApi = {
  listMembers: (organizationId: string) =>
    apiFetchJson<Member[]>(`/team/${organizationId}`),
  updateMemberRole: (organizationId: string, userId: string, role: Role) =>
    apiFetchJson<Member>(`/team/${organizationId}/members/${userId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    }),
  removeMember: async (organizationId: string, userId: string) => {
    const response = await apiFetch(`/team/${organizationId}/members/${userId}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error(`Failed to remove member (${response.status})`);
  },
  invite: (organizationId: string, email: string, role: Role) =>
    apiFetchJson<Invitation>(`/team/${organizationId}/invite`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, role }),
    }),
  listInvitations: (organizationId: string) =>
    apiFetchJson<Invitation[]>(`/team/${organizationId}/invitations`),
  revokeInvitation: async (organizationId: string, invitationId: string) => {
    const response = await apiFetch(
      `/team/${organizationId}/invitations/${invitationId}`,
      { method: "DELETE" },
    );
    if (!response.ok) throw new Error(`Failed to revoke invitation (${response.status})`);
  },
  resendInvitation: (organizationId: string, invitationId: string) =>
    apiFetchJson<Invitation>(
      `/team/${organizationId}/invitations/${invitationId}/resend`,
      { method: "POST" },
    ),
  acceptInvite: (token: string) =>
    apiFetchJson<Member>("/team/invite/accept", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    }),
  listRoles: () => apiFetchJson<RolePermissions[]>("/api/roles"),
};
