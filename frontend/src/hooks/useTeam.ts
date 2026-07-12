/** TanStack Query wrappers over `teamApi` (Phase 60, ADR-0078). */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { teamApi } from "@/services/teamApi";
import type { Role } from "@/types/api";

export function useMembers(organizationId: string) {
  return useQuery({
    queryKey: ["team", organizationId, "members"],
    queryFn: () => teamApi.listMembers(organizationId),
  });
}

export function useUpdateMemberRole(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: Role }) =>
      teamApi.updateMemberRole(organizationId, userId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team", organizationId] });
    },
  });
}

export function useRemoveMember(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => teamApi.removeMember(organizationId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team", organizationId] });
    },
  });
}

export function useInvitations(organizationId: string) {
  return useQuery({
    queryKey: ["team", organizationId, "invitations"],
    queryFn: () => teamApi.listInvitations(organizationId),
  });
}

export function useInviteMember(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ email, role }: { email: string; role: Role }) =>
      teamApi.invite(organizationId, email, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team", organizationId] });
    },
  });
}

export function useRevokeInvitation(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (invitationId: string) =>
      teamApi.revokeInvitation(organizationId, invitationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team", organizationId] });
    },
  });
}

export function useResendInvitation(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (invitationId: string) =>
      teamApi.resendInvitation(organizationId, invitationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team", organizationId] });
    },
  });
}

export function useAcceptInvite() {
  return useMutation({ mutationFn: (token: string) => teamApi.acceptInvite(token) });
}

export function useRoles() {
  return useQuery({ queryKey: ["roles"], queryFn: teamApi.listRoles });
}
