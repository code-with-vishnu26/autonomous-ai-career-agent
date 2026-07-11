import { Send } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { StatusBadge } from "@/components/StatusBadge";
import { CliOnlyAction } from "@/components/CliOnlyAction";
import { QueryState } from "@/components/QueryState";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useReviews, useSubmissions } from "@/hooks/useApi";
import { readyForSubmission } from "@/lib/derive";

export function SubmissionQueuePage() {
  const reviews = useReviews();
  const submissions = useSubmissions();

  const isLoading = reviews.isLoading || submissions.isLoading;
  const isError = reviews.isError || submissions.isError;

  const ready = readyForSubmission(reviews.data ?? [], submissions.data ?? []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Submission Queue</h1>

      <Callout>
        There is no live browser state or countdown to show here: submission only
        happens inside a real, supervised <code>career-agent submit</code> terminal
        session -- a 5-second countdown plus a blocking ENTER confirmation
        (ADR-0071) that this dashboard cannot safely reproduce over HTTP.
      </Callout>

      <QueryState isLoading={isLoading} isError={isError}>
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Ready ({ready.length})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {ready.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No approved applications waiting on a submission attempt.
                </p>
              ) : (
                ready.map((review) => (
                  <div
                    key={review.id}
                    className="flex items-center justify-between rounded-md border border-border p-3"
                  >
                    <div>
                      <p className="text-sm font-medium">{review.job_title}</p>
                      <p className="text-xs text-muted-foreground">{review.company}</p>
                    </div>
                    <CliOnlyAction
                      command={`career-agent submit --review-session <artifacts_dir>/reviews/${review.id}.json --opportunity-file <path> --profile <path>`}
                      size="sm"
                    >
                      <Send className="h-4 w-4" />
                      Submit
                    </CliOnlyAction>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Recorded attempts</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {(submissions.data ?? []).length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">
                  No submission attempts recorded yet.
                </p>
              ) : (
                <Table>
                  <THead>
                    <TR>
                      <TH>Company</TH>
                      <TH>Role</TH>
                      <TH>Status</TH>
                      <TH>Warnings</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {(submissions.data ?? []).map((result) => (
                      <TR key={result.id}>
                        <TD>{result.company}</TD>
                        <TD>{result.job_title}</TD>
                        <TD>
                          <StatusBadge status={result.status} />
                        </TD>
                        <TD className="text-xs text-muted-foreground">
                          {result.warnings.length > 0 ? result.warnings.join("; ") : "—"}
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      </QueryState>
    </div>
  );
}
