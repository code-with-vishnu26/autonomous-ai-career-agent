import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { StatusBadge } from "@/components/StatusBadge";
import { QueryState } from "@/components/QueryState";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useReviews, useSubmissions } from "@/hooks/useApi";
import {
  useConfirmSubmission,
  usePendingSubmissionStatus,
  usePrepareSubmission,
} from "@/hooks/useSubmissionActions";
import { readyForSubmission } from "@/lib/derive";
import type { ReviewSession } from "@/types/api";

function SubmissionCard({ review }: { review: ReviewSession }) {
  const queryClient = useQueryClient();
  const prepare = usePrepareSubmission();
  const confirm = useConfirmSubmission();
  const [token, setToken] = useState<string | undefined>(undefined);
  const status = usePendingSubmissionStatus(token);
  const entry = status.data;

  useEffect(() => {
    if (entry?.status === "DONE") {
      queryClient.invalidateQueries({ queryKey: ["submissions"] });
    }
  }, [entry?.status, queryClient]);

  function startSubmit() {
    prepare.mutate(review.application_session_id, {
      onSuccess: (result) => setToken(result.token),
    });
  }

  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">{review.job_title}</p>
          <p className="text-xs text-muted-foreground">{review.company}</p>
        </div>
        {!token && (
          <Button size="sm" onClick={startSubmit} disabled={prepare.isPending}>
            <Send className="h-4 w-4" />
            {prepare.isPending ? "Starting…" : "Submit"}
          </Button>
        )}
      </div>

      {prepare.isError && (
        <p className="text-xs text-destructive">{(prepare.error as Error).message}</p>
      )}

      {token && entry && (
        <div className="rounded-md bg-muted/50 p-2 text-sm">
          {entry.status === "PREPARING" && (
            <p>Preparing — re-tailoring the résumé and running the promptfoo gate…</p>
          )}
          {entry.status === "AWAITING_CONFIRMATION" && (
            <div className="flex flex-wrap items-center gap-2">
              <span>Every precondition holds. Confirm the real submission?</span>
              <Button
                size="sm"
                onClick={() => confirm.mutate({ token, approved: true })}
                disabled={confirm.isPending}
              >
                Confirm submit
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => confirm.mutate({ token, approved: false })}
                disabled={confirm.isPending}
              >
                Cancel
              </Button>
            </div>
          )}
          {entry.status === "SUBMITTING" && <p>Submitting…</p>}
          {entry.status === "DONE" && <p>Done — see Recorded attempts below.</p>}
          {entry.status === "FAILED" && (
            <p className="text-destructive">Failed: {entry.error}</p>
          )}
        </div>
      )}
    </div>
  );
}

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
        Submitting here calls the exact same <code>submit_prepared_application</code>/
        <code>SubmissionEngine</code> <code>career-agent submit</code> uses (ADR-0071,
        extended over HTTP by ADR-0081) -- the same fail-closed preconditions, and a
        real, un-bypassable confirmation gate (a bounded wait; declining or letting it
        time out never submits). If the browser pauses for a login wall or challenge
        mid-attempt, it closes and reports <code>FAILED</code> -- finish that one from
        the CLI.
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
                ready.map((review) => <SubmissionCard key={review.id} review={review} />)
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
