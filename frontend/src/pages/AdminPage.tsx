import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { QueryState } from "@/components/QueryState";
import { Callout } from "@/components/ui/callout";
import { useAdminOrganizationMembers, useAdminOrganizations } from "@/hooks/useAdmin";

export function AdminPage() {
  const organizations = useAdminOrganizations();
  const [selected, setSelected] = useState<string | undefined>();
  const members = useAdminOrganizationMembers(selected);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Platform Admin</h1>

      <Callout>
        Visible only to platform administrators (an account-level flag,
        separate from any organization's own owner/admin role).
      </Callout>

      <QueryState
        isLoading={organizations.isLoading}
        isError={organizations.isError}
        isEmpty={organizations.data?.length === 0}
      >
        <Card>
          <CardHeader>
            <CardTitle>Every organization on the platform</CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-border p-0">
            {organizations.data?.map((organization) => (
              <button
                key={organization.id}
                onClick={() => setSelected(organization.id)}
                className="flex w-full items-center justify-between p-3 text-left text-sm hover:bg-accent"
              >
                <span>{organization.name}</span>
                <span className="text-muted-foreground">
                  {organization.member_count} member(s)
                </span>
              </button>
            ))}
          </CardContent>
        </Card>
      </QueryState>

      {selected && (
        <Card>
          <CardHeader>
            <CardTitle>Members</CardTitle>
          </CardHeader>
          <CardContent>
            <QueryState isLoading={members.isLoading} isError={members.isError}>
              <div className="space-y-1">
                {members.data?.map((member) => (
                  <div
                    key={member.user_id}
                    className="flex items-center justify-between text-sm"
                  >
                    <span>{member.email}</span>
                    <span className="capitalize text-muted-foreground">{member.role}</span>
                  </div>
                ))}
              </div>
            </QueryState>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
