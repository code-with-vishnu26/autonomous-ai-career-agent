import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid } from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardValue } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { QueryState } from "@/components/QueryState";
import { useAnalyticsSummary, useApplications } from "@/hooks/useApi";
import { applicationsPerDay, countBy } from "@/lib/derive";

function toChartData(record: Record<string, number>, keyName: string) {
  return Object.entries(record).map(([key, count]) => ({ [keyName]: key, count }));
}

export function AnalyticsPage() {
  const analytics = useAnalyticsSummary();
  const applications = useApplications();

  const isLoading = analytics.isLoading || applications.isLoading;
  const isError = analytics.isError || applications.isError;

  const submissionsByStatus = analytics.data?.submissions_by_status ?? {};
  const submittedCount = submissionsByStatus["SUBMITTED"] ?? 0;
  const totalSubmissions = Object.values(submissionsByStatus).reduce((a, b) => a + b, 0);
  const successRate = totalSubmissions === 0 ? null : submittedCount / totalSubmissions;

  const providerUsage = countBy(applications.data ?? [], (a) => a.provider);
  const perDay = applicationsPerDay(applications.data ?? []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Analytics</h1>

      <Callout>
        Interview rate and offer rate aren't shown: no route in this API exposes
        interview/offer outcomes (that's the older, separate outcome-tracking
        pipeline — see the Dashboard page's note). Every chart below is a real
        aggregation over <code>/api/analytics/summary</code> and{" "}
        <code>/api/applications</code>, nothing simulated.
      </Callout>

      <QueryState isLoading={isLoading} isError={isError}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>Submission success rate</CardTitle>
            </CardHeader>
            <CardContent>
              <CardValue>
                {successRate === null ? "—" : `${Math.round(successRate * 100)}%`}
              </CardValue>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Applications per day</CardTitle>
            </CardHeader>
            <CardContent className="h-64">
              {perDay.length === 0 ? (
                <p className="text-sm text-muted-foreground">No data yet.</p>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={perDay}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="hsl(var(--primary))" radius={4} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Provider usage</CardTitle>
            </CardHeader>
            <CardContent className="h-64">
              {Object.keys(providerUsage).length === 0 ? (
                <p className="text-sm text-muted-foreground">No data yet.</p>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={toChartData(providerUsage, "provider")}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="provider" tick={{ fontSize: 11 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="hsl(var(--primary))" radius={4} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Submissions by status</CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            {totalSubmissions === 0 ? (
              <p className="text-sm text-muted-foreground">No submission attempts yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={toChartData(submissionsByStatus, "status")}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis dataKey="status" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="hsl(var(--primary))" radius={4} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </QueryState>
    </div>
  );
}
