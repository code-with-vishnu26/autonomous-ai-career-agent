import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { QueryState } from "@/components/QueryState";
import {
  useNotificationSettings,
  useUpdateNotificationSettings,
} from "@/hooks/useNotifications";

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between border-b border-border py-2 text-sm last:border-0">
      <span>{label}</span>
      <input
        type="checkbox"
        className="h-4 w-4"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  );
}

export function NotificationSettingsPage() {
  const { data, isLoading, isError } = useNotificationSettings();
  const updateSettings = useUpdateNotificationSettings();
  const [webhookUrl, setWebhookUrl] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setWebhookUrl("");
  }, [data?.webhook_configured]);

  const toggle = (field: string, value: boolean) => {
    setSaved(false);
    updateSettings.mutate(
      { [field]: value },
      { onSuccess: () => setSaved(true) },
    );
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Notification Settings</h1>

      <Callout>
        In-app notifications work with no configuration. Email needs an
        administrator-configured SMTP server; without one, email attempts are
        recorded as skipped, never fabricated as sent.
      </Callout>

      <QueryState isLoading={isLoading} isError={isError}>
        {data && (
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Channels</CardTitle>
              </CardHeader>
              <CardContent>
                <ToggleRow
                  label="In-app notifications"
                  checked={data.enable_in_app}
                  onChange={(value) => toggle("enable_in_app", value)}
                />
                <ToggleRow
                  label="Browser notifications"
                  checked={data.enable_browser}
                  onChange={(value) => toggle("enable_browser", value)}
                />
                <ToggleRow
                  label="Email notifications"
                  checked={data.enable_email}
                  onChange={(value) => toggle("enable_email", value)}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Reminders &amp; digests</CardTitle>
              </CardHeader>
              <CardContent>
                <ToggleRow
                  label="Reminders (pending review, pending submission, etc.)"
                  checked={data.enable_reminders}
                  onChange={(value) => toggle("enable_reminders", value)}
                />
                <ToggleRow
                  label="Daily/weekly digests"
                  checked={data.enable_digests}
                  onChange={(value) => toggle("enable_digests", value)}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Webhook</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Status</span>
                  <Badge variant={data.webhook_configured ? "success" : "muted"}>
                    {data.webhook_configured ? "configured" : "not set"}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  Works with any service that accepts an incoming JSON POST --
                  including Slack, Discord, and Microsoft Teams incoming
                  webhooks.
                </p>
                <Input
                  placeholder="https://hooks.example.com/..."
                  value={webhookUrl}
                  onChange={(event) => setWebhookUrl(event.target.value)}
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={!webhookUrl || updateSettings.isPending}
                    onClick={() => {
                      setSaved(false);
                      updateSettings.mutate(
                        { webhook_url: webhookUrl },
                        {
                          onSuccess: () => {
                            setWebhookUrl("");
                            setSaved(true);
                          },
                        },
                      );
                    }}
                  >
                    Save webhook
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!data.webhook_configured || updateSettings.isPending}
                    onClick={() => {
                      setSaved(false);
                      updateSettings.mutate(
                        { webhook_url: "" },
                        { onSuccess: () => setSaved(true) },
                      );
                    }}
                  >
                    Remove
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </QueryState>

      {saved && <p className="text-sm text-success">Saved.</p>}
    </div>
  );
}
