/**
 * Phase 68 (ADR-0086). Assisted-apply for platforms this project never
 * scrapes (LinkedIn, Indeed, Naukri, Workday -- ADR-0036): paste a posting
 * you found there, the AI tailors a résumé + cover letter for it from your
 * Master Profile, and you apply on the platform's own site. No auto-submit
 * -- a pasted posting resolves to no known ATS, so the submission engine
 * refuses it anyway; this is tailoring + tracking, not automation of a
 * site that forbids it.
 */

import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button, buttonVariants } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { useStartPastedPreparation, usePreparationStatus } from "@/hooks/usePrepare";
import type { PastedJobRequest } from "@/types/api";

export function PasteJobCard() {
  const { register, handleSubmit, reset } = useForm<PastedJobRequest>();
  const [token, setToken] = useState<string | undefined>(undefined);
  const start = useStartPastedPreparation();
  const status = usePreparationStatus(token);

  const state = status.data?.status;
  const isBusy = start.isPending || state === "PREPARING";

  const onSubmit = (values: PastedJobRequest) => {
    start.mutate(values, {
      onSuccess: (started) => {
        setToken(started.token);
        reset();
      },
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Paste a job from LinkedIn / Indeed / Naukri</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Callout>
          These sites can't be auto-searched (their terms prohibit it), so
          paste a posting here: the AI tailors your résumé + cover letter for
          it, and you submit on the site itself.
        </Callout>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              placeholder="Job title"
              aria-label="Job title"
              {...register("title", { required: true })}
            />
            <Input
              placeholder="Company"
              aria-label="Company"
              {...register("company", { required: true })}
            />
          </div>
          <Input
            placeholder="Posting URL (optional)"
            aria-label="Posting URL"
            {...register("url")}
          />
          <Textarea
            placeholder="Paste the full job description here..."
            aria-label="Job description"
            rows={6}
            {...register("description", { required: true })}
          />
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={isBusy} aria-busy={isBusy}>
              <Sparkles className="mr-1 h-3.5 w-3.5" />
              {isBusy ? "Tailoring…" : "Tailor for this job"}
            </Button>
            {state === "DONE" && (
              <Link
                to="/review"
                className={buttonVariants({ variant: "outline", size: "default" })}
              >
                Review application
              </Link>
            )}
          </div>
        </form>
        {state === "FAILED" && status.data?.error && (
          <p className="text-xs text-destructive">{status.data.error}</p>
        )}
        {start.isError && (
          <p className="text-xs text-destructive">
            {(start.error as Error).message}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
