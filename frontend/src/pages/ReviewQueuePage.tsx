import { useState } from "react";
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { QueryState } from "@/components/QueryState";
import { usePendingReviews, useResumeVariants } from "@/hooks/useApi";
import { useDecideReview } from "@/hooks/useReviewDecision";

export function ReviewQueuePage() {
  const pending = usePendingReviews();
  const variants = useResumeVariants();
  const decide = useDecideReview();
  const [confirming, setConfirming] = useState<{ id: string; approved: boolean } | null>(
    null,
  );

  const sessions = pending.data ?? [];
  const variantById = new Map((variants.data ?? []).map((variant) => [variant.id, variant]));

  function confirmDecision() {
    if (!confirming) return;
    decide.mutate(
      { applicationSessionId: confirming.id, approved: confirming.approved },
      { onSettled: () => setConfirming(null) },
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Review Queue</h1>

      <Callout>
        Approving or rejecting here calls the same <code>ReviewEngine</code>{" "}
        <code>career-agent review</code> uses (ADR-0070, extended over HTTP by
        ADR-0081) -- the sole <code>READY_FOR_REVIEW → APPROVED</code> transition
        boundary. One decision is recorded per session; a second attempt is refused.
      </Callout>

      <QueryState
        isLoading={pending.isLoading}
        isError={pending.isError}
        isEmpty={sessions.length === 0}
        emptyMessage="Nothing waiting for review."
      >
        <div className="space-y-4">
          {sessions.map((session) => {
            const variant = session.resume_variant_id
              ? variantById.get(session.resume_variant_id)
              : undefined;
            const isConfirmingThis = confirming?.id === session.id;
            return (
              <Card key={session.id}>
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="text-base font-semibold text-foreground">
                    {session.job_title} @ {session.company}
                  </CardTitle>
                  <Badge variant="outline" className="capitalize">
                    {session.provider}
                  </Badge>
                </CardHeader>
                <CardContent className="space-y-4">
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

                  {decide.isError && isConfirmingThis === false && (
                    <p className="text-sm text-destructive">{(decide.error as Error).message}</p>
                  )}

                  <div className="flex items-center gap-2 pt-2">
                    {isConfirmingThis ? (
                      <>
                        <span className="text-sm text-muted-foreground">
                          {confirming?.approved
                            ? "Approve this application?"
                            : "Reject this application?"}
                        </span>
                        <Button
                          size="sm"
                          variant={confirming?.approved ? "default" : "destructive"}
                          onClick={confirmDecision}
                          disabled={decide.isPending}
                        >
                          {decide.isPending ? "Working…" : "Yes, confirm"}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setConfirming(null)}
                          disabled={decide.isPending}
                        >
                          Cancel
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button
                          size="sm"
                          onClick={() => setConfirming({ id: session.id, approved: true })}
                        >
                          <CheckCircle2 className="h-4 w-4" />
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => setConfirming({ id: session.id, approved: false })}
                        >
                          <XCircle className="h-4 w-4" />
                          Reject
                        </Button>
                      </>
                    )}
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
