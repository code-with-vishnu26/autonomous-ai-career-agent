/**
 * Résumé upload + review (Phase 71, ADR-0089) -- lets onboarding also
 * accept an existing résumé instead of hand-typing every field. Upload
 * parses the file into proposed facts with the evidence text they were
 * found in; nothing is written to the profile until the user explicitly
 * confirms or rejects each one here (an un-decided proposal is left
 * `UNVERIFIED` and is never promoted -- the same fail-closed boundary
 * `career-agent import-cv`/`promote-cv` has used since Phase 26,
 * ADR-0052, reused unmodified on the backend).
 */

import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Callout } from "@/components/ui/callout";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { useConfirmResumeImport, useUploadResume } from "@/hooks/useCvImport";
import type { CvImportProposal, CvImportProposalDecision } from "@/types/api";

type Decision = "skip" | "confirm" | "reject";

const ACCEPTED_EXTENSIONS = ".pdf,.docx,.txt,.md";

const OUTCOME_BADGE: Record<string, BadgeProps["variant"]> = {
  ADD: "success",
  NO_OP: "muted",
  REQUIRES_RESOLUTION: "warning",
  REJECT: "destructive",
  SKIPPED_NO_TARGET: "muted",
};

function formatFieldPath(fieldPath: string): string {
  if (fieldPath === "skills") return "Skill";
  const key = fieldPath.split(".", 2)[1] ?? fieldPath;
  return key.charAt(0).toUpperCase() + key.slice(1);
}

export function ResumeImportPanel() {
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadResume();
  const confirm = useConfirmResumeImport();
  const [proposals, setProposals] = useState<CvImportProposal[] | null>(null);
  const [token, setToken] = useState<string | undefined>(undefined);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    confirm.reset();
    upload.mutate(file, {
      onSuccess: (response) => {
        setToken(response.token);
        setProposals(response.proposals);
        setDecisions({});
      },
    });
    event.target.value = "";
  };

  const setDecision = (proposalId: string, decision: Decision) =>
    setDecisions((prev) => ({ ...prev, [proposalId]: decision }));

  const handleSave = () => {
    if (!token) return;
    const body: CvImportProposalDecision[] = Object.entries(decisions)
      .filter(([, decision]) => decision !== "skip")
      .map(([proposal_id, decision]) => ({
        proposal_id,
        confirmed: decision === "confirm",
      }));
    confirm.mutate({ token, decisions: body });
  };

  const decidedCount = Object.values(decisions).filter((d) => d !== "skip").length;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Import from an existing résumé</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Callout>
          Upload a résumé (PDF, DOCX, TXT, or MD) and the AI will find your
          name, email, phone, location, and skills, showing exactly what it
          found and where. Nothing is saved to your profile until you
          confirm each fact below -- reject anything wrong, and leave the
          rest skipped if you're not sure.
        </Callout>

        <div className="flex items-center gap-3">
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS}
            aria-label="Résumé file"
            className="hidden"
            onChange={handleFileChange}
          />
          <Button
            type="button"
            variant="outline"
            disabled={upload.isPending}
            aria-busy={upload.isPending}
            onClick={() => inputRef.current?.click()}
          >
            <Upload className="h-4 w-4" />
            {upload.isPending ? "Analyzing résumé…" : "Choose résumé file"}
          </Button>
        </div>

        {upload.isError && (
          <p className="text-sm text-destructive">{(upload.error as Error).message}</p>
        )}

        {proposals && proposals.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No facts could be confidently extracted from that file. You can
            still fill in the steps below by hand.
          </p>
        )}

        {proposals && proposals.length > 0 && (
          <div className="space-y-3">
            {proposals.map((proposal) => (
              <div
                key={proposal.proposal_id}
                className="space-y-2 rounded-md border border-border p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">
                      {formatFieldPath(proposal.field_path)}:{" "}
                      <span className="font-normal">{proposal.proposed_value}</span>
                    </p>
                    {proposal.evidence_text && (
                      <p className="text-xs text-muted-foreground">
                        Found: "{proposal.evidence_text}"
                      </p>
                    )}
                  </div>
                  <Select
                    aria-label={`Decision for ${formatFieldPath(proposal.field_path)}: ${proposal.proposed_value}`}
                    className="w-44 shrink-0"
                    value={decisions[proposal.proposal_id] ?? "skip"}
                    onChange={(e) =>
                      setDecision(proposal.proposal_id, e.target.value as Decision)
                    }
                  >
                    <option value="skip">Skip (leave unconfirmed)</option>
                    <option value="confirm">Confirm -- this is correct</option>
                    <option value="reject">Reject -- this is wrong</option>
                  </Select>
                </div>
              </div>
            ))}
            <Button
              type="button"
              onClick={handleSave}
              disabled={decidedCount === 0 || confirm.isPending}
              aria-busy={confirm.isPending}
            >
              {confirm.isPending ? "Saving…" : `Save ${decidedCount} decision${decidedCount === 1 ? "" : "s"}`}
            </Button>
          </div>
        )}

        {confirm.isError && (
          <p className="text-sm text-destructive">{(confirm.error as Error).message}</p>
        )}

        {confirm.isSuccess && (
          <div className="space-y-2">
            <Callout>
              {confirm.data.profile_saved
                ? "Profile updated from your résumé. The steps below are now pre-filled -- review and adjust as needed."
                : confirm.data.missing_required_fields.length > 0
                  ? `Your profile still needs: ${confirm.data.missing_required_fields.join(", ")}. Fill those in below.`
                  : "Nothing was saved -- see the outcome for each decision below."}
            </Callout>
            <div className="space-y-1">
              {confirm.data.results
                .filter((result) => decisions[result.proposal_id] !== undefined)
                .map((result) => (
                  <div
                    key={result.proposal_id}
                    className="flex items-center justify-between gap-2 text-xs"
                  >
                    <span className="text-muted-foreground">
                      {formatFieldPath(result.field_path)}: {result.proposed_value} --{" "}
                      {result.reason}
                    </span>
                    <Badge variant={OUTCOME_BADGE[result.outcome] ?? "outline"}>
                      {result.outcome}
                    </Badge>
                  </div>
                ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
