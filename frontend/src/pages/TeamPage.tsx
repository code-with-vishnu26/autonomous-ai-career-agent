import { useState } from "react";
import { useParams } from "react-router-dom";
import { Trash2, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { QueryState } from "@/components/QueryState";
import {
  useInvitations,
  useInviteMember,
  useMembers,
  useRemoveMember,
  useResendInvitation,
  useRevokeInvitation,
  useRoles,
  useUpdateMemberRole,
} from "@/hooks/useTeam";
import type { Role } from "@/types/api";

const ROLE_OPTIONS: Role[] = ["owner", "admin", "recruiter", "member", "viewer"];

export function TeamPage() {
  const { organizationId = "" } = useParams<{ organizationId: string }>();
  const members = useMembers(organizationId);
  const invitations = useInvitations(organizationId);
  const roles = useRoles();
  const updateRole = useUpdateMemberRole(organizationId);
  const removeMember = useRemoveMember(organizationId);
  const inviteMember = useInviteMember(organizationId);
  const revokeInvitation = useRevokeInvitation(organizationId);
  const resendInvitation = useResendInvitation(organizationId);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Role>("member");
  const [inviteError, setInviteError] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Team</h1>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Invite a member</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Input
              placeholder="email@example.com"
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
              className="flex-1"
            />
            <Select
              value={inviteRole}
              onChange={(event) => setInviteRole(event.target.value as Role)}
              className="w-auto"
            >
              {ROLE_OPTIONS.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </Select>
            <Button
              disabled={!inviteEmail || inviteMember.isPending}
              onClick={() => {
                setInviteError(null);
                inviteMember.mutate(
                  { email: inviteEmail, role: inviteRole },
                  {
                    onSuccess: () => setInviteEmail(""),
                    onError: (error: unknown) =>
                      setInviteError(
                        error instanceof Error ? error.message : "Invite failed.",
                      ),
                  },
                );
              }}
            >
              Invite
            </Button>
          </div>
          {inviteError && <p className="text-sm text-destructive">{inviteError}</p>}
          {roles.data && (
            <p className="text-xs text-muted-foreground">
              {roles.data.find((r) => r.role === inviteRole)?.permissions.join(", ")}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Members</CardTitle>
        </CardHeader>
        <CardContent>
          <QueryState isLoading={members.isLoading} isError={members.isError}>
            <div className="space-y-2">
              {members.data?.map((member) => (
                <div
                  key={member.user_id}
                  className="flex items-center justify-between gap-2 border-b border-border py-2 text-sm last:border-0"
                >
                  <div>
                    <p className="font-medium">{member.display_name ?? member.email}</p>
                    <p className="text-xs text-muted-foreground">{member.email}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Select
                      value={member.role}
                      className="w-auto"
                      onChange={(event) =>
                        updateRole.mutate({
                          userId: member.user_id,
                          role: event.target.value as Role,
                        })
                      }
                    >
                      {ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </Select>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Remove member"
                      onClick={() => removeMember.mutate(member.user_id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </QueryState>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Pending &amp; past invitations</CardTitle>
        </CardHeader>
        <CardContent>
          <QueryState
            isLoading={invitations.isLoading}
            isError={invitations.isError}
            isEmpty={invitations.data?.length === 0}
            emptyMessage="No invitations sent yet."
          >
            <div className="space-y-2">
              {invitations.data?.map((invitation) => (
                <div
                  key={invitation.id}
                  className="flex items-center justify-between gap-2 border-b border-border py-2 text-sm last:border-0"
                >
                  <div>
                    <p className="font-medium">{invitation.email}</p>
                    <p className="text-xs text-muted-foreground capitalize">
                      {invitation.role}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={
                        invitation.status === "PENDING"
                          ? "warning"
                          : invitation.status === "ACCEPTED"
                            ? "success"
                            : "muted"
                      }
                    >
                      {invitation.status}
                    </Badge>
                    {invitation.status === "PENDING" && (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => resendInvitation.mutate(invitation.id)}
                        >
                          Resend
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label="Revoke invitation"
                          onClick={() => revokeInvitation.mutate(invitation.id)}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </QueryState>
        </CardContent>
      </Card>
    </div>
  );
}
