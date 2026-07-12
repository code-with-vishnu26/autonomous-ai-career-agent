import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAcceptInvite } from "@/hooks/useTeam";

export function AcceptInvitePage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const navigate = useNavigate();
  const acceptInvite = useAcceptInvite();
  const [attempted, setAttempted] = useState(false);

  useEffect(() => {
    if (token && !attempted) {
      setAttempted(true);
      acceptInvite.mutate(token);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once per token
  }, [token]);

  return (
    <div className="mx-auto max-w-md space-y-6 pt-12">
      <Card>
        <CardHeader>
          <CardTitle>Accept invitation</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          {!token && <p className="text-destructive">No invitation token provided.</p>}
          {acceptInvite.isPending && <p>Accepting invitation...</p>}
          {acceptInvite.isSuccess && (
            <>
              <p className="text-success">
                You joined as <span className="font-medium">{acceptInvite.data.role}</span>.
              </p>
              <Button onClick={() => navigate("/organizations")}>
                Go to your organizations
              </Button>
            </>
          )}
          {acceptInvite.isError && (
            <p className="text-destructive">
              {acceptInvite.error instanceof Error
                ? acceptInvite.error.message
                : "This invitation could not be accepted."}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
