import { useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/StatusBadge";
import { QueryState } from "@/components/QueryState";
import { DownloadExcelButton } from "@/components/DownloadExcelButton";
import { exportApi } from "@/services/exportApi";
import { useReviews, useSubmissions } from "@/hooks/useApi";

interface TimelineEntry {
  id: string;
  at: string;
  kind: "review" | "submission";
  status: string;
  company: string;
  jobTitle: string;
}

export function HistoryPage() {
  const reviews = useReviews();
  const submissions = useSubmissions();
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<"all" | "review" | "submission">("all");

  const isLoading = reviews.isLoading || submissions.isLoading;
  const isError = reviews.isError || submissions.isError;

  const entries = useMemo<TimelineEntry[]>(() => {
    const reviewEntries: TimelineEntry[] = (reviews.data ?? []).map((r) => ({
      id: r.id,
      at: r.approved_at ?? r.created_at,
      kind: "review",
      status: r.approval_status,
      company: r.company,
      jobTitle: r.job_title,
    }));
    const submissionEntries: TimelineEntry[] = (submissions.data ?? []).map((s) => ({
      id: s.id,
      at: s.submitted_at ?? "",
      kind: "submission",
      status: s.status,
      company: s.company,
      jobTitle: s.job_title,
    }));
    return [...reviewEntries, ...submissionEntries].sort((a, b) =>
      b.at.localeCompare(a.at),
    );
  }, [reviews.data, submissions.data]);

  const filtered = entries.filter((entry) => {
    if (kind !== "all" && entry.kind !== kind) return false;
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return entry.company.toLowerCase().includes(q) || entry.jobTitle.toLowerCase().includes(q);
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">History</h1>
        <DownloadExcelButton
          onDownload={exportApi.submissions}
          label="Download submissions (Excel)"
        />
      </div>

      <div className="flex flex-wrap gap-3">
        <Input
          placeholder="Search by company or role..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="max-w-sm"
        />
        <Select
          value={kind}
          onChange={(event) => setKind(event.target.value as typeof kind)}
          className="max-w-40"
        >
          <option value="all">All events</option>
          <option value="review">Reviews</option>
          <option value="submission">Submissions</option>
        </Select>
      </div>

      <QueryState
        isLoading={isLoading}
        isError={isError}
        isEmpty={filtered.length === 0}
        emptyMessage="No review or submission history yet."
      >
        <ol className="space-y-3 border-l border-border pl-4">
          {filtered.map((entry) => (
            <li key={`${entry.kind}-${entry.id}`} className="relative">
              <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-primary" />
              <Card>
                <CardContent className="flex flex-wrap items-center justify-between gap-2 p-3">
                  <div>
                    <p className="text-sm font-medium">
                      {entry.jobTitle} @ {entry.company}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {entry.kind === "review" ? "Review" : "Submission"}
                      {entry.at ? ` — ${new Date(entry.at).toLocaleString()}` : ""}
                    </p>
                  </div>
                  <StatusBadge status={entry.status} />
                </CardContent>
              </Card>
            </li>
          ))}
        </ol>
      </QueryState>
    </div>
  );
}
