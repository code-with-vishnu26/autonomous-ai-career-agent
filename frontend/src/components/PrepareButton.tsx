/**
 * Phase 67 (ADR-0085). Web-triggers résumé + cover-letter tailoring for one
 * opportunity from the stored Master Profile, then routes the human to the
 * Review Queue -- the "AI builds your résumé from the details you entered"
 * step of the fully web-driven apply loop. The real form fill and résumé
 * upload happen later, at submit, behind the human-confirmation gate.
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { useStartPreparation, usePreparationStatus } from "@/hooks/usePrepare";

interface PrepareButtonProps {
  opportunityId: string;
}

export function PrepareButton({ opportunityId }: PrepareButtonProps) {
  const [token, setToken] = useState<string | undefined>(undefined);
  const start = useStartPreparation();
  const status = usePreparationStatus(token);

  const state = status.data?.status;
  const isBusy = start.isPending || state === "PREPARING";

  if (state === "DONE") {
    return (
      <Link to="/review" className={buttonVariants({ variant: "outline", size: "sm" })}>
        Review application
      </Link>
    );
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        size="sm"
        disabled={isBusy}
        aria-busy={isBusy}
        onClick={() =>
          start.mutate(opportunityId, {
            onSuccess: (started) => setToken(started.token),
          })
        }
      >
        <Sparkles className="mr-1 h-3.5 w-3.5" />
        {isBusy ? "Tailoring…" : "Prepare application"}
      </Button>
      {state === "FAILED" && status.data?.error && (
        <p className="max-w-56 text-right text-xs text-destructive">
          {status.data.error}
        </p>
      )}
      {start.isError && (
        <p className="text-xs text-destructive">
          {(start.error as Error).message}
        </p>
      )}
    </div>
  );
}
