import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { CliOnlyAction } from "@/components/CliOnlyAction";
import { QueryState } from "@/components/QueryState";
import { usePendingReviews, useApplications, useResumeVariants } from "@/hooks/useApi";
import { joinReviewsWithSessions } from "@/lib/derive";

export function ReviewQueuePage() {
  const reviews = usePendingReviews();
  const applications = useApplications();
  const variants = useResumeVariants();

  const isLoading = reviews.isLoading || applications.isLoading;
  const isError = reviews.isError || applications.isError;

  const joined = joinReviewsWithSessions(reviews.data ?? [], applications.data ?? []);
  const variantById = new Map((variants.data ?? []).map((variant) => [variant.id, variant]));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Review Queue</h1>

      <Callout>
        Approving or rejecting a review is a CLI-only action --{" "}
        <code>career-agent review --session &lt;path&gt;</code> is the sole
        <code> READY_FOR_REVIEW → APPROVED</code> transition boundary (ADR-0070). This
        page shows exactly what that command would show you.
      </Callout>

      <QueryState
        isLoading={isLoading}
        isError={isError}
        isEmpty={joined.length === 0}
        emptyMessage="Nothing waiting for review."
      >
        <div className="space-y-4">
          {joined.map(({ review, session }) => {
            const variant = session?.resume_variant_id
              ? variantById.get(session.resume_variant_id)
              : undefined;
            return (
              <Card key={review.id}>
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="text-base font-semibold text-foreground">
                    {review.job_title} @ {review.company}
                  </CardTitle>
                  <Badge variant="outline" className="capitalize">
                    {review.provider}
                  </Badge>
                </CardHeader>
                <CardContent className="space-y-4">
                  {!session ? (
                    <p className="text-sm text-muted-foreground">
                      Application session {review.application_session_id} not found.
                    </p>
                  ) : (
                    <>
                      {variant && (
                        <section>
                          <h3 className="mb-1 text-xs font-medium uppercase text-muted-foreground">
                            Resume preview ({variant.category})
                          </h3>
                          <p className="text-sm">{variant.content.summary}</p>
                          <ul className="mt-1 flex flex-wrap gap-1">
                            {variant.content.skills.slice(0, 12).map((skill) => (
                              <Badge key={skill} variant="muted">
                                {skill}
                              </Badge>
                            ))}
                          </ul>
                        </section>
                      )}

                      {session.cover_letter_body && (
                        <section>
                          <h3 className="mb-1 text-xs font-medium uppercase text-muted-foreground">
                            Cover letter preview
                          </h3>
                          <p className="whitespace-pre-line text-sm text-muted-foreground">
                            {session.cover_letter_body.slice(0, 400)}
                            {session.cover_letter_body.length > 400 ? "…" : ""}
                          </p>
                        </section>
                      )}

                      {session.warnings.length > 0 && (
                        <section>
                          <h3 className="mb-1 flex items-center gap-1 text-xs font-medium uppercase text-warning">
                            <AlertTriangle className="h-3.5 w-3.5" /> Warnings
                          </h3>
                          <ul className="list-inside list-disc text-sm text-muted-foreground">
                            {session.warnings.map((warning) => (
                              <li key={warning}>{warning}</li>
                            ))}
                          </ul>
                        </section>
                      )}

                      {session.missing_fields.length > 0 && (
                        <section>
                          <h3 className="mb-1 text-xs font-medium uppercase text-muted-foreground">
                            Missing fields
                          </h3>
                          <ul className="flex flex-wrap gap-1">
                            {session.missing_fields.map((field) => (
                              <Badge key={field} variant="destructive">
                                {field}
                              </Badge>
                            ))}
                          </ul>
                        </section>
                      )}

                      {session.uploaded_files.length > 0 && (
                        <section>
                          <h3 className="mb-1 text-xs font-medium uppercase text-muted-foreground">
                            Uploaded files
                          </h3>
                          <ul className="text-sm text-muted-foreground">
                            {session.uploaded_files.map((file) => (
                              <li key={file}>{file}</li>
                            ))}
                          </ul>
                        </section>
                      )}
                    </>
                  )}

                  <div className="flex gap-2 pt-2">
                    <CliOnlyAction command={`career-agent review --session <artifacts_dir>/sessions/${session?.id ?? review.application_session_id}.json`}>
                      <CheckCircle2 className="h-4 w-4" />
                      Approve
                    </CliOnlyAction>
                    <CliOnlyAction command={`career-agent review --session <artifacts_dir>/sessions/${session?.id ?? review.application_session_id}.json`}>
                      <XCircle className="h-4 w-4" />
                      Reject
                    </CliOnlyAction>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </QueryState>
    </div>
  );
}
