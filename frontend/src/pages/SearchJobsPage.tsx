import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Loader2, Search } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { PrepareButton } from "@/components/PrepareButton";
import { QueryState } from "@/components/QueryState";
import { useJobPreferences, useUpdateJobPreferences } from "@/hooks/useJobPreferences";
import {
  useDiscoveryOpportunities,
  useDiscoveryRun,
  useTriggerDiscovery,
} from "@/hooks/useDiscover";
import type { JobPreferences } from "@/types/api";

interface SearchFormValues {
  role: string;
  countries: string;
  workMode: string;
  salaryMin: string;
  salaryMax: string;
  seniority: string;
  employmentType: string;
  provider: string;
}

function toFormValues(preferences: JobPreferences | undefined): SearchFormValues {
  return {
    role: preferences?.preferred_titles.join(", ") ?? "",
    countries: preferences?.countries.join(", ") ?? "",
    workMode: preferences?.work_mode[0] ?? "any",
    salaryMin: preferences?.salary_min?.toString() ?? "",
    salaryMax: preferences?.salary_max?.toString() ?? "",
    seniority: preferences?.seniority ?? "any",
    employmentType: preferences?.employment_types[0] ?? "any",
    provider: preferences?.preferred_ats_providers[0] ?? "any",
  };
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function toPreferences(
  current: JobPreferences,
  values: SearchFormValues,
): JobPreferences {
  return {
    ...current,
    preferred_titles: splitList(values.role),
    countries: splitList(values.countries),
    work_mode: values.workMode === "any" ? [] : [values.workMode],
    salary_min: values.salaryMin ? Number(values.salaryMin) : null,
    salary_max: values.salaryMax ? Number(values.salaryMax) : null,
    seniority: values.seniority === "any" ? null : values.seniority,
    employment_types: values.employmentType === "any" ? [] : [values.employmentType],
    preferred_ats_providers: values.provider === "any" ? [] : [values.provider],
  };
}

export function SearchJobsPage() {
  const preferences = useJobPreferences();
  const updatePreferences = useUpdateJobPreferences();
  const triggerDiscovery = useTriggerDiscovery();
  const opportunities = useDiscoveryOpportunities();
  const queryClient = useQueryClient();

  const [runId, setRunId] = useState<string | undefined>(undefined);
  const run = useDiscoveryRun(runId);

  const { register, handleSubmit, reset } = useForm<SearchFormValues>({
    defaultValues: toFormValues(preferences.data),
  });

  useEffect(() => {
    if (preferences.data) reset(toFormValues(preferences.data));
  }, [preferences.data, reset]);

  useEffect(() => {
    if (run.data?.status === "COMPLETED") {
      queryClient.invalidateQueries({ queryKey: ["discover", "opportunities"] });
    }
  }, [run.data?.status, queryClient]);

  const onSubmit = handleSubmit((values) => {
    if (!preferences.data) return;
    const updated = toPreferences(preferences.data, values);
    updatePreferences.mutate(updated, {
      onSuccess: () => {
        triggerDiscovery.mutate(undefined, {
          onSuccess: (started) => setRunId(started.id),
        });
      },
    });
  });

  const isSearching = run.data?.status === "PENDING" || run.data?.status === "RUNNING";
  const isSubmitDisabled = !preferences.data || updatePreferences.isPending || isSearching;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Search Jobs</h1>

      <Callout>
        Search runs the exact same discovery pipeline <code>career-agent discover</code>{" "}
        uses (ADR-0081) -- your filters save to Job Search Preferences first
        (<code>PUT /user/preferences</code>), then a background run polls every
        configured source. <strong>Prepare application</strong> then tailors a
        résumé + cover letter for a result from your onboarded Master Profile
        (ADR-0085) and sends it to the Review Queue -- the live form is filled
        and the résumé uploaded later, at submit, behind the confirmation gate.
      </Callout>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Role</span>
              <Input placeholder="Software Engineer" {...register("role")} />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Countries</span>
              <Input placeholder="India, United States" {...register("countries")} />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Work mode</span>
              <Select {...register("workMode")}>
                <option value="any">Any</option>
                <option value="remote">Remote only</option>
                <option value="hybrid">Hybrid</option>
                <option value="onsite">On-site</option>
              </Select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Minimum salary</span>
              <Input type="number" placeholder="80000" {...register("salaryMin")} />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Maximum salary</span>
              <Input type="number" placeholder="150000" {...register("salaryMax")} />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Experience</span>
              <Select {...register("seniority")}>
                <option value="any">Any</option>
                <option value="entry">Entry</option>
                <option value="junior">Junior</option>
                <option value="mid">Mid</option>
                <option value="senior">Senior</option>
                <option value="lead">Lead</option>
                <option value="principal">Principal</option>
                <option value="staff">Staff</option>
              </Select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Employment type</span>
              <Select {...register("employmentType")}>
                <option value="any">Any</option>
                <option value="full_time">Full-time</option>
                <option value="part_time">Part-time</option>
                <option value="contract">Contract</option>
                <option value="internship">Internship</option>
                <option value="temporary">Temporary</option>
              </Select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Preferred ATS</span>
              <Select {...register("provider")}>
                <option value="any">Any</option>
                <option value="greenhouse">Greenhouse</option>
                <option value="lever">Lever</option>
                <option value="ashby">Ashby</option>
                <option value="workday">Workday</option>
              </Select>
            </label>
            <div className="flex items-end sm:col-span-2 lg:col-span-3">
              <Button type="submit" disabled={isSubmitDisabled}>
                {isSearching ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
                {isSearching ? "Searching…" : "Search"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {run.data && (
        <Callout>
          {run.data.status === "PENDING" && "Queued — starting the discovery run…"}
          {run.data.status === "RUNNING" &&
            `Running against ${run.data.source_labels.length || "your configured"} source(s)…`}
          {run.data.status === "COMPLETED" &&
            `Found ${run.data.new_count} new opportunit${run.data.new_count === 1 ? "y" : "ies"}.` +
              (run.data.errors.length > 0
                ? ` ${run.data.errors.length} source(s) failed: ${run.data.errors.join("; ")}`
                : "")}
          {run.data.status === "FAILED" &&
            `This run failed: ${run.data.errors.join("; ") || "unknown error."}`}
        </Callout>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Results</CardTitle>
        </CardHeader>
        <CardContent>
          <QueryState
            isLoading={opportunities.isLoading}
            isError={opportunities.isError}
            isEmpty={(opportunities.data ?? []).length === 0}
            emptyMessage="No opportunities discovered yet -- run a search above."
          >
            <div className="space-y-3">
              {(opportunities.data ?? []).map((opportunity) => (
                <div
                  key={opportunity.id}
                  className="flex flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div>
                    <p className="text-sm font-medium">
                      {opportunity.title} @ {opportunity.canonical_company}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {opportunity.location ?? "Location unspecified"}
                      {opportunity.remote ? " · Remote" : ""}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      <Badge variant="muted">{opportunity.source}</Badge>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <a
                      href={opportunity.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                      View
                    </a>
                    <PrepareButton opportunityId={opportunity.id} />
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
