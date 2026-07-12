import { useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { QueryState } from "@/components/QueryState";
import { useCreateOrganization, useOrganizations } from "@/hooks/useOrganizations";

export function OrganizationsPage() {
  const { data, isLoading, isError } = useOrganizations();
  const createOrganization = useCreateOrganization();
  const [name, setName] = useState("");

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Organizations</h1>

      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>Create a new organization</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Input
            placeholder="Organization name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Button
            disabled={!name || createOrganization.isPending}
            onClick={() => {
              createOrganization.mutate(name, { onSuccess: () => setName("") });
            }}
          >
            Create
          </Button>
        </CardContent>
      </Card>

      <QueryState
        isLoading={isLoading}
        isError={isError}
        isEmpty={data?.length === 0}
        emptyMessage="You don't belong to any organization yet."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data?.map((organization) => (
            <Card key={organization.id}>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-base font-semibold text-foreground">
                  {organization.name}
                </CardTitle>
                <Badge variant="outline" className="capitalize">
                  {organization.role}
                </Badge>
              </CardHeader>
              <CardContent className="space-y-2">
                <p className="text-xs text-muted-foreground">{organization.slug}</p>
                <div className="flex flex-wrap gap-2">
                  <Link to={`/organizations/${organization.id}/team`}>
                    <Button variant="outline" size="sm">
                      Team
                    </Button>
                  </Link>
                  <Link to={`/organizations/${organization.id}/billing`}>
                    <Button variant="outline" size="sm">
                      Billing
                    </Button>
                  </Link>
                  <Link to={`/organizations/${organization.id}/audit`}>
                    <Button variant="outline" size="sm">
                      Audit Log
                    </Button>
                  </Link>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </QueryState>
    </div>
  );
}
