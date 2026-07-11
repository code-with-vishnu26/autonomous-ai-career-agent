import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { QueryState } from "@/components/QueryState";
import { useSettings } from "@/hooks/useApi";

const PROFILE_KEYS = ["job_preferences_path", "database_path", "artifacts_dir"];
const BROWSER_KEYS = ["browser_session_dir"];
const EXPORT_KEYS = ["promptfoo_results_dir"];

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}

export function SettingsPage() {
  const { data, isLoading, isError } = useSettings();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <Callout>
        Read-only: this page reads <code>GET /api/settings</code> exactly as
        returned. Editing configuration is a <code>.env</code>/CLI action (
        <code>career-agent preferences</code>); there is no write endpoint for it.
      </Callout>

      <QueryState isLoading={isLoading} isError={isError}>
        {data && (
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Profile &amp; job preferences</CardTitle>
              </CardHeader>
              <CardContent>
                {PROFILE_KEYS.map((key) => (
                  <Row key={key} label={key} value={String(data.values[key] ?? "—")} />
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Browser</CardTitle>
              </CardHeader>
              <CardContent>
                {BROWSER_KEYS.map((key) => (
                  <Row key={key} label={key} value={String(data.values[key] ?? "—")} />
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Export</CardTitle>
              </CardHeader>
              <CardContent>
                {EXPORT_KEYS.map((key) => (
                  <Row key={key} label={key} value={String(data.values[key] ?? "—")} />
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>API keys</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {Object.entries(data.configured_secrets).map(([key, configured]) => (
                  <div key={key} className="flex items-center justify-between text-sm">
                    <span className="font-mono text-muted-foreground">{key}</span>
                    <Badge variant={configured ? "success" : "muted"}>
                      {configured ? "configured" : "not set"}
                    </Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        )}
      </QueryState>
    </div>
  );
}
