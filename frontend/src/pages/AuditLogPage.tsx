import { useParams } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { QueryState } from "@/components/QueryState";
import { useAuditLog } from "@/hooks/useAuditLog";

export function AuditLogPage() {
  const { organizationId = "" } = useParams<{ organizationId: string }>();
  const { data, isLoading, isError } = useAuditLog(organizationId);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Audit Log</h1>

      <QueryState
        isLoading={isLoading}
        isError={isError}
        isEmpty={data?.length === 0}
        emptyMessage="No recorded activity yet."
      >
        <Card>
          <CardContent className="divide-y divide-border p-0">
            {data?.map((entry) => (
              <div key={entry.id} className="flex items-center justify-between p-3 text-sm">
                <div>
                  <p className="font-mono">{entry.action}</p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(entry.created_at).toLocaleString()}
                    {entry.ip_address ? ` -- ${entry.ip_address}` : ""}
                  </p>
                </div>
                <span
                  className={
                    entry.result === "ok" ? "text-success" : "text-destructive"
                  }
                >
                  {entry.result}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </QueryState>
    </div>
  );
}
