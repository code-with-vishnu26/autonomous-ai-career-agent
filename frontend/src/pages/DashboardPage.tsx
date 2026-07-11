import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid } from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardValue } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { QueryState } from "@/components/QueryState";
import {
  useApplications,
  useAnalyticsSummary,
  useResumeVariants,
  useSubmissions,
} from "@/hooks/useApi";
import { applicationsPerDay, countBy } from "@/lib/derive";

function StatCard({ title, value }: { title: string; value: number }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <CardValue>{value}</CardValue>
      </CardContent>
    </Card>
  );
}

export function DashboardPage() {
  const applications = useApplications();
  const analytics = useAnalyticsSummary();
  const submissions = useSubmissions();
  const variants = useResumeVariants();

  const isLoading = applications.isLoading || analytics.isLoading || submissions.isLoading;
  const isError = applications.isError || analytics.isError || submissions.isError;

  const pending = analytics.data?.applications_by_status["READY_FOR_REVIEW"] ?? 0;
  const approved = analytics.data?.reviews_by_status["APPROVED"] ?? 0;
  const submitted = analytics.data?.submissions_by_status["SUBMITTED"] ?? 0;
  const prepared = applications.data?.length ?? 0;

  const perDay = applicationsPerDay(applications.data ?? []);
  const providerUsage = countBy(applications.data ?? [], (a) => a.provider);
  const variantUsage = countBy(variants.data ?? [], (v) => v.category);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      <QueryState isLoading={isLoading} isError={isError}>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
          <StatCard title="Prepared" value={prepared} />
          <StatCard title="Pending review" value={pending} />
          <StatCard title="Approved" value={approved} />
          <StatCard title="Submitted" value={submitted} />
          <StatCard
            title="Interviews"
            value={0}
          />
          <StatCard title="Offers" value={0} />
        </div>
        <Callout className="mt-2">
          Interviews/Offers aren't tracked by this dashboard's API yet -- outcome
          recording lives on the older <code>SqliteApplicationStore</code> pipeline
          (<code>career-agent outcome</code>/<code>report</code>), a deliberately
          separate pipeline this dashboard's Phase 54 API doesn't read from.
        </Callout>

        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Applications per day</CardTitle>
            </CardHeader>
            <CardContent className="h-64">
              {perDay.length === 0 ? (
                <p className="text-sm text-muted-foreground">No prepared applications yet.</p>
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
                <p className="text-sm text-muted-foreground">No prepared applications yet.</p>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={Object.entries(providerUsage).map(([provider, count]) => ({
                      provider,
                      count,
                    }))}
                  >
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

        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Success rate (submitted / prepared)</CardTitle>
            </CardHeader>
            <CardContent>
              <CardValue>
                {prepared === 0 ? "—" : `${Math.round((submitted / prepared) * 100)}%`}
              </CardValue>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Resume variants in use</CardTitle>
            </CardHeader>
            <CardContent>
              {Object.keys(variantUsage).length === 0 ? (
                <p className="text-sm text-muted-foreground">No stored variants yet.</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {Object.entries(variantUsage).map(([category, count]) => (
                    <li key={category} className="flex justify-between">
                      <span>{category}</span>
                      <span className="text-muted-foreground">{count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </QueryState>
    </div>
  );
}
